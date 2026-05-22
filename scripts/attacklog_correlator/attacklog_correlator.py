#!/usr/bin/env python3

# Author: Erik Grafendorfer, AIT
# 
# VERSION: attack_log_correlator_lexical_v22
"""
attack_log_correlator.py

Correlate attack logs against heterogeneous Linux host logs.

Highlights:
- Reads JSON attack logs from nested directories
- Reads mixed log formats from nested host directories
- Guesses timestamps, hostnames, and candidate target hosts
- Supports per-host timezone and clock-skew correction via config file
- Produces global and per-target-host correlation JSON/CSV outputs
- Includes attack file, line number, and original attack line in outputs
- Provides a simple ncurses browser for stepping through correlations

The program uses only the Python standard library.
For binary systemd journal files it shells out to:
    journalctl --file ... -o short-iso-precise --no-pager
"""

from __future__ import annotations

import argparse
import csv
import curses
import dataclasses
import datetime as dt
import ipaddress
import json
import math
import re
import shlex
import subprocess
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
CURRENT_YEAR_FALLBACK = dt.datetime.now().year
MAX_TIME_DELTA_SECONDS = 0.3

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

COMMON_DIR_NAMES = {"logs", "log", "var", "tmp", "journal", "audit", "syslog", "host", "hosts"}
ATTACK_LOG_SUFFIXES = {".json", ".jsonl", ".attacklog"}
TEXT_EXTENSIONS = {".log", ".txt", ".json", ".jsonl", ".out", ".err", ".messages", ".syslog", ".csv"}
STOP_TOKENS = {
    "sudo", "nmap", "bash", "sh", "python", "python3", "nc", "curl", "wget", "ssh", "scp", "ftp",
    "http", "https", "tcp", "udp", "icmp", "reconnaissance", "discovery", "network", "scan", "ports",
}

LEXICAL_STOP_TOKENS = STOP_TOKENS | {
    "bin", "usr", "var", "tmp", "etc", "log", "logs", "root", "system", "service", "session",
    "shell", "command", "interactive", "background", "error", "metadata", "description",
    "the", "and", "for", "with", "from", "into", "that", "this", "false", "true", "null",
}


@dataclasses.dataclass
class Attack:
    attack_id: str
    timestamp: dt.datetime
    attack_type: str
    cmd: str
    source_file: str
    line_number: int
    raw: dict[str, Any]
    metadata: dict[str, Any]
    raw_line: str = ""
    target_hosts: list[str] = dataclasses.field(default_factory=list)
    target_ips: list[str] = dataclasses.field(default_factory=list)
    target_networks: list[str] = dataclasses.field(default_factory=list)
    target_tokens: list[str] = dataclasses.field(default_factory=list)
    attacker_host: str = "unknown-attacker"

@dataclasses.dataclass
class LogEvent:
    event_id: str
    timestamp: dt.datetime
    raw_timestamp: str
    host: str
    source_type: str
    file_path: str
    line_number: int
    message: str
    raw_line: str
    extra: dict[str, Any]
    candidate_hosts: list[str]
    candidate_ips: list[str]


@dataclasses.dataclass
class Correlation:
    correlation_id: str
    attack_id: str
    event_id: str
    attacker_host: str
    attack_time: dt.datetime
    event_time: dt.datetime
    delta_seconds: float
    abs_delta_seconds: float
    attack_file: str
    attack_line: int
    attack_raw_line: str
    event_file: str
    event_line: int
    host: str
    attack_type: str
    attack_cmd: str
    attack_targets: list[str]
    target_host_matches: list[str]
    event_message: str
    event_source_type: str
    score: float
    score_breakdown: dict[str, float]


@dataclasses.dataclass
class HostProfile:
    name: str
    timezone: str
    clock_skew_seconds: float = 0.0
    aliases: list[str] = dataclasses.field(default_factory=list)
    ip_addresses: list[str] = dataclasses.field(default_factory=list)
    path_hints: list[str] = dataclasses.field(default_factory=list)
    notes: str = ""


@dataclasses.dataclass
class ConfigBundle:
    default_timezone: str
    default_clock_skew_seconds: float
    hosts: dict[str, HostProfile]
    raw_config: dict[str, Any] = dataclasses.field(default_factory=dict)



def parse_utc_shift_hours(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def apply_timezone_shift(parsed: dt.datetime, shift_hours: float) -> dt.datetime:
    return parsed - dt.timedelta(hours=shift_hours)



def normalize_path_host_part(name: str) -> str:
    """
    Normalize directory/file name fragments when inferring hostnames from paths.
    """
    try:
        return sanitize_host_name(name)
    except Exception:
        name = str(name)
        name = re.sub(r"\.(log|txt|json|jsonl|journal|gz|xz|bz2)$", "", name, flags=re.I)
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-_.")
        return name or "unknown-host"


def guess_attacker_host_from_path(path: Path, root: Path) -> str:
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except Exception:
        rel_parts = path.parts
    for part in rel_parts[:-1]:
        lowered = part.lower()
        if lowered not in {"attacklogs", "attacks", "attacklog", "logs", "log"}:
            return normalize_path_host_part(part)
    if len(rel_parts) >= 2:
        return normalize_path_host_part(rel_parts[-2])
    return "unknown-attacker"

def parse_iso_datetime(value: str) -> Optional[dt.datetime]:
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def sanitize_host_name(name: str) -> str:
    name = re.sub(r"\.(log|txt|json|journal|gz|xz|bz2)$", "", name, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-_.")
    return name.lower() or "unknown-host"


IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
HOST_TOKEN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_.-]{2,}\b")


def safe_ip_network(token: str) -> Optional[ipaddress._BaseNetwork]:
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def safe_ip_address(token: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None


ndefault = object()


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


@dataclasses.dataclass
class ParsedTimestamp:
    timestamp_utc: dt.datetime
    raw_text: str
    naive: bool
    parser_name: str


class HostResolver:
    def __init__(self, config: ConfigBundle):
        self.config = config
        self.alias_to_host: dict[str, str] = {}
        self.ip_to_host: dict[str, str] = {}
        self.networks: list[tuple[ipaddress._BaseNetwork, str]] = []
        self.path_hints: list[tuple[str, str]] = []
        for host, profile in config.hosts.items():
            for alias in {host, *profile.aliases}:
                self.alias_to_host[sanitize_host_name(alias)] = host
            for ip_text in profile.ip_addresses:
                if "/" in ip_text:
                    net = safe_ip_network(ip_text)
                    if net:
                        self.networks.append((net, host))
                else:
                    addr = safe_ip_address(ip_text)
                    if addr:
                        self.ip_to_host[str(addr)] = host
            for hint in profile.path_hints:
                self.path_hints.append((sanitize_host_name(hint), host))

    def resolve_timezone(self, host: str) -> str:
        return self.config.hosts.get(host, HostProfile(host, self.config.default_timezone)).timezone

    def resolve_clock_skew(self, host: str) -> float:
        return self.config.hosts.get(host, HostProfile(host, self.config.default_timezone)).clock_skew_seconds

    def canonicalize_host(self, host: str) -> str:
        return self.alias_to_host.get(sanitize_host_name(host), sanitize_host_name(host))

    def host_for_ip(self, ip_text: str) -> Optional[str]:
        addr = safe_ip_address(ip_text)
        if not addr:
            net = safe_ip_network(ip_text)
            if net:
                for known_net, host in self.networks:
                    if net.subnet_of(known_net) or known_net.subnet_of(net) or net == known_net:
                        return host
            return None
        direct = self.ip_to_host.get(str(addr))
        if direct:
            return direct
        for net, host in self.networks:
            if addr in net:
                return host
        return None

    def host_from_path(self, path: Path, root: Path) -> Optional[str]:
        try:
            rel_parts = path.resolve().relative_to(root.resolve()).parts
        except Exception:
            rel_parts = path.parts
        candidates: list[str] = []
        for part in rel_parts[:-1]:
            part_s = sanitize_host_name(part)
            if part_s and part_s not in COMMON_DIR_NAMES:
                candidates.append(part_s)
        for cand in candidates:
            if cand in self.alias_to_host:
                return self.alias_to_host[cand]
        for cand in reversed(candidates):
            for hint, host in self.path_hints:
                if hint and hint in cand:
                    return host
        if candidates:
            return candidates[0]
        return sanitize_host_name(path.stem)

    def candidate_hosts_for_tokens(self, tokens: list[str], path: Optional[Path] = None, root: Optional[Path] = None) -> list[str]:
        found: list[str] = []
        for tok in tokens:
            st = sanitize_host_name(tok)
            host = self.alias_to_host.get(st)
            if host and host not in found:
                found.append(host)
            by_ip = self.host_for_ip(tok)
            if by_ip and by_ip not in found:
                found.append(by_ip)
        if path and root:
            path_host = self.host_from_path(path, root)
            if path_host and path_host not in found:
                found.append(path_host)
        return found


# ---------------------------- timestamp parsing ----------------------------

def parse_epoch_seconds(text: str) -> Optional[dt.datetime]:
    try:
        value = float(text)
    except ValueError:
        return None
    return dt.datetime.fromtimestamp(value, tz=UTC)


def parse_audit_timestamp(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.search(r"audit\((\d+(?:\.\d+)?):\d+\)", line)
    if not m:
        return None
    ts = parse_epoch_seconds(m.group(1))
    if not ts:
        return None
    return ParsedTimestamp(ts, m.group(1), False, "auditd-epoch")


def parse_syslog_timestamp(line: str, default_year: int) -> Optional[tuple[dt.datetime, str]]:
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})(?:\.(\d+))?\s+", line)
    if not m:
        return None
    month = MONTHS.get(m.group(1))
    if not month:
        return None
    day = int(m.group(2))
    hh, mm, ss = [int(x) for x in m.group(3).split(":")]
    micro = int((m.group(4) or "0")[:6].ljust(6, "0"))
    text = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    try:
        return dt.datetime(default_year, month, day, hh, mm, ss, micro), text
    except ValueError:
        return None


def parse_syslog_like(line: str, default_year: int) -> Optional[ParsedTimestamp]:
    res = parse_syslog_timestamp(line, default_year)
    if not res:
        return None
    naive_dt, text = res
    return ParsedTimestamp(naive_dt.replace(tzinfo=UTC), text, True, "syslog-like")


def parse_suricata_timestamp(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})\s+--\s+(\d{2}:\d{2}:\d{2})", line)
    if not m:
        return None
    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))
    if year < 100:
        year += 2000
    hh, mm, ss = [int(x) for x in m.group(4).split(":")]
    raw = m.group(0)
    try:
        naive_dt = dt.datetime(year, month, day, hh, mm, ss)
    except ValueError:
        return None
    return ParsedTimestamp(naive_dt.replace(tzinfo=UTC), raw, True, "suricata")


def parse_iso_prefix(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))\s+", line)
    if not m:
        return None
    parsed = parse_iso_datetime(m.group(1))
    if not parsed:
        return None
    return ParsedTimestamp(parsed, m.group(1), False, "iso-prefix")


def parse_json_line_timestamp(line: str, *_args) -> Optional[ParsedTimestamp]:
    if not line.lstrip().startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("time", "timestamp", "@timestamp", "ts", "datetime", "date"):
        value = obj.get(key)
        if isinstance(value, str):
            parsed = parse_iso_datetime(value)
            if parsed:
                return ParsedTimestamp(parsed, value, False, f"json:{key}")
    return None


def try_parse_line_timestamp(line: str, default_year: int) -> Optional[ParsedTimestamp]:
    for parser in (parse_json_line_timestamp, parse_audit_timestamp, parse_iso_prefix, parse_suricata_timestamp):
        parsed = parser(line, default_year)
        if parsed:
            return parsed
    parsed = parse_syslog_like(line, default_year)
    if parsed:
        return parsed
    return None


# ---------------------------- extraction helpers ---------------------------

def detect_source_type(path: Path, line: str) -> str:
    lower = path.name.lower()
    if lower.endswith(".journal"):
        return "journal-binary"
    if "audit" in lower or "audit(" in line:
        return "auditd"
    if line.lstrip().startswith("{") and '"time"' in line and '"log"' in line:
        return "docker-json"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}\s+--\s+\d{2}:\d{2}:\d{2}", line):
        return "suricata"
    if re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}", line):
        return "syslog-like"
    return "generic-text"


def guess_host_from_line(line: str) -> Optional[str]:
    m = re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+([A-Za-z0-9._-]+)\s+", line)
    if m:
        return sanitize_host_name(m.group(1))
    m = re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\s+([A-Za-z0-9._-]+)\s+", line)
    if m:
        return sanitize_host_name(m.group(1))
    return None


def extract_ips(text: str) -> list[str]:
    seen: list[str] = []
    for token in IP_RE.findall(text):
        if token not in seen:
            seen.append(token)
    return seen


def extract_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in HOST_TOKEN_RE.findall(text):
        st = sanitize_host_name(token)
        if st in STOP_TOKENS or st.isdigit() or len(st) < 3:
            continue
        if st not in seen:
            seen.append(st)
    return seen


def preview_message_from_line(line: str) -> str:
    text = line.rstrip("\n")
    if text.lstrip().startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for key in ("log", "message", "msg", "MESSAGE"):
                    if isinstance(obj.get(key), str):
                        return obj[key].rstrip()[:400]
        except Exception:
            pass
    return text[:400]


def normalize_event_time(parsed: ParsedTimestamp, host: str, resolver: HostResolver) -> dt.datetime:
    base = parsed.timestamp_utc
    if parsed.naive:
        zone = get_zone(resolver.resolve_timezone(host))
        naive_local = base.replace(tzinfo=None)
        base = naive_local.replace(tzinfo=zone).astimezone(UTC)
    skew = resolver.resolve_clock_skew(host)
    if skew:
        base = base - dt.timedelta(seconds=skew)
    return base.astimezone(UTC)



def extract_command_binaries(cmd: str) -> list[str]:
    try:
        parts = shlex.split(cmd)
    except Exception:
        parts = cmd.split()

    binaries: list[str] = []
    command_starters = {"sudo", "env", "nohup", "time", "command", "builtin", "exec", "doas"}
    shell_separators = {"|", "||", "&&", ";", "&"}
    expect_command = True

    for raw in parts:
        token = raw.strip()
        if not token:
            continue
        if token in shell_separators:
            expect_command = True
            continue
        if token in command_starters:
            expect_command = True
            continue
        if token.startswith("-"):
            continue
        if "=" in token and not token.startswith("/"):
            continue

        candidate = sanitize_host_name(Path(token).name if "/" in token else token)
        if not candidate or candidate.isdigit() or len(candidate) < 2:
            continue
        if safe_ip_address(candidate) or safe_ip_network(candidate):
            continue

        if expect_command:
            if candidate not in binaries:
                binaries.append(candidate)
            expect_command = False
            continue

        if candidate.endswith((".py", ".pl", ".sh")):
            stem = sanitize_host_name(Path(candidate).stem)
            if stem and stem not in binaries:
                binaries.append(stem)
        elif "/" in token:
            if candidate not in binaries:
                binaries.append(candidate)

    return binaries


def extract_attack_lexical_terms(attack: Attack) -> list[str]:
    terms: list[str] = []

    for binary in extract_command_binaries(attack.cmd):
        if binary not in terms and binary not in LEXICAL_STOP_TOKENS:
            terms.append(binary)

    sources = [attack.cmd, attack.raw_line]
    for value in attack.metadata.values():
        if isinstance(value, str):
            sources.append(value)

    for source in sources:
        for tok in extract_tokens(source):
            if tok in LEXICAL_STOP_TOKENS or tok.isdigit() or len(tok) < 3:
                continue
            if tok not in terms:
                terms.append(tok)

    return terms[:40]


def event_lexical_terms(event: LogEvent) -> set[str]:
    return set(
        extract_tokens(
            event.raw_line + " " + event.message + " " + " ".join(event.candidate_hosts) + " " + " ".join(event.candidate_ips)
        )
    )


def lexical_overlap_score(attack: Attack, event: LogEvent) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}
    score = 0.0

    event_text = (event.message + " " + event.raw_line).lower()
    event_terms = event_lexical_terms(event)

    binary_hits = []
    for binary in extract_command_binaries(attack.cmd):
        if binary and binary not in LEXICAL_STOP_TOKENS and binary in event_text:
            binary_hits.append(binary)
    if binary_hits:
        val = min(120.0, 40.0 + 25.0 * len(set(binary_hits)))
        breakdown["binary_name_match"] = val
        score += val

    lexical_terms = extract_attack_lexical_terms(attack)
    exact_hits = [tok for tok in lexical_terms if tok not in LEXICAL_STOP_TOKENS and tok in event_text]
    if exact_hits:
        val = min(80.0, 10.0 * len(set(exact_hits)))
        breakdown["lexical_exact_match"] = val
        score += val

    overlap_terms = sorted((set(lexical_terms) - set(exact_hits)) & event_terms)
    if overlap_terms:
        val = min(40.0, 6.0 * len(overlap_terms))
        breakdown["lexical_token_overlap"] = val
        score += val

    matched_total = len(set(binary_hits)) + len(set(exact_hits)) + len(set(overlap_terms))
    if matched_total >= 3:
        bonus = min(25.0, 5.0 * matched_total)
        breakdown["lexical_multi_signal_bonus"] = bonus
        score += bonus

    return score, breakdown


def extract_attack_targets(cmd: str, metadata: dict[str, Any], resolver: Optional[HostResolver] = None) -> tuple[list[str], list[str], list[str], list[str]]:
    target_ips: list[str] = []
    target_networks: list[str] = []
    target_tokens: list[str] = []
    target_hosts: list[str] = []

    for token in extract_ips(cmd):
        if "/" in token:
            if token not in target_networks:
                target_networks.append(token)
        else:
            if token not in target_ips:
                target_ips.append(token)
    text_blobs = [cmd]
    for value in metadata.values():
        if isinstance(value, str):
            text_blobs.append(value)
    for blob in text_blobs:
        for tok in extract_tokens(blob):
            if tok not in target_tokens:
                target_tokens.append(tok)
    if resolver:
        for ip in target_ips + target_networks:
            host = resolver.host_for_ip(ip)
            if host and host not in target_hosts:
                target_hosts.append(host)
        for tok in target_tokens:
            host = resolver.alias_to_host.get(tok)
            if host and host not in target_hosts:
                target_hosts.append(host)
    return target_ips, target_networks, target_tokens, target_hosts


def content_overlap_score(attack: Attack, event: LogEvent) -> tuple[float, dict[str, float], list[str]]:
    breakdown: dict[str, float] = {}
    matched_hosts: list[str] = []
    score = 0.0

    lexical_score, lexical_breakdown = lexical_overlap_score(attack, event)
    score += lexical_score
    breakdown.update(lexical_breakdown)

    if attack.target_hosts:
        if event.host in attack.target_hosts:
            breakdown["target_host_exact"] = 45.0
            score += 45.0
            matched_hosts.append(event.host)
        overlap = sorted(set(attack.target_hosts) & set(event.candidate_hosts))
        if overlap:
            breakdown["target_host_candidate"] = 25.0
            score += 25.0
            matched_hosts.extend(h for h in overlap if h not in matched_hosts)

    ip_hits = 0
    for ip_text in attack.target_ips:
        if ip_text in event.raw_line or ip_text in event.message:
            ip_hits += 1
    if ip_hits:
        val = min(50.0, 20.0 + 10.0 * ip_hits)
        breakdown["ip_literal_match"] = val
        score += val

    network_hits = 0
    for net_text in attack.target_networks:
        net = safe_ip_network(net_text)
        if not net:
            continue
        for ip_text in event.candidate_ips:
            addr = safe_ip_address(ip_text.split("/")[0])
            if addr and addr in net:
                network_hits += 1
                break
    if network_hits:
        val = min(35.0, 15.0 + 10.0 * network_hits)
        breakdown["network_match"] = val
        score += val

    if attack.attack_type and attack.attack_type.lower() in event.source_type.lower():
        breakdown["source_type_hint"] = 6.0
        score += 6.0

    return score, breakdown, matched_hosts

def time_score(delta_seconds: float, window_before: float, window_after: float) -> tuple[float, dict[str, float]]:
    max_window = max(window_before, window_after, 1.0)
    decay = max(0.0, 1.0 - min(abs(delta_seconds), max_window) / max_window)
    base = 40.0 * decay
    breakdown = {"time_proximity": base}
    if 0 <= delta_seconds <= min(10.0, window_after):
        breakdown["post_attack_bonus"] = 12.0
        base += 12.0
    elif -5.0 <= delta_seconds < 0:
        breakdown["pre_attack_context_bonus"] = 4.0
        base += 4.0
    return base, breakdown


def relevance_threshold(correlation: Correlation) -> bool:
    breakdown_keys = set(correlation.score_breakdown)

    if "binary_name_match" in breakdown_keys:
        return True
    if "lexical_exact_match" in breakdown_keys and correlation.abs_delta_seconds <= MAX_TIME_DELTA_SECONDS:
        return True
    if correlation.score >= 60.0:
        return True
    if correlation.score >= 45.0 and correlation.target_host_matches:
        return True
    if correlation.score >= 40.0 and any(k in breakdown_keys for k in ("ip_literal_match", "network_match")):
        return True
    return False


# -------------------------- config loading/building -------------------------

def discover_attack_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in ATTACK_LOG_SUFFIXES or "attack" in path.name.lower()):
            found.append(path)
    return sorted(found)


def looks_like_log_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS or path.suffix.lower() == ".journal":
        return True
    name = path.name.lower()
    keywords = ("syslog", "messages", "audit", "suricata", "eve", "journal", "docker", "container")
    return any(k in name for k in keywords)


def discover_log_files(root: Path, attack_root: Optional[Path]) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if attack_root and attack_root.resolve() in path.resolve().parents:
            continue
        if looks_like_log_file(path):
            found.append(path)
    return sorted(found)


def load_config(config_path: Optional[Path], discovered_hosts: dict[str, HostProfile], default_timezone: str) -> ConfigBundle:
    base_hosts = {name: dataclasses.replace(profile) for name, profile in discovered_hosts.items()}
    config = ConfigBundle(default_timezone=default_timezone, default_clock_skew_seconds=0.0, hosts=base_hosts, raw_config={})
    if not config_path or not config_path.exists():
        return config
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return config
    config.raw_config = dict(data)
    config.default_timezone = str(data.get("default_timezone", config.default_timezone))
    config.default_clock_skew_seconds = float(data.get("default_clock_skew_seconds", 0.0) or 0.0)
    hosts = data.get("hosts", {})
    if isinstance(hosts, dict):
        for host_name, host_cfg in hosts.items():
            if not isinstance(host_cfg, dict):
                continue
            key = sanitize_host_name(host_name)
            existing = config.hosts.get(key, HostProfile(key, config.default_timezone))
            existing.timezone = str(host_cfg.get("timezone", existing.timezone or config.default_timezone))
            existing.clock_skew_seconds = float(host_cfg.get("clock_skew_seconds", existing.clock_skew_seconds or 0.0) or 0.0)
            existing.aliases = sorted(set(existing.aliases + [sanitize_host_name(x) for x in host_cfg.get("aliases", []) if str(x).strip()]))
            existing.ip_addresses = sorted(set(existing.ip_addresses + [str(x).strip() for x in host_cfg.get("ip_addresses", []) if str(x).strip()]))
            existing.path_hints = sorted(set(existing.path_hints + [sanitize_host_name(x) for x in host_cfg.get("path_hints", []) if str(x).strip()]))
            existing.notes = str(host_cfg.get("notes", existing.notes))
            config.hosts[key] = existing
    for host, profile in config.hosts.items():
        if not profile.timezone:
            profile.timezone = config.default_timezone
    return config


def write_generated_config(path: Path, config: ConfigBundle) -> None:
    payload = {
        "default_timezone": config.default_timezone,
        "default_clock_skew_seconds": config.default_clock_skew_seconds,
        "hosts": {
            host: {
                "timezone": profile.timezone,
                "clock_skew_seconds": profile.clock_skew_seconds,
                "aliases": profile.aliases,
                "ip_addresses": profile.ip_addresses,
                "path_hints": profile.path_hints,
                "notes": profile.notes,
            }
            for host, profile in sorted(config.hosts.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def discover_hosts_from_logs(log_root: Path, attack_root: Optional[Path], default_timezone: str) -> dict[str, HostProfile]:
    hosts: dict[str, HostProfile] = {}
    for path in discover_log_files(log_root, attack_root):
        host = sanitize_host_name(path.parent.name)
        if host in COMMON_DIR_NAMES:
            host = sanitize_host_name(path.stem)
        if not host or host == "unknown-host":
            continue
        profile = hosts.setdefault(host, HostProfile(name=host, timezone=default_timezone))
        path_hint = sanitize_host_name(path.parent.name)
        if path_hint and path_hint not in profile.path_hints:
            profile.path_hints.append(path_hint)
        stem = sanitize_host_name(path.stem)
        if stem and stem not in profile.path_hints:
            profile.path_hints.append(stem)
    return hosts


# ------------------------------- loading -----------------------------------

def load_attack_file(path: Path, resolver: HostResolver, attack_root: Optional[Path] = None, config: Optional[Any] = None) -> list[Attack]:
    attacks: list[Attack] = []
    attacker_host = guess_attacker_host_from_path(path, attack_root or path.parent)

    raw_cfg: dict[str, Any] = {}
    if isinstance(config, dict):
        raw_cfg = config
    elif hasattr(config, "raw_config") and isinstance(getattr(config, "raw_config"), dict):
        raw_cfg = getattr(config, "raw_config")

    attacker_cfg = (raw_cfg.get("attacker_hosts", {}) or {}).get(attacker_host, {})
    attacker_shift = parse_utc_shift_hours(
        attacker_cfg.get("utc_offset_hours", raw_cfg.get("default_utc_offset_hours", 0))
    )

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            text_line = line.strip()
            if not text_line:
                continue
            try:
                obj = json.loads(text_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            ts = obj.get("start-datetime")
            if not isinstance(ts, str):
                continue
            parsed = parse_iso_datetime(ts)
            if not parsed:
                continue
            parsed = apply_timezone_shift(parsed, attacker_shift)
            attack_type = str(obj.get("type", "unknown"))
            cmd = str(obj.get("cmd", ""))
            metadata = {}
            params = obj.get("parameters")
            if isinstance(params, dict):
                meta = params.get("metadata")
                if isinstance(meta, dict):
                    metadata = meta
            target_ips, target_networks, target_tokens, target_hosts = extract_attack_targets(cmd, metadata, resolver)
            attack_id = f"{path}:{line_number}"
            attacks.append(
                Attack(
                    attack_id=attack_id,
                    timestamp=parsed,
                    attack_type=attack_type,
                    cmd=cmd,
                    source_file=str(path),
                    line_number=line_number,
                    raw=obj,
                    metadata=metadata,
                    raw_line=line.rstrip("\n"),
                    target_hosts=target_hosts,
                    target_ips=target_ips,
                    target_networks=target_networks,
                    target_tokens=target_tokens,
                    attacker_host=attacker_host,
                )
            )
    return attacks


def run_journalctl_export(path: Path) -> list[str]:
    cmd = ["journalctl", f"--file={path}", "-o", "short-iso-precise", "--no-pager"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "journalctl failed")
    return result.stdout.splitlines()


def load_log_file(path: Path, root: Path, default_year: int, resolver: HostResolver) -> list[LogEvent]:
    events: list[LogEvent] = []
    path_host = resolver.host_from_path(path, root) or sanitize_host_name(path.parent.name)

    def convert_line(line: str, line_number: int, source_type_override: Optional[str] = None) -> Optional[LogEvent]:
        parsed = try_parse_line_timestamp(line, default_year)
        if not parsed:
            return None
        line_host = guess_host_from_line(line)
        host = resolver.canonicalize_host(line_host or path_host)
        normalized_ts = normalize_event_time(parsed, host, resolver)
        source_type = source_type_override or detect_source_type(path, line)
        candidate_ips = extract_ips(line)
        candidate_tokens = extract_tokens(line)
        candidate_hosts = resolver.candidate_hosts_for_tokens(candidate_tokens + candidate_ips, path=path, root=root)
        if host not in candidate_hosts:
            candidate_hosts.insert(0, host)
        return LogEvent(
            event_id=f"{path}:{line_number}",
            timestamp=normalized_ts,
            raw_timestamp=parsed.raw_text,
            host=host,
            source_type=source_type,
            file_path=str(path),
            line_number=line_number,
            message=preview_message_from_line(line),
            raw_line=line.rstrip("\n"),
            extra={"timestamp_parser": parsed.parser_name},
            candidate_hosts=candidate_hosts,
            candidate_ips=candidate_ips,
        )

    if path.suffix.lower() == ".journal":
        try:
            lines = run_journalctl_export(path)
        except Exception:
            return events
        for line_number, line in enumerate(lines, start=1):
            ev = convert_line(line, line_number, "journalctl-export")
            if ev:
                events.append(ev)
        return events

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            ev = convert_line(line, line_number)
            if ev:
                events.append(ev)
    return events


def load_all_attacks(attack_root: Path, resolver: HostResolver, config: Optional[dict[str, Any]] = None) -> list[Attack]:
    attacks: list[Attack] = []
    for path in discover_attack_files(attack_root):
        try:
            attacks.extend(load_attack_file(path, resolver, attack_root=attack_root, config=config))
        except Exception as exc:
            print(f"[warn] failed to read attack log: {path}: {exc}", file=sys.stderr)
    return sorted(attacks, key=lambda x: x.timestamp)


def load_all_events(log_root: Path, attack_root: Optional[Path], default_year: int, resolver: HostResolver) -> list[LogEvent]:
    events: list[LogEvent] = []
    for path in discover_log_files(log_root, attack_root):
        try:
            events.extend(load_log_file(path, log_root, default_year, resolver))
        except Exception:
            print(f"[warn] failed to read log file: {path}", file=sys.stderr)
    return sorted(events, key=lambda x: x.timestamp)


# ------------------------------ correlation --------------------------------

def correlate(attacks: list[Attack], events: list[LogEvent], window_before: float, window_after: float, max_per_attack: int) -> list[Correlation]:
    correlations: list[Correlation] = []
    events_sorted = sorted(events, key=lambda e: e.timestamp)
    start_idx = 0

    for attack in sorted(attacks, key=lambda a: a.timestamp):
        lower = attack.timestamp - dt.timedelta(seconds=window_before)
        upper = attack.timestamp + dt.timedelta(seconds=window_after)

        while start_idx < len(events_sorted) and events_sorted[start_idx].timestamp < lower:
            start_idx += 1

        matches: list[Correlation] = []
        idx = start_idx

        while idx < len(events_sorted) and events_sorted[idx].timestamp <= upper:
            event = events_sorted[idx]
            delta = (event.timestamp - attack.timestamp).total_seconds()
            abs_delta = abs(delta)

            if abs_delta > MAX_TIME_DELTA_SECONDS:
                idx += 1
                continue

            t_score, t_breakdown = time_score(delta, window_before, window_after)
            c_score, c_breakdown, matched_hosts = content_overlap_score(attack, event)
            weighted_time_score = t_score
            weighted_lexical_score = c_score * 2.0
            total = weighted_time_score + weighted_lexical_score
            breakdown = {
                **t_breakdown,
                **c_breakdown,
                "weighted_time_score": weighted_time_score,
                "weighted_lexical_score": weighted_lexical_score,
            }

            corr = Correlation(
                correlation_id=f"{attack.attack_id}|{event.event_id}",
                attack_id=attack.attack_id,
                event_id=event.event_id,
                attacker_host=attack.attacker_host,
                attack_time=attack.timestamp,
                event_time=event.timestamp,
                delta_seconds=delta,
                abs_delta_seconds=abs_delta,
                attack_file=attack.source_file,
                attack_line=attack.line_number,
                attack_raw_line=attack.raw_line,
                event_file=str(event.file_path),
                event_line=event.line_number,
                host=event.host,
                attack_type=attack.attack_type,
                attack_cmd=attack.cmd,
                attack_targets=attack.target_hosts + attack.target_ips + attack.target_networks + attack.target_tokens,
                target_host_matches=matched_hosts,
                event_message=event.message,
                event_source_type=event.source_type,
                score=total,
                score_breakdown=breakdown,
            )
            if relevance_threshold(corr):
                matches.append(corr)
            idx += 1

        matches.sort(key=lambda c: (-c.score, c.abs_delta_seconds, c.host, c.event_file, c.event_line))
        correlations.extend(matches[:max_per_attack])

    correlations.sort(key=lambda c: (c.attack_time, -c.score, c.abs_delta_seconds))
    return correlations

def correlations_by_host(correlations: list[Correlation]) -> dict[str, list[Correlation]]:
    grouped: dict[str, list[Correlation]] = defaultdict(list)
    for corr in correlations:
        if corr.host:
            grouped[corr.host].append(corr)
        for host in corr.target_host_matches:
            if corr not in grouped[host]:
                grouped[host].append(corr)
    for host in grouped:
        grouped[host].sort(key=lambda c: (c.attack_time, -c.score, c.abs_delta_seconds))
    return dict(grouped)


# ------------------------------- exporting ---------------------------------

def attack_summary_row(attack: Attack) -> dict[str, Any]:
    return {
        "attack_id": attack.attack_id,
        "timestamp": attack.timestamp.isoformat(),
        "type": attack.attack_type,
        "cmd": attack.cmd,
        "source_file": attack.source_file,
        "line_number": attack.line_number,
        "raw_line": attack.raw_line,
        "metadata": attack.metadata,
        "target_ips": attack.target_ips,
        "target_networks": attack.target_networks,
        "target_tokens": attack.target_tokens,
        "target_hosts": attack.target_hosts,
    }


def event_summary_row(event: LogEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp.isoformat(),
        "raw_timestamp": event.raw_timestamp,
        "host": event.host,
        "source_type": event.source_type,
        "file_path": event.file_path,
        "line_number": event.line_number,
        "message": event.message,
        "candidate_hosts": event.candidate_hosts,
        "candidate_ips": event.candidate_ips,
        "extra": event.extra,
    }


def correlation_row(c: Correlation) -> dict[str, Any]:
    return {
        "correlation_id": c.correlation_id,
        "attack_id": c.attack_id,
        "event_id": c.event_id,
        "attacker_host": getattr(c, "attacker_host", ""),
        "attack_time": c.attack_time.isoformat(),
        "event_time": c.event_time.isoformat(),
        "delta_seconds": c.delta_seconds,
        "abs_delta_seconds": c.abs_delta_seconds,
        "host": c.host,
        "attack_type": c.attack_type,
        "attack_cmd": c.attack_cmd,
        "attacker_host": getattr(c, "attacker_host", ""),
        "attack_targets": c.attack_targets,
        "target_host_matches": c.target_host_matches,
        "event_source_type": c.event_source_type,
        "event_message": c.event_message,
        "score": c.score,
        "score_breakdown": c.score_breakdown,
        "attack_file": c.attack_file,
        "attack_line": c.attack_line,
        "attack_raw_line": c.attack_raw_line,
        "event_file": c.event_file,
        "event_line": c.event_line,
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_correlation_csv(path: Path, correlations: list[Correlation]) -> None:
    fieldnames = [
        "correlation_id", "attack_id", "event_id", "attacker_host", "attack_time", "event_time", "delta_seconds",
        "abs_delta_seconds", "host", "attack_type", "attack_cmd", "attack_targets", "target_host_matches",
        "event_source_type", "event_message", "score", "score_breakdown", "attack_file", "attack_line",
        "attack_raw_line", "event_file", "event_line",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in correlations:
            try:
                row = correlation_row(c)
                row["attack_targets"] = ";".join(str(x) for x in row.get("attack_targets", []))
                row["target_host_matches"] = ";".join(str(x) for x in row.get("target_host_matches", []))
                row["score_breakdown"] = json.dumps(row.get("score_breakdown", {}), ensure_ascii=False, sort_keys=True)
                row["attack_raw_line"] = str(row.get("attack_raw_line", "")).replace(chr(0), "")
                row["event_message"] = str(row.get("event_message", "")).replace(chr(0), "")
                writer.writerow(row)
            except Exception as exc:
                print(f"[warn] failed to write correlation row for {getattr(c, 'correlation_id', '<unknown>')}: {exc}", file=sys.stderr)
                continue


def write_human_summary(path: Path, attacks: list[Attack], correlations: list[Correlation]) -> None:
    by_attack: dict[str, list[Correlation]] = defaultdict(list)
    for c in correlations:
        by_attack[c.attack_id].append(c)

    for attack_id in by_attack:
        by_attack[attack_id].sort(key=lambda c: (-c.score, c.abs_delta_seconds, c.host, c.event_file, c.event_line))

    with path.open("w", encoding="utf-8") as fh:
        for idx, attack in enumerate(sorted(attacks, key=lambda a: a.timestamp), start=1):
            fh.write(f"Attack step {idx}\n")
            fh.write(f"  Time:   {attack.timestamp.isoformat()}\n")
            fh.write(f"  Type:   {attack.attack_type}\n")
            fh.write(f"  Source: {attack.source_file}:{attack.line_number}\n")
            fh.write(f"  Attacker: {attack.attacker_host}\n")
            fh.write(f"  Cmd:    {attack.cmd}\n")
            fh.write(f"  Attack: {attack.raw_line.replace(chr(0), '').strip()}\n\n")

            rows = by_attack.get(attack.attack_id, [])
            if not rows:
                fh.write("  No correlated host log entries found.\n\n")
                fh.write("-" * 100 + "\n\n")
                continue

            for c in rows:
                event_msg = (c.event_message or "").replace(chr(0), "").replace("\n", " ").replace("\r", " ").strip()
                fh.write(
                    f"  Host={c.host}  File={c.event_file}  Line={c.event_line}  "
                    f"Delta={c.delta_seconds:.3f}s  Score={c.score:.2f}\n"
                )
                fh.write(f"    Log: {event_msg}\n")
            fh.write("\n" + "-" * 100 + "\n\n")
def export_outputs(out_dir: Path, config: ConfigBundle, attacks: list[Attack], events: list[LogEvent], correlations: list[Correlation]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_generated_config(out_dir / "host_config.generated.json", config)
    write_json(
        out_dir / "correlations.json",
        {
            "summary": {
                "attack_count": len(attacks),
                "event_count": len(events),
                "correlation_count": len(correlations),
                "created_at": dt.datetime.now(tz=UTC).isoformat(),
            },
            "attacks": [attack_summary_row(a) for a in attacks],
            "events": [event_summary_row(e) for e in events],
            "correlations": [correlation_row(c) for c in correlations],
        },
    )
    write_correlation_csv(out_dir / "correlations.csv", correlations)
    write_human_summary(out_dir / "correlations_human.txt", attacks, correlations)

    grouped = correlations_by_host(correlations)
    per_host_dir = out_dir / "per_host"
    per_host_dir.mkdir(exist_ok=True)
    host_summary = {}

    for host, rows in grouped.items():
        host_dir = per_host_dir / host
        host_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            host_dir / "correlations.json",
            {
                "host": host,
                "correlation_count": len(rows),
                "correlations": [correlation_row(c) for c in rows],
            },
        )
        write_correlation_csv(host_dir / "correlations.csv", rows)
        write_human_summary(host_dir / "correlations_human.txt", attacks, rows)
        host_summary[host] = {"correlation_count": len(rows)}

    write_json(
        out_dir / "summary.json",
        {
            "attacks": len(attacks),
            "events": len(events),
            "correlations": len(correlations),
            "per_host": host_summary,
            "created_at": dt.datetime.now(tz=UTC).isoformat(),
            "max_time_delta_seconds": MAX_TIME_DELTA_SECONDS,
        },
    )





def attack_from_summary_row(row: dict[str, Any]) -> Attack:
    timestamp = parse_iso_datetime(str(row.get("timestamp", row.get("attack_time", "")))) or dt.datetime.fromtimestamp(0, tz=UTC)
    target_hosts = row.get("target_hosts", [])
    target_ips = row.get("target_ips", [])
    target_networks = row.get("target_networks", [])
    target_tokens = row.get("target_tokens", [])
    return Attack(
        attack_id=str(row.get("attack_id", "")),
        timestamp=timestamp,
        attack_type=str(row.get("type", row.get("attack_type", "unknown"))),
        cmd=str(row.get("cmd", row.get("attack_cmd", ""))),
        source_file=str(row.get("source_file", row.get("attack_file", ""))),
        line_number=int(row.get("line_number", row.get("attack_line", 0)) or 0),
        raw={},
        metadata=row.get("metadata", {}) if isinstance(row.get("metadata", {}), dict) else {},
        raw_line=str(row.get("raw_line", row.get("attack_raw_line", ""))),
        target_hosts=target_hosts if isinstance(target_hosts, list) else [],
        target_ips=target_ips if isinstance(target_ips, list) else [],
        target_networks=target_networks if isinstance(target_networks, list) else [],
        target_tokens=target_tokens if isinstance(target_tokens, list) else [],
        attacker_host=str(row.get("attacker_host", "unknown-attacker")),
    )


def correlation_from_summary_row(row: dict[str, Any]) -> Correlation:
    attack_time = parse_iso_datetime(str(row.get("attack_time", ""))) or dt.datetime.fromtimestamp(0, tz=UTC)
    event_time = parse_iso_datetime(str(row.get("event_time", ""))) or dt.datetime.fromtimestamp(0, tz=UTC)
    breakdown = row.get("score_breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    attack_targets = row.get("attack_targets", [])
    if not isinstance(attack_targets, list):
        attack_targets = [str(attack_targets)] if attack_targets else []
    target_host_matches = row.get("target_host_matches", [])
    if not isinstance(target_host_matches, list):
        target_host_matches = [str(target_host_matches)] if target_host_matches else []
    delta = float(row.get("delta_seconds", 0.0) or 0.0)
    return Correlation(
        correlation_id=str(row.get("correlation_id", "")),
        attack_id=str(row.get("attack_id", "")),
        event_id=str(row.get("event_id", "")),
        attacker_host=str(row.get("attacker_host", "unknown-attacker")),
        attack_time=attack_time,
        event_time=event_time,
        delta_seconds=delta,
        abs_delta_seconds=float(row.get("abs_delta_seconds", abs(delta)) or abs(delta)),
        attack_file=str(row.get("attack_file", "")),
        attack_line=int(row.get("attack_line", 0) or 0),
        attack_raw_line=str(row.get("attack_raw_line", "")),
        event_file=str(row.get("event_file", "")),
        event_line=int(row.get("event_line", 0) or 0),
        host=str(row.get("host", "unknown-host")),
        attack_type=str(row.get("attack_type", "unknown")),
        attack_cmd=str(row.get("attack_cmd", "")),
        attack_targets=attack_targets,
        target_host_matches=target_host_matches,
        event_message=str(row.get("event_message", "")),
        event_source_type=str(row.get("event_source_type", "")),
        score=float(row.get("score", 0.0) or 0.0),
        score_breakdown=breakdown,
    )


def load_output_for_browsing(out_dir: Path) -> tuple[list[Attack], list[Correlation]]:
    data_path = out_dir / "correlations.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Missing saved output file: {data_path}")
    with data_path.open("r", encoding="utf-8", errors="replace") as fh:
        payload = json.load(fh)
    attack_rows = payload.get("attacks", [])
    corr_rows = payload.get("correlations", [])
    if not isinstance(attack_rows, list):
        attack_rows = []
    if not isinstance(corr_rows, list):
        corr_rows = []
    attacks = [attack_from_summary_row(r) for r in attack_rows if isinstance(r, dict)]
    correlations = [correlation_from_summary_row(r) for r in corr_rows if isinstance(r, dict)]
    if not attacks:
        seen: dict[str, Attack] = {}
        for c in correlations:
            if c.attack_id in seen:
                continue
            seen[c.attack_id] = Attack(
                attack_id=c.attack_id,
                timestamp=c.attack_time,
                attack_type=c.attack_type,
                cmd=c.attack_cmd,
                source_file=c.attack_file,
                line_number=c.attack_line,
                raw={},
                metadata={},
                raw_line=c.attack_raw_line,
                target_hosts=[],
                target_ips=[],
                target_networks=[],
                target_tokens=[],
                attacker_host=c.attacker_host,
            )
        attacks = list(seen.values())
    return attacks, correlations

# ---------------------------------- tui ------------------------------------

def read_context_lines(path: str, line_number: int, radius: int = 3) -> list[str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return [f"[missing file] {path}"]
    start = max(1, line_number - radius)
    end = line_number + radius
    out: list[str] = []

    def _sanitize_preview_text(value: str) -> str:
        value = str(value).replace(chr(0), "")
        cleaned = []
        for ch in value:
            code = ord(ch)
            if ch == "\t" or code >= 32:
                cleaned.append(ch)
            else:
                cleaned.append("?")
        return "".join(cleaned)

    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for idx, line in enumerate(fh, start=1):
                if idx < start:
                    continue
                if idx > end:
                    break
                prefix = ">" if idx == line_number else " "
                out.append(f"{prefix}{idx:6d} {_sanitize_preview_text(line.rstrip())}")
    except Exception as exc:
        out.append(f"[unable to preview] {exc}")
    return out



def _ui_sanitize(value: str) -> str:
    value = str(value).replace(chr(0), "")
    cleaned = []
    for ch in value:
        code = ord(ch)
        if ch == "\t" or code >= 32:
            cleaned.append(ch)
        else:
            cleaned.append("?")
    return "".join(cleaned)


def _preview_keywords(corr: Optional[Correlation]) -> list[str]:
    if not corr:
        return []
    out: list[str] = []
    for token in [corr.attack_type, corr.attack_cmd]:
        if token:
            for piece in extract_tokens(str(token)):
                if len(piece) >= 3 and piece not in STOP_TOKENS and piece not in out:
                    out.append(piece)
    for token in getattr(corr, "attack_targets", []) or []:
        t = str(token).strip()
        if t and t not in out:
            out.append(t)
    for token in getattr(corr, "target_host_matches", []) or []:
        t = str(token).strip()
        if t and t not in out:
            out.append(t)
    return out[:50]


def _render_highlighted_line(win, y: int, x: int, width: int, line: str, keywords: list[str], highlight_attr: int) -> None:
    safe = _ui_sanitize(line)
    lowered = safe.lower()
    pos = 0
    col = x
    remaining = width
    ordered = sorted([k for k in keywords if k], key=len, reverse=True)

    while pos < len(safe) and remaining > 0:
        match_start = None
        match_end = None
        for kw in ordered:
            kw_l = kw.lower()
            idx = lowered.find(kw_l, pos)
            if idx != -1 and (match_start is None or idx < match_start):
                match_start = idx
                match_end = idx + len(kw)
        if match_start is None:
            chunk = safe[pos:pos + remaining]
            win.addnstr(y, col, chunk, remaining)
            break
        if match_start > pos:
            chunk = safe[pos:match_start]
            draw = chunk[:remaining]
            win.addnstr(y, col, draw, remaining)
            used = len(draw)
            col += used
            remaining -= used
            pos += used
            if remaining <= 0:
                break
        chunk = safe[match_start:match_end]
        draw = chunk[:remaining]
        win.addnstr(y, col, draw, remaining, highlight_attr)
        used = len(draw)
        col += used
        remaining -= used
        pos = match_start + used



def correlation_lexical_score(corr: Correlation) -> float:
    keys = (
        "binary_name_match",
        "lexical_exact_match",
        "lexical_token_overlap",
        "lexical_multi_signal_bonus",
    )
    total = 0.0
    for key in keys:
        try:
            total += float((corr.score_breakdown or {}).get(key, 0.0))
        except Exception:
            pass
    return total


def average_lexical_score(correlations: list[Correlation]) -> float:
    if not correlations:
        return 0.0
    vals = [correlation_lexical_score(c) for c in correlations]
    return sum(vals) / len(vals) if vals else 0.0


def build_preview_lines(corr: Optional[Correlation], collapsed: bool = True) -> list[str]:
    if not corr:
        return ["No selection"]

    lines: list[str] = [
        f"Host:  {corr.host}",
        f"Attacker: {getattr(corr, 'attacker_host', 'unknown-attacker')}",
        f"Time:  {corr.event_time.isoformat()}",
        f"Delta: {corr.delta_seconds:.3f}s    Score: {corr.score:.2f}",
        f"Command: {corr.attack_cmd}",
        f"File:  {corr.event_file}:{corr.event_line}",
    ]

    breakdown = getattr(corr, "score_breakdown", {}) or {}
    if breakdown:
        lines.append("Why this matched:")
        items = sorted(breakdown.items(), key=lambda kv: (-kv[1], kv[0]))
        if collapsed:
            items = items[:5]
        for key, value in items:
            pretty_key = key.replace("_", " ")
            lines.append(f"  - {pretty_key}: {value:.2f}")
        if collapsed and len(breakdown) > 5:
            lines.append(f"  ... {len(breakdown) - 5} more scoring details hidden")

    lines.append("Matched log line:")
    focus_line = read_context_lines(corr.event_file, corr.event_line, radius=0)
    lines.extend(focus_line or ["[missing matched line]"])
    lines.append("------------------")
    lines.append("Context:")
    context = read_context_lines(corr.event_file, corr.event_line, radius=2 if collapsed else 6)
    if context:
        if focus_line:
            context = [x for x in context if x not in focus_line]
        lines.extend(context)

    if not collapsed:
        lines.append("Event:")
        lines.append(_ui_sanitize(corr.event_message))
        lines.append("Scoring breakdown:")
        pretty = pp.pformat(breakdown, width=88, compact=False, sort_dicts=True)
        lines.extend(_ui_sanitize(pretty).splitlines())

    return lines




HILITE_GREEN_PATTERNS = [
    r'\bname="[^"]+"',
    r"\bcomm=[^\s]+",
    r"\bexe=[^\s]+",
    r"\bcmd=[^\s].*$",
    r"\b(?:sudo|curl|wget|nc|ncat|netcat|nmap|ssh|scp|ftp|python|python3|bash|sh|zsh|perl|ruby|php|busybox|systemctl|iptables|ip|ss|netstat|tcpdump|socat)\b",
    r"\b(?:/[A-Za-z0-9._-]+)+\b",
    r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b",
]


def _collect_semantic_spans(line: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    safe = _ui_sanitize(line)

    for pat in HILITE_GREEN_PATTERNS:
        for m in re.finditer(pat, safe):
            spans.append((m.start(), m.end(), "blue"))

    for m in re.finditer(r'\b(?:error|failed|failure|denied|invalid|refused|blocked|drop(?:ped)?|alert)\b', safe, flags=re.I):
        spans.append((m.start(), m.end(), "bold"))

    return spans


def _merge_spans(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    if not spans:
        return []
    priority = {"green": 2, "blue": 1, "bold": 0}
    spans = [s for s in spans if s[0] < s[1]]
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0]), -priority.get(x[2], 0)))

    merged: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for s, e, kind in spans:
        cur = s
        while cur < e:
            blocked = False
            for os, oe in occupied:
                if os <= cur < oe:
                    cur = oe
                    blocked = True
                    break
            if blocked:
                continue
            next_block = e
            for os, oe in occupied:
                if cur < os < next_block:
                    next_block = os
            if cur < next_block:
                merged.append((cur, next_block, kind))
                occupied.append((cur, next_block))
            cur = next_block
    merged.sort(key=lambda x: x[0])
    return merged


def _render_semantic_highlighted_line(win, y: int, x: int, width: int, line: str, keywords: list[str], blue_attr: int, green_attr: int, bold_attr: int) -> None:
    safe = _ui_sanitize(line)
    spans: list[tuple[int, int, str]] = []

    lowered = safe.lower()
    ordered = sorted([k for k in keywords if k], key=len, reverse=True)
    for kw in ordered:
        kw_l = kw.lower()
        pos = 0
        while pos < len(safe):
            idx = lowered.find(kw_l, pos)
            if idx == -1:
                break
            end = idx + len(kw)
            spans.append((idx, end, "green"))
            pos = end

    spans.extend(_collect_semantic_spans(safe))
    spans = _merge_spans(spans)

    cur = 0
    col = x
    remaining = width
    for s, e, kind in spans:
        if remaining <= 0:
            break
        if s > cur:
            chunk = safe[cur:s]
            draw = chunk[:remaining]
            win.addnstr(y, col, draw, remaining)
            col += len(draw)
            remaining -= len(draw)
            cur = s
            if remaining <= 0:
                break
        if e > cur:
            chunk = safe[cur:e]
            draw = chunk[:remaining]
            attr = green_attr if kind == "green" else blue_attr if kind == "blue" else bold_attr
            win.addnstr(y, col, draw, remaining, attr)
            col += len(draw)
            remaining -= len(draw)
            cur += len(draw)

    if remaining > 0 and cur < len(safe):
        chunk = safe[cur:cur + remaining]
        win.addnstr(y, col, chunk, remaining)

class CorrelationBrowser:
    PANE_ATTACKS = 0
    PANE_CORRELATIONS = 1
    PANE_PREVIEW = 2

    def __init__(self, attacks: list[Attack], correlations: list[Correlation]):
        self.attacks = sorted(attacks, key=lambda x: x.timestamp)
        self.by_attack: dict[str, list[Correlation]] = defaultdict(list)
        self.attack_lookup = {a.attack_id: a for a in attacks}
        for c in correlations:
            self.by_attack[c.attack_id].append(c)
        for attack_id in self.by_attack:
            self.by_attack[attack_id].sort(key=lambda c: (-c.score, c.abs_delta_seconds))
        self.attack_idx = 0
        self.corr_idx = 0
        self.focus_pane = self.PANE_ATTACKS
        self.preview_highlight_attr = curses.A_BOLD
        self.preview_green_attr = curses.A_BOLD
        self.preview_bold_attr = curses.A_BOLD
        self.correlation_highlight_attr = curses.A_BOLD

    def current_attack(self) -> Optional[Attack]:
        if not self.attacks:
            return None
        self.attack_idx = max(0, min(self.attack_idx, len(self.attacks) - 1))
        return self.attacks[self.attack_idx]

    def current_correlations(self) -> list[Correlation]:
        attack = self.current_attack()
        if not attack:
            return []
        return self.by_attack.get(attack.attack_id, [])

    def current_correlation(self) -> Optional[Correlation]:
        rows = self.current_correlations()
        if not rows:
            return None
        self.corr_idx = max(0, min(self.corr_idx, len(rows) - 1))
        return rows[self.corr_idx]

    def run(self) -> None:
        curses.wrapper(self._main)

    def _focus_title(self, title: str, pane: int) -> str:
        return f"> {title} <" if self.focus_pane == pane else title

    def _draw_list(self, win, title: str, rows: list[str], selected: int, top: int, highlighted: Optional[set[int]] = None, highlight_attr: Optional[int] = None) -> int:
        height, width = win.getmaxyx()
        win.box()
        title_attr = curses.A_REVERSE | curses.A_BOLD if title.startswith(">") else curses.A_BOLD
        win.addnstr(0, 2, f" {title} ", width - 4, title_attr)
        visible = max(1, height - 2)
        if rows:
            selected = max(0, min(selected, len(rows) - 1))
        if selected < top:
            top = selected
        if selected >= top + visible:
            top = selected - visible + 1
        highlighted = highlighted or set()
        highlight_attr = highlight_attr if highlight_attr is not None else curses.A_NORMAL
        for i in range(visible):
            idx = top + i
            if idx >= len(rows):
                break
            base_attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            if idx in highlighted:
                attr = highlight_attr | (curses.A_REVERSE if idx == selected else curses.A_NORMAL)
            else:
                attr = base_attr
            win.addnstr(i + 1, 1, rows[idx].ljust(width - 2), width - 2, attr)
        return top

    def _draw_text(self, win, title: str, lines: list[str], top: int = 0, keywords: Optional[list[str]] = None) -> int:
        height, width = win.getmaxyx()
        inner_width = max(1, width - 2)
        max_rows = max(0, height - 2)
        win.box()
        rendered: list[str] = []
        previous_blank = False
        for line in lines:
            safe_line = _ui_sanitize(line)
            if safe_line == "":
                if not previous_blank:
                    rendered.append("")
                previous_blank = True
                continue
            previous_blank = False
            start_idx = 0
            while start_idx < len(safe_line):
                rendered.append(safe_line[start_idx:start_idx + inner_width])
                start_idx += inner_width
        if top < 0:
            top = 0
        max_top = max(0, len(rendered) - max_rows)
        if top > max_top:
            top = max_top
        title_attr = curses.A_REVERSE | curses.A_BOLD if title.startswith(">") else curses.A_BOLD
        status = f" {title} [{top + 1}-{min(len(rendered), top + max_rows)}/{max(len(rendered), 1)}] "
        win.addnstr(0, 2, status, width - 4, title_attr)
        highlight_attr = getattr(self, "preview_highlight_attr", curses.A_BOLD)
        keywords = keywords or []
        for i in range(max_rows):
            idx = top + i
            if idx >= len(rendered):
                break
            _render_semantic_highlighted_line(
                win,
                i + 1,
                1,
                inner_width,
                rendered[idx].ljust(inner_width),
                keywords,
                highlight_attr,
                getattr(self, "preview_green_attr", curses.A_BOLD),
                getattr(self, "preview_bold_attr", curses.A_BOLD),
            )
        return top

    def _main(self, stdscr) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_BLUE, -1)
            self.preview_highlight_attr = curses.color_pair(1) | curses.A_BOLD
            self.preview_green_attr = curses.color_pair(2) | curses.A_BOLD
            self.preview_bold_attr = curses.A_BOLD
            self.correlation_highlight_attr = curses.color_pair(1) | curses.A_BOLD
        except Exception:
            self.preview_highlight_attr = curses.A_BOLD
            self.preview_green_attr = curses.A_BOLD
            self.preview_bold_attr = curses.A_BOLD
            self.correlation_highlight_attr = curses.A_BOLD
        attack_top = 0
        corr_top = 0
        preview_top = 0
        preview_collapsed = True
        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()
            header = "Attack / Log Correlator  q:quit  Left/Right:switch pane  Up/Down:scroll focused pane  Shift-Up/Down:scroll correlations  PgUp/PgDn:page  z:collapse"
            stdscr.addnstr(0, 0, header.ljust(max_x), max_x - 1, curses.A_STANDOUT)
            mid_w = max(34, max_x // 5)
            side_total = max_x - mid_w
            left_w = side_total // 2
            right_w = max_x - left_w - mid_w
            attack_win = stdscr.derwin(max_y - 1, left_w, 1, 0)
            corr_win = stdscr.derwin(max_y - 1, mid_w, 1, left_w)
            preview_win = stdscr.derwin(max_y - 1, right_w, 1, left_w + mid_w)

            attack_rows = []
            highlighted_attack_rows: set[int] = set()
            attack_corr_counts = {a.attack_id: len(self.by_attack.get(a.attack_id, [])) for a in self.attacks}
            for idx, a in enumerate(self.attacks):
                cnt = attack_corr_counts.get(a.attack_id, 0)
                if cnt > 0:
                    highlighted_attack_rows.add(idx)
                attack_rows.append(
                    f"{idx+1:3d} {cnt:3d} {a.attacker_host[:12]:<12} {a.timestamp.strftime('%Y-%m-%d %H:%M:%S')} {a.attack_type:<8} {a.cmd[:38]}"
                )
            attack_top = self._draw_list(
                attack_win,
                self._focus_title(f"Attacks ({len(self.attacks)})", self.PANE_ATTACKS),
                attack_rows,
                self.attack_idx,
                attack_top,
                highlighted=highlighted_attack_rows,
                highlight_attr=getattr(self, "correlation_highlight_attr", curses.A_BOLD),
            )

            correlations = self.current_correlations()
            corr_rows = []
            lexical_avg = average_lexical_score(correlations)
            highlighted_corr_rows: set[int] = set()
            for idx, c in enumerate(correlations):
                lex_score = correlation_lexical_score(c)
                if lex_score > lexical_avg:
                    highlighted_corr_rows.add(idx)
                corr_rows.append(
                    f"{c.host[:12]:<12} s={c.score:5.1f} lx={lex_score:5.1f} dt={c.delta_seconds:7.2f}s {c.event_message[:42]}"
                )
            corr_top = self._draw_list(
                corr_win,
                self._focus_title(f"Correlations ({len(correlations)})", self.PANE_CORRELATIONS),
                corr_rows,
                self.corr_idx,
                corr_top,
                highlighted=highlighted_corr_rows,
                highlight_attr=getattr(self, "correlation_highlight_attr", curses.A_BOLD),
            )

            corr = self.current_correlation()
            preview = build_preview_lines(corr, collapsed=preview_collapsed)
            preview_title = "Event Preview (collapsed)" if preview_collapsed else "Event Preview (expanded)"
            preview_top = self._draw_text(
                preview_win,
                self._focus_title(preview_title, self.PANE_PREVIEW),
                preview,
                preview_top,
                _preview_keywords(corr),
            )
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord("q"), 27):
                break
            if ch == curses.KEY_LEFT:
                self.focus_pane = (self.focus_pane - 1) % 3
            elif ch == curses.KEY_RIGHT:
                self.focus_pane = (self.focus_pane + 1) % 3
            elif ch == curses.KEY_UP:
                if self.focus_pane == self.PANE_ATTACKS:
                    self.attack_idx = max(0, self.attack_idx - 1)
                    self.corr_idx = 0
                    preview_top = 0
                elif self.focus_pane == self.PANE_CORRELATIONS:
                    self.corr_idx = max(0, self.corr_idx - 1)
                    preview_top = 0
                else:
                    preview_top = max(0, preview_top - 1)
            elif ch == curses.KEY_DOWN:
                if self.focus_pane == self.PANE_ATTACKS:
                    self.attack_idx = min(max(0, len(self.attacks) - 1), self.attack_idx + 1)
                    self.corr_idx = 0
                    preview_top = 0
                elif self.focus_pane == self.PANE_CORRELATIONS:
                    self.corr_idx = min(max(0, len(correlations) - 1), self.corr_idx + 1)
                    preview_top = 0
                else:
                    preview_top += 1
            elif ch in (getattr(curses, "KEY_SR", -9999), 337):
                self.corr_idx = max(0, self.corr_idx - 1)
                preview_top = 0
            elif ch in (getattr(curses, "KEY_SF", -9998), 336):
                self.corr_idx = min(max(0, len(correlations) - 1), self.corr_idx + 1)
                preview_top = 0
            elif ch == curses.KEY_NPAGE:
                if self.focus_pane == self.PANE_ATTACKS:
                    self.attack_idx = min(max(0, len(self.attacks) - 1), self.attack_idx + max(1, attack_win.getmaxyx()[0] - 3))
                    self.corr_idx = 0
                    preview_top = 0
                elif self.focus_pane == self.PANE_CORRELATIONS:
                    self.corr_idx = min(max(0, len(correlations) - 1), self.corr_idx + max(1, corr_win.getmaxyx()[0] - 3))
                    preview_top = 0
                else:
                    preview_top += max(1, preview_win.getmaxyx()[0] - 3)
            elif ch == curses.KEY_PPAGE:
                if self.focus_pane == self.PANE_ATTACKS:
                    self.attack_idx = max(0, self.attack_idx - max(1, attack_win.getmaxyx()[0] - 3))
                    self.corr_idx = 0
                    preview_top = 0
                elif self.focus_pane == self.PANE_CORRELATIONS:
                    self.corr_idx = max(0, self.corr_idx - max(1, corr_win.getmaxyx()[0] - 3))
                    preview_top = 0
                else:
                    preview_top = max(0, preview_top - max(1, preview_win.getmaxyx()[0] - 3))
            elif ch in (ord("z"), ord("Z")):
                preview_collapsed = not preview_collapsed
                preview_top = 0


# --------------------------------- cli -------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Correlate attack logs against heterogeneous host logs.")
    p.add_argument("--attack-root", required=True, help="Root directory containing JSON attack logs")
    p.add_argument("--log-root", required=True, help="Root directory containing nested host logs")
    p.add_argument("--out-dir", required=True, help="Directory for correlation outputs")
    p.add_argument("--host-config", help="Optional JSON config for host timezones, skew, aliases, and IPs")
    p.add_argument("--default-timezone", default="Europe/Vienna", help="Default timezone for naive host logs")
    p.add_argument("--window-before", type=float, default=60.0, help="Seconds before attack to include")
    p.add_argument("--window-after", type=float, default=240.0, help="Seconds after attack to include")
    p.add_argument("--max-per-attack", type=int, default=30, help="Maximum saved correlations per attack")
    p.add_argument("--default-year", type=int, default=CURRENT_YEAR_FALLBACK, help="Fallback year for yearless timestamps")
    p.add_argument("--no-ui", action="store_true", help="Write outputs only")
    p.add_argument("--browse-output", action="store_true", help="Browse existing output/correlations.json without recomputing logs")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    attack_root = Path(args.attack_root).expanduser().resolve()
    log_root = Path(args.log_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    host_config_path = Path(args.host_config).expanduser().resolve() if args.host_config else None

    if args.browse_output:
        attacks, correlations = load_output_for_browsing(out_dir)
        summary = {
            "mode": "browse-output",
            "attacks": len(attacks),
            "correlations": len(correlations),
            "out_dir": str(out_dir),
            "source": str(out_dir / "correlations.json"),
        }
        print(json.dumps(summary, indent=2))
        if not args.no_ui:
            try:
                CorrelationBrowser(attacks, correlations).run()
            except Exception:
                print("[error] curses UI crashed", file=sys.stderr)
                traceback.print_exc()
        return 0

    discovered_hosts = discover_hosts_from_logs(log_root, attack_root, args.default_timezone)
    discovered_attacker_hosts = sorted({guess_attacker_host_from_path(p, attack_root) for p in discover_attack_files(attack_root)})
    config = load_config(host_config_path, discovered_hosts, args.default_timezone)

    # ConfigBundle compatibility: enrich the underlying raw config dict if present.
    raw_cfg = getattr(config, "raw_config", None)
    if not isinstance(raw_cfg, dict):
        raw_cfg = {}
        try:
            config.raw_config = raw_cfg
        except Exception:
            pass

    raw_cfg.setdefault("attacker_hosts", {})
    raw_cfg.setdefault("default_utc_offset_hours", 0)
    for attacker in discovered_attacker_hosts:
        raw_cfg["attacker_hosts"].setdefault(attacker, {
            "utc_offset_hours": raw_cfg.get("default_utc_offset_hours", 0),
            "notes": "Adjust attacker time offset relative to UTC here",
        })

    resolver = HostResolver(config)

    attacks = load_all_attacks(attack_root, resolver, config=config)
    # attacks may reveal additional hostnames via IP mapping in config; reload not necessary
    events = load_all_events(log_root, attack_root, args.default_year, resolver)
    correlations = correlate(attacks, events, args.window_before, args.window_after, args.max_per_attack)
    export_outputs(out_dir, config, attacks, events, correlations)

    summary = {
        "attacks": len(attacks),
        "events": len(events),
        "correlations": len(correlations),
        "attack_root": str(attack_root),
        "log_root": str(log_root),
        "out_dir": str(out_dir),
        "host_config": str(host_config_path) if host_config_path else None,
        "generated_host_config": str(out_dir / "host_config.generated.json"),
    }
    print(json.dumps(summary, indent=2))

    if not args.no_ui:
        try:
            CorrelationBrowser(attacks, correlations).run()
        except Exception:
            print("[error] curses UI crashed", file=sys.stderr)
            traceback.print_exc()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
