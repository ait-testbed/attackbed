#!/usr/bin/env python3
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

Author: Erik Grafendorfer 
"""

# =============================================================================
# BIG-PICTURE MAP
# =============================================================================
# This script is a pipeline.  Almost every function belongs to one of these
# stages:
#
#   1. Discovery
#      Find attack-log files and host-log files below the supplied roots.
#
#   2. Configuration / host resolution
#      Build a HostResolver so messy names, aliases, IPs, networks, and paths can
#      all point to canonical host names.
#
#   3. Attack loading
#      Read JSON attack-log lines into Attack objects and extract command,
#      timestamp, attacker host, and likely targets.
#
#   4. Host-log loading
#      Read text logs, convert binary journals with journalctl, parse timestamps,
#      normalize timezones/skew, and produce LogEvent objects.
#
#   5. Correlation
#      For each attack, examine nearby events, score time/content evidence, and
#      keep correlations that pass relevance_threshold().
#
#   6. Export / review
#      Write JSON, CSV, human-readable summaries, per-host outputs, and optionally
#      open an ncurses browser for manual inspection.
#
# Comments below are intentionally verbose.  They explain not only what each
# function does, but how it contributes to the end-to-end correlation pipeline.
# =============================================================================

from __future__ import annotations

# Standard-library imports only: the script has no third-party dependency.
import argparse
import csv
import curses
import dataclasses
import datetime as dt
import ipaddress
import json
import math
import pprint as pp
import re
import shlex
import subprocess
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

# All internally comparable timestamps are normalized to UTC.  The script may
# parse local/naive timestamps first, but correlation only makes sense once
# attack and host-log times are on the same timezone-aware timeline.
UTC = dt.timezone.utc
# Syslog-style lines often do not include a year.  This default supplies the
# current year unless the user overrides it with --default-year.
CURRENT_YEAR_FALLBACK = dt.datetime.now().year
# Hard cap used inside correlate(): even if the CLI search window is wider,
# candidate pairs whose absolute timestamp delta is above this value are skipped
# before scoring.  This makes time correlation extremely strict for timestamped
# events.  Events with no parseable timestamp bypass this cap and receive a time
# score of zero instead.
MAX_TIME_DELTA_SECONDS = 0.3

# Sentinel used internally for log lines that do not contain a parseable
# timestamp.  The real signal for these rows is extra["timestamp_missing"], not
# this placeholder value; the placeholder exists because LogEvent.timestamp is a
# datetime field and export/UI code expects it to be present.
UNKNOWN_TIMESTAMP_SENTINEL = dt.datetime.fromtimestamp(0, tz=UTC)

# Counter for log lines that could be converted into events but did not have a
# parseable timestamp.  main() prints this to stdout after loading host logs.
UNPARSABLE_LINE_COUNT = 0
# Diagnostics for binary input handling.  These are printed in the stdout
# summary so it is visible whether journalctl conversion actually happened.
JOURNALCTL_CONVERTED_FILE_COUNT = 0
BINARY_LOG_FILE_SKIPPED_COUNT = 0

# Scoring weights.  These replace the former inline “magic numbers” so the
# scoring model can be tuned from one visible section without hunting through
# the implementation.  The values are intentionally unchanged.
BINARY_MATCH_BASE = 40.0
BINARY_MATCH_PER_HIT = 25.0
BINARY_MATCH_MAX = 120.0
LEXICAL_EXACT_PER_HIT = 10.0
LEXICAL_EXACT_MAX = 80.0
LEXICAL_OVERLAP_PER_TERM = 6.0
LEXICAL_OVERLAP_MAX = 40.0
METADATA_LEXICAL_PER_HIT = 3.0
METADATA_LEXICAL_MAX = 18.0
LEXICAL_MULTI_MIN_MATCHES = 3
LEXICAL_MULTI_PER_MATCH = 5.0
LEXICAL_MULTI_MAX = 25.0
TARGET_HOST_EXACT_SCORE = 45.0
TARGET_HOST_CANDIDATE_SCORE = 25.0
IP_LITERAL_BASE = 20.0
IP_LITERAL_PER_HIT = 10.0
IP_LITERAL_MAX = 50.0
NETWORK_MATCH_BASE = 15.0
NETWORK_MATCH_PER_HIT = 10.0
NETWORK_MATCH_MAX = 35.0
SOURCE_TYPE_HINT_SCORE = 6.0
TIME_PROXIMITY_MAX_SCORE = 40.0
POST_ATTACK_BONUS_WINDOW_SECONDS = 10.0
POST_ATTACK_BONUS_SCORE = 12.0
PRE_ATTACK_CONTEXT_WINDOW_SECONDS = 5.0
PRE_ATTACK_CONTEXT_BONUS_SCORE = 4.0
RELEVANCE_SCORE_THRESHOLD = 60.0
RELEVANCE_TARGET_HOST_THRESHOLD = 45.0
RELEVANCE_IP_NETWORK_THRESHOLD = 40.0
CONTENT_SCORE_WEIGHT = 2.0

# Values larger than this are assumed to be Unix epoch milliseconds
# rather than Unix epoch seconds.
EPOCH_MILLISECONDS_THRESHOLD = 10_000_000_000

# Lookup table for parsing classic syslog month abbreviations.
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

# Generic path names that should not be mistaken for hostnames when inferring a
# host from a log file path.
COMMON_DIR_NAMES = {"logs", "log", "var", "tmp", "journal", "journals", "audit", "audits", "syslog", "host", "hosts", "varlog"}
# File names/stems that describe a log type, not a host.  These should not end
# up as host names in host_config.generated.json.
COMMON_LOG_STEMS = {
    "auth", "authlog", "boot", "btmp", "cloud-init", "container", "daemon", "debug", "dmesg",
    "dpkg", "eve", "faillog", "kern", "lastlog", "messages", "secure", "syslog", "wtmp",
}
# Binary files that are not valid systemd journals should not be read as text
# with replacement characters, because that creates binary-looking UI/output rows.
BINARY_SAMPLE_BYTES = 8192
BINARY_CONTROL_BYTE_RATIO = 0.30
# File suffixes considered attack logs during attack discovery.
ATTACK_LOG_SUFFIXES = {".json"}
# File suffixes considered text host logs during host-log discovery.
TEXT_EXTENSIONS = {".log", ".txt", ".json", ".jsonl", ".out", ".err", ".messages", ".syslog", ".csv"}
# Very common words/commands/protocol labels that are too generic to be useful
# as host or content-matching tokens.
STOP_TOKENS = {
    "sudo", "nmap", "bash", "sh", "python", "python3", "nc", "curl", "wget", "ssh", "scp", "ftp",
    "http", "https", "tcp", "udp", "icmp", "reconnaissance", "discovery", "network", "scan", "ports",
}

# Extra stop words used only for lexical scoring.  These remove path components,
# boilerplate terms, and JSON-y values that would otherwise create false matches.
LEXICAL_STOP_TOKENS = STOP_TOKENS | {
    "bin", "usr", "var", "tmp", "etc", "log", "logs", "root", "system", "service", "session",
    "shell", "command", "interactive", "background", "error", "metadata", "description",
    "the", "and", "for", "with", "from", "into", "that", "this", "false", "true", "null",
}


@dataclasses.dataclass
# ---------------------------------------------------------------------------
# Data model: one row from an attack log.
#
# An Attack is the "left side" of a correlation.  It represents one attack
# action from the attack log, not a host-log event.  Later scoring compares this
# object against many LogEvent objects.  The fields deliberately preserve both
# normalized data (timestamp, command, targets) and provenance (file, line)
# so that output rows can point back to the original evidence. The original
# full JSON object is intentionally not stored; raw_line preserves the exact
# attack-log evidence without keeping a second structured copy.
# ---------------------------------------------------------------------------
class Attack:
    attack_id: str
    timestamp: dt.datetime
    attack_type: str
    cmd: str
    source_file: str
    line_number: int
    metadata: dict[str, Any]
    raw_line: str = ""
    target_hosts: list[str] = dataclasses.field(default_factory=list)
    target_ips: list[str] = dataclasses.field(default_factory=list)
    target_networks: list[str] = dataclasses.field(default_factory=list)
    target_tokens: list[str] = dataclasses.field(default_factory=list)
    attacker_host: str = "unknown-attacker"

@dataclasses.dataclass
# ---------------------------------------------------------------------------
# Data model: one parsed host-log line.
#
# A LogEvent is the "right side" of a correlation.  Every host log line that can
# be assigned a timestamp becomes one LogEvent.  Lines without parseable
# timestamps are currently skipped before correlation, which is important for
# understanding missed matches.
# ---------------------------------------------------------------------------
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
# ---------------------------------------------------------------------------
# Data model: one proposed connection between an attack and a host-log event.
#
# A Correlation stores the two IDs being linked, the time delta, the evidence
# used for scoring, and enough source-location information to inspect both
# original lines.  The exporter and ncurses browser both consume this structure.
# ---------------------------------------------------------------------------
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
    matched_lexical_terms: list[str] = dataclasses.field(default_factory=list)
    matched_command_terms: list[str] = dataclasses.field(default_factory=list)
    matched_metadata_terms: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
# ---------------------------------------------------------------------------
# Data model: configuration for a single host.
#
# HostProfile is the user-editable knowledge base for resolving aliases, IPs,
# path hints, timezone, and clock skew.  HostResolver turns these profiles into
# lookup tables used throughout parsing and scoring.
# ---------------------------------------------------------------------------
class HostProfile:
    name: str
    timezone: str
    clock_skew_seconds: float = 0.0
    aliases: list[str] = dataclasses.field(default_factory=list)
    ip_addresses: list[str] = dataclasses.field(default_factory=list)
    path_hints: list[str] = dataclasses.field(default_factory=list)
    notes: str = ""


@dataclasses.dataclass
# ---------------------------------------------------------------------------
# Data model: the full configuration bundle.
#
# The bundle combines automatically discovered hosts, optional JSON
# configuration, and global defaults.  It is passed into HostResolver and also
# written back out as host_config.generated.json for tuning.
# ---------------------------------------------------------------------------
class ConfigBundle:
    default_timezone: str
    default_clock_skew_seconds: float
    hosts: dict[str, HostProfile]
    raw_config: dict[str, Any] = dataclasses.field(default_factory=dict)



# Convert attacker clock-offset config into a float number of hours.
# This is separate from host clock skew: it adjusts attack-log timestamps when
# attack logs were produced in a local/non-UTC clock but encoded as ISO text.
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


# Apply the attacker time shift by subtracting hours from the parsed timestamp.
# Example: a +2 offset means local time is two hours ahead of UTC, so subtract
# two hours to normalize to UTC.
def apply_timezone_shift(parsed: dt.datetime, shift_hours: float) -> dt.datetime:
    return parsed - dt.timedelta(hours=shift_hours)



# Turn arbitrary path fragments into safe host-like names.
# This is used when host/attacker names are inferred from directory names.  It
# wraps sanitize_host_name but has a defensive fallback so path inference does
# not crash if unexpected input appears.
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


# Infer the attacker machine from the attack-log path.
# The script assumes attack logs may be grouped by attacker directory.  It walks
# the relative path and picks the first meaningful directory that is not a
# generic container name like 'attacklogs' or 'logs'.
def guess_attacker_host_from_path(path: Path, root: Path) -> str:
    # Prefer a path relative to the user-supplied root, because directory
    # components inside that root are meaningful for host inference.  If that
    # fails (for example because paths are on different roots), fall back to the
    # raw path parts rather than aborting.
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except Exception:
        rel_parts = path.parts
    # Ignore the filename itself (rel_parts[:-1]) and look for the first
    # non-generic directory.  Example:
    #   attacklogs/attacker-a/step01.json -> attacker-a
    for part in rel_parts[:-1]:
        lowered = part.lower()
        if lowered not in {"attacklogs", "attacks", "attacklog", "logs", "log"}:
            return normalize_path_host_part(part)
    if len(rel_parts) >= 2:
        return normalize_path_host_part(rel_parts[-2])
    return "unknown-attacker"

# Parse an ISO-8601 datetime and return it as timezone-aware UTC.
# Naive datetimes are treated as UTC here.  Other parts of the script separately
# handle naive host-log timestamps by applying host timezones.
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


def parse_attack_datetime(value: str, attacker_timezone: str = "UTC") -> Optional[dt.datetime]:
    """Parse an attack-log timestamp using the attacker's configured timezone.

    parse_iso_datetime() intentionally treats naive timestamps as UTC because
    many machine logs are UTC by convention.  Attack logs are different here:
    different attacker machines may have been configured to different local
    timezones.  This helper preserves existing behavior for timestamps that
    already include an offset, but interprets naive attack timestamps in the
    per-attacker timezone from host_config/generated config.
    """
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        zone = get_zone(attacker_timezone or "UTC")
        return parsed.replace(tzinfo=zone).astimezone(UTC)
    return parsed.astimezone(UTC)


# Normalize names so aliases, paths, and extracted tokens can be compared.
# Lowercasing and replacing weird characters avoids mismatches like
# 'Host A.log' versus 'host-a'.
def sanitize_host_name(name: str) -> str:
    name = re.sub(r"\.(log|txt|json|journal|gz|xz|bz2)$", "", name, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-_.")
    return name.lower() or "unknown-host"


def looks_like_random_identifier(name: str) -> bool:
    """Return True for path fragments that are probably IDs, not hostnames."""
    text = sanitize_host_name(name)
    compact = text.replace("-", "").replace("_", "").replace(".", "")
    if not compact:
        return True
    # UUID-ish or long hex-ish directory/file names are common in extracted log
    # bundles and should not become generated host names.
    if re.fullmatch(r"[0-9a-f]{12,}", compact, flags=re.I):
        return True
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, flags=re.I):
        return True
    # Long mostly-numeric strings are usually timestamps, container IDs, or
    # artifact IDs rather than machine names.
    digit_count = sum(ch.isdigit() for ch in compact)
    if len(compact) >= 10 and digit_count / max(1, len(compact)) > 0.60:
        return True
    # Very long opaque tokens with no separators tend to be hashes/container IDs.
    if len(compact) >= 24 and re.fullmatch(r"[a-z0-9]+", compact, flags=re.I):
        return True
    return False


def is_plausible_host_name(name: str) -> bool:
    """Filter path fragments before using them as inferred host names."""
    text = sanitize_host_name(name)
    if not text or text == "unknown-host":
        return False
    if text in COMMON_DIR_NAMES or text in COMMON_LOG_STEMS:
        return False
    if text.isdigit() or len(text) < 3:
        return False
    if safe_ip_address(text) or safe_ip_network(text):
        return False
    if looks_like_random_identifier(text):
        return False
    return True


def host_candidates_from_path(path: Path, root: Path) -> list[str]:
    """Return only the top-level host folder under the log root, if plausible.

    Earlier versions collected many directory names and file stems as path hints.
    That made unrelated hosts share hints such as ``apt``, ``history``,
    ``system``, or ``user-1000``.  For generated config and path-based host
    inference, the only reliable automatic hint is the first path component
    below ``log_root``: for example ``hostlogs/fileshare/var/log/syslog`` should
    produce only ``fileshare``.
    """
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except Exception:
        rel_parts = path.parts

    if not rel_parts:
        return []

    top_level = sanitize_host_name(rel_parts[0])
    if is_plausible_host_name(top_level):
        return [top_level]
    return []


# Regexes used by extraction helpers.  IP_RE intentionally finds IPv4-looking
# tokens; safe_ip_address/safe_ip_network later validate when needed.
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
HOST_TOKEN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_.-]{2,}\b")


# Parse an IP network without raising an exception on bad input.
# strict=False accepts host addresses as /32 or /128 networks, which is useful
# when user config mixes individual IPs and CIDR ranges.
def safe_ip_network(token: str) -> Optional[ipaddress._BaseNetwork]:
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


# Parse an IP address without raising an exception on bad input.
# Returning None lets extraction/scoring code try many tokens safely.
def safe_ip_address(token: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None



# Resolve an IANA timezone name into a ZoneInfo object.
# If lookup fails, warn loudly and fall back to UTC.  That keeps the script
# running while making misspelled timezone names visible in stderr.
def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:
        print(f"[warn] failed to load timezone {name!r}; falling back to UTC: {exc}", file=sys.stderr)
        return ZoneInfo("UTC")


@dataclasses.dataclass
# ---------------------------------------------------------------------------
# Intermediate timestamp parse result.
#
# The parser records both the UTC-ish timestamp and whether it was naive.  If
# naive=True, normalize_event_time later reinterprets the wall-clock time in the
# host's configured timezone.
# ---------------------------------------------------------------------------
class ParsedTimestamp:
    timestamp_utc: dt.datetime
    raw_text: str
    naive: bool
    parser_name: str


# ---------------------------------------------------------------------------
# Host resolution engine.
#
# HostResolver precomputes lookup tables from ConfigBundle so the rest of the
# script can answer questions like:
#   - Which canonical host does this alias mean?
#   - Which host owns this IP address or network?
#   - Which host does this path probably belong to?
# This is the glue between messy log naming and stable host identities.
# ---------------------------------------------------------------------------
class HostResolver:
    # Build lookup indexes once so repeated correlation checks are fast.
    # These maps/lists are used for alias normalization, direct IP lookup,
    # CIDR-network lookup, and path-hint matching.
    def __init__(self, config: ConfigBundle):
        self.config = config
        self.alias_to_host: dict[str, str] = {}
        self.ip_to_host: dict[str, str] = {}
        self.networks: list[tuple[ipaddress._BaseNetwork, str]] = []
        self.path_hints: list[tuple[str, str]] = []
        # Precompute alias/IP/network/path indexes from the config.  This is
        # done once at startup so later line-by-line parsing does not repeatedly
        # traverse the full host config.
        for host, profile in config.hosts.items():
            for alias in {host, *profile.aliases}:
                self.alias_to_host[sanitize_host_name(alias)] = host
            for ip_text in profile.ip_addresses:
                if "/" in ip_text:
                    net = safe_ip_network(ip_text)
                    if net:
                        # Networks are stored as (network, host) pairs because
                        # an event IP may later match by CIDR membership.
                        self.networks.append((net, host))
                else:
                    addr = safe_ip_address(ip_text)
                    if addr:
                        self.ip_to_host[str(addr)] = host
            for hint in profile.path_hints:
                self.path_hints.append((sanitize_host_name(hint), host))

    # Return a host-specific timezone, or the global default if the host is unknown.
    def resolve_timezone(self, host: str) -> str:
        return self.config.hosts.get(host, HostProfile(host, self.config.default_timezone)).timezone

    # Return a host-specific clock skew in seconds, or zero/default if unknown.
    def resolve_clock_skew(self, host: str) -> float:
        return self.config.hosts.get(host, HostProfile(host, self.config.default_timezone)).clock_skew_seconds

    # Convert any observed host token/alias into the canonical configured host name.
    def canonicalize_host(self, host: str) -> str:
        return self.alias_to_host.get(sanitize_host_name(host), sanitize_host_name(host))

    # Map an IP address or CIDR network to a configured host.
    # Direct IP matches are tried first; then CIDR membership is checked.  If the
    # input itself is a network, overlapping/subnet networks are considered a match.
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

    # Guess which host a log file belongs to based on its directory/file path.
    # The function prefers configured aliases, then configured path hints, then a
    # best-effort non-generic path component.  This is why directory structure
    # matters for the correlator.
    def host_from_path(self, path: Path, root: Path) -> Optional[str]:
        candidates = host_candidates_from_path(path, root)
        for cand in candidates:
            if cand in self.alias_to_host:
                return self.alias_to_host[cand]
        for cand in reversed(candidates):
            for hint, host in self.path_hints:
                if hint and hint in cand:
                    return host
        if candidates:
            return candidates[0]
        return None

    # Combine all host-resolution hints available for one log line.
    # Tokens can match aliases, IPs can map to hosts, and the file path can provide
    # a fallback host.  The returned list is later used in target-host scoring.
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

# Convert epoch seconds into a UTC datetime.
# auditd timestamps use this form inside audit(...), so this helper supports
# audit log parsing.
def parse_epoch_seconds(text: str) -> Optional[dt.datetime]:
    try:
        value = float(text)
    except ValueError:
        return None

    # Many JSON loggers emit epoch milliseconds while auditd emits epoch
    # seconds.  Treat very large epoch-like values as milliseconds so
    # 1710000000123 becomes 1710000000.123 instead of year 56157.
    if abs(value) >= EPOCH_MILLISECONDS_THRESHOLD:
        value = value / 1000.0

    try:
        return dt.datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


# Extract auditd timestamps such as audit(1716814917.123:456).
# auditd stores seconds since epoch, so these timestamps are already absolute
# and do not need host timezone interpretation.
def parse_audit_timestamp(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.search(r"audit\((\d+(?:\.\d+)?):\d+\)", line)
    if not m:
        return None
    ts = parse_epoch_seconds(m.group(1))
    if not ts:
        return None
    return ParsedTimestamp(ts, m.group(1), False, "auditd-epoch")


# Parse classic syslog timestamps like 'May 27 13:01:57'.
# Syslog usually omits the year and timezone.  The caller supplies a fallback
# year; timezone handling happens later because it depends on the host.
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


# Wrap parse_syslog_timestamp into the common ParsedTimestamp shape.
# The timestamp is marked naive=True so normalize_event_time will reinterpret it
# in the configured host timezone.
def parse_syslog_like(line: str, default_year: int) -> Optional[ParsedTimestamp]:
    res = parse_syslog_timestamp(line, default_year)
    if not res:
        return None
    naive_dt, text = res
    return ParsedTimestamp(naive_dt.replace(tzinfo=UTC), text, True, "syslog-like")


# Parse Suricata-style timestamps like '27/05/2026 -- 13:01:57'.
# These are treated as naive host-local times and normalized later.
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


# Parse log lines that begin with an ISO timestamp followed by whitespace.
# journalctl short-iso-precise output is one example of this shape.


# Parse Apache/Nginx access-log timestamps embedded in square brackets, e.g.
#   127.0.0.1 - - [27/May/2026:13:01:57 +0200] "GET / HTTP/1.1" 200 ...
# The timezone offset is part of the timestamp, so the result is non-naive and
# normalize_event_time must not apply the host timezone a second time.
def parse_apache_nginx_timestamp(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.search(r"\[(\d{1,2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\]", line)
    if not m:
        return None
    raw = m.group(1)
    try:
        parsed = dt.datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    return ParsedTimestamp(parsed.astimezone(UTC), raw, False, "apache-nginx")


def parse_iso_prefix(line: str, *_args) -> Optional[ParsedTimestamp]:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))\s+", line)
    if not m:
        return None
    parsed = parse_iso_datetime(m.group(1))
    if not parsed:
        return None
    return ParsedTimestamp(parsed, m.group(1), False, "iso-prefix")


# Parse a JSON log line and look for common timestamp fields.
# String values are treated as ISO-like datetimes.  Numeric values are treated as
# Unix epoch seconds, which covers logs that emit timestamps like 1716814917 or
# 1716814917.123 instead of an ISO string.
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
        elif isinstance(value, (int, float)):
            parsed = parse_epoch_seconds(str(value))
            if parsed:
                return ParsedTimestamp(parsed, str(value), False, f"json:{key}:epoch")
    return None


# Try all supported timestamp parsers in priority order.
# Returning None means the host-log line will not become a LogEvent, so timestamp
# coverage directly controls what can be correlated.
def try_parse_line_timestamp(line: str, default_year: int) -> Optional[ParsedTimestamp]:
    for parser in (parse_json_line_timestamp, parse_audit_timestamp, parse_iso_prefix, parse_apache_nginx_timestamp, parse_suricata_timestamp):
        parsed = parser(line, default_year)
        if parsed:
            return parsed
    parsed = parse_syslog_like(line, default_year)
    if parsed:
        return parsed
    return None


# ---------------------------- extraction helpers ---------------------------

# Classify the log source from filename and line shape.
# This does not parse the whole log format; it gives scoring/export/UI a useful
# label such as auditd, docker-json, suricata, syslog-like, or generic-text.
def detect_source_type(path: Path, line: str) -> str:
    lower = path.name.lower()
    if lower.endswith(".journal"):
        return "journal-binary"
    if "audit" in lower or "audit(" in line:
        return "auditd"
    if line.lstrip().startswith("{") and '"time"' in line and '"log"' in line:
        return "docker-json"
    if re.search(r"\[\d{1,2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}\]", line):
        if "nginx" in lower:
            return "nginx-access"
        if "apache" in lower or "access" in lower:
            return "apache-access"
        return "http-access"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}\s+--\s+\d{2}:\d{2}:\d{2}", line):
        return "suricata"
    if re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}", line):
        return "syslog-like"
    return "generic-text"


# Extract an explicit host name from log lines whose format carries one.
# Syslog and ISO-prefix journal exports often place the hostname immediately
# after the timestamp.
def guess_host_from_line(line: str) -> Optional[str]:
    m = re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+([A-Za-z0-9._-]+)\s+", line)
    if m:
        return sanitize_host_name(m.group(1))
    m = re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\s+([A-Za-z0-9._-]+)\s+", line)
    if m:
        return sanitize_host_name(m.group(1))
    return None


# Return unique IPv4/CIDR-looking tokens from arbitrary text.
# Validation is intentionally loose here; later helpers decide whether a token
# is a valid address/network.
def extract_ips(text: str) -> list[str]:
    seen: list[str] = []
    for token in IP_RE.findall(text):
        if token not in seen:
            seen.append(token)
    return seen


# Extract unique host/word-like tokens from text.
# Stop words are removed so scoring focuses on distinctive commands, hostnames,
# paths, usernames, and metadata terms rather than generic protocol words.
def extract_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in HOST_TOKEN_RE.findall(text):
        st = sanitize_host_name(token)
        if st in STOP_TOKENS or st.isdigit() or len(st) < 3:
            continue
        if st not in seen:
            seen.append(st)
    return seen


# Build a compact human-readable message for output and the UI.
# JSON container logs often wrap the actual log message under 'log' or 'msg';
# this helper unwraps those fields when possible.
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


# Convert a parsed host-log timestamp into normalized UTC.
# If the parser said the timestamp was naive, the same wall-clock time is first
# interpreted in the event host's timezone.  Host clock skew is then subtracted
# so different machines can be compared on one timeline.
def normalize_event_time(parsed: ParsedTimestamp, host: str, resolver: HostResolver) -> dt.datetime:
    base = parsed.timestamp_utc
    if parsed.naive:
        # The parser initially stored naive timestamps as UTC just to carry a
        # datetime object around.  Here we remove that placeholder tzinfo,
        # attach the host's real timezone, then convert to UTC.
        zone = get_zone(resolver.resolve_timezone(host))
        naive_local = base.replace(tzinfo=None)
        base = naive_local.replace(tzinfo=zone).astimezone(UTC)
    skew = resolver.resolve_clock_skew(host)
    if skew:
        base = base - dt.timedelta(seconds=skew)
    return base.astimezone(UTC)



# Pull probable executable names out of an attack command line.
# This is a major lexical signal: if the attack runs 'curl' or '/usr/bin/nmap',
# nearby host-log lines mentioning that binary receive score.
def extract_command_binaries(cmd: str) -> list[str]:
    try:
        parts = shlex.split(cmd)
    except Exception:
        parts = cmd.split()

    binaries: list[str] = []
    command_starters = {"sudo", "env", "nohup", "time", "command", "builtin", "exec", "doas"}
    shell_separators = {"|", "||", "&&", ";", "&"}
    expect_command = True

    # Walk shell tokens and collect probable command positions.  This is a
    # heuristic, not a full shell parser, but handles common wrappers and
    # separators well enough for scoring.
    for raw in parts:
        token = raw.strip()
        if not token:
            continue
        if token in shell_separators:
            # After a pipe/&&/; etc., the next non-option token is probably a
            # new command binary.
            expect_command = True
            continue
        if token in command_starters:
            expect_command = True
            continue
        if token.startswith("-"):
            # Command-line options are not binaries and should not become
            # lexical signals.
            continue
        if "=" in token and not token.startswith("/"):
            continue

        candidate = sanitize_host_name(Path(token).name if "/" in token else token)
        if not candidate or candidate.isdigit() or len(candidate) < 2:
            continue
        if safe_ip_address(candidate) or safe_ip_network(candidate):
            continue

        if expect_command:
            # The first meaningful token after a separator/wrapper is treated as
            # the executable name.
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


# Build the attack-side vocabulary used for content matching.
#
# Important: this must NOT tokenize attack.raw_line directly.  raw_line is the
# complete JSON text from the attack log, so tokenizing it would turn schema
# keys such as ``type``, ``cmd``, ``parameters``, and ``metadata`` into lexical
# evidence.  That caused false matches like:
#
#     Command: sudo nmcli device set wlan1 managed
#     Matched lexical tokens: type
#
# even though ``type`` was only a JSON key, not part of the command.
#
# Therefore scoring uses only operator-controlled/value evidence: the command
# itself and string values from metadata.  The list is capped to avoid huge
# metadata blobs dominating scoring.
def extract_attack_command_lexical_terms(attack: Attack) -> list[str]:
    """Return lexical tokens that come from the attack command only.

    These are the primary lexical signals.  A correlation may only survive when
    at least one of these command-side tokens appears visibly in the host log.
    """
    terms: list[str] = []

    for binary in extract_command_binaries(attack.cmd):
        if binary not in terms and binary not in LEXICAL_STOP_TOKENS:
            terms.append(binary)

    for tok in extract_tokens(attack.cmd):
        if tok in LEXICAL_STOP_TOKENS or tok.isdigit() or len(tok) < 3:
            continue
        if tok not in terms:
            terms.append(tok)

    return terms[:40]


def extract_attack_metadata_lexical_terms(attack: Attack) -> list[str]:
    """Return weaker lexical tokens that come from attack metadata values.

    Metadata can contain useful context such as target role, scenario label, or
    technique notes, but it is also much noisier than the command.  Therefore
    metadata terms are only scored after a command term has already matched.
    """
    terms: list[str] = []

    for value in attack.metadata.values():
        if not isinstance(value, str):
            continue
        for tok in extract_tokens(value):
            if tok in LEXICAL_STOP_TOKENS or tok.isdigit() or len(tok) < 3:
                continue
            if tok not in terms:
                terms.append(tok)

    return terms[:40]


def extract_attack_lexical_terms(attack: Attack) -> list[str]:
    """Return all attack lexical terms, command first, then metadata.

    Kept as a compatibility helper for UI highlighting and older call sites.
    Scoring uses the split command/metadata helpers above so metadata cannot
    create a correlation by itself.
    """
    terms: list[str] = []
    for tok in extract_attack_command_lexical_terms(attack) + extract_attack_metadata_lexical_terms(attack):
        if tok not in terms:
            terms.append(tok)
    return terms[:40]


# Build the event-side vocabulary from only the visible host-log text.
#
# Important: this intentionally does NOT include candidate_hosts or candidate_ips.
# Those values are derived metadata produced by the parser/resolver.  If they are
# included here, a correlation can look lexical even when the visible log line
# does not contain any attack-log token.
def event_lexical_terms(event: LogEvent) -> set[str]:
    return set(extract_tokens(event.raw_line + " " + event.message))


def lexical_token_in_event_text(token: str, event_text: str, event_terms: set[str]) -> bool:
    """Return True only when an attack token visibly appears in host-log text.

    The old scoring code used plain substring checks, so short tokens could match
    inside unrelated longer words.  It also allowed token-overlap evidence from
    derived candidate host/IP metadata.  This helper keeps lexical matching tied
    to what a reviewer can actually see in the matched log line.
    """
    tok = sanitize_host_name(token)
    if not tok or tok.isdigit():
        return False
    if tok in event_terms:
        return True
    # Fall back to a component-boundary check for cases where extract_tokens()
    # and the raw text disagree around punctuation.  Host/path characters are
    # treated as part of a token, so "sh" will not match inside "shell" and
    # "apt" will not match inside "/var/log/aptitude".
    pattern = r"(?<![A-Za-z0-9_.-])" + re.escape(tok) + r"(?![A-Za-z0-9_.-])"
    return re.search(pattern, event_text, flags=re.I) is not None


def _append_unique_token(out: list[str], token: str) -> None:
    tok = sanitize_host_name(token)
    if tok and tok not in out:
        out.append(tok)


# Score command/text similarity between one Attack and one LogEvent.
# The function returns the numeric score, named score breakdown, and the exact
# visible attack-log tokens that matched in the host-log text.
def lexical_overlap_score(attack: Attack, event: LogEvent) -> tuple[float, dict[str, float], list[str], list[str], list[str]]:
    breakdown: dict[str, float] = {}
    score = 0.0
    matched_terms: list[str] = []
    matched_command_terms: list[str] = []
    matched_metadata_terms: list[str] = []

    event_text = (event.message + " " + event.raw_line).lower()
    event_terms = event_lexical_terms(event)

    command_terms = extract_attack_command_lexical_terms(attack)
    metadata_terms = extract_attack_metadata_lexical_terms(attack)

    # Strongest lexical signal: the executable from the attack command appears
    # as a visible token in the host log text.
    binary_hits: list[str] = []
    for binary in extract_command_binaries(attack.cmd):
        if binary and binary not in LEXICAL_STOP_TOKENS and lexical_token_in_event_text(binary, event_text, event_terms):
            binary_hits.append(binary)
            _append_unique_token(matched_terms, binary)
            _append_unique_token(matched_command_terms, binary)
    if binary_hits:
        val = min(BINARY_MATCH_MAX, BINARY_MATCH_BASE + BINARY_MATCH_PER_HIT * len(set(binary_hits)))
        breakdown["binary_name_match"] = val
        score += val

    # Command matches are the required gate for lexical evidence.  These are
    # derived only from attack.cmd, never from JSON keys or metadata values.
    command_exact_hits: list[str] = []
    for tok in command_terms:
        if tok in LEXICAL_STOP_TOKENS or tok.isdigit() or len(tok) < 3:
            continue
        if lexical_token_in_event_text(tok, event_text, event_terms):
            command_exact_hits.append(tok)
            _append_unique_token(matched_terms, tok)
            _append_unique_token(matched_command_terms, tok)
    if command_exact_hits:
        val = min(LEXICAL_EXACT_MAX, LEXICAL_EXACT_PER_HIT * len(set(command_exact_hits)))
        breakdown["command_lexical_match"] = val
        # Keep the old key as a compatibility alias for existing UI/export
        # helpers that look for generic lexical evidence.
        breakdown["lexical_exact_match"] = val
        score += val

    command_overlap_terms = sorted((set(command_terms) - set(command_exact_hits)) & event_terms)
    command_overlap_terms = [tok for tok in command_overlap_terms if tok not in LEXICAL_STOP_TOKENS and len(tok) >= 3]
    for tok in command_overlap_terms:
        _append_unique_token(matched_terms, tok)
        _append_unique_token(matched_command_terms, tok)
    if command_overlap_terms:
        val = min(LEXICAL_OVERLAP_MAX, LEXICAL_OVERLAP_PER_TERM * len(command_overlap_terms))
        breakdown["command_token_overlap"] = val
        breakdown["lexical_token_overlap"] = val
        score += val

    command_matched = bool(binary_hits or command_exact_hits or command_overlap_terms)

    # Metadata is weaker supporting evidence only.  It is deliberately ignored
    # unless a command token has already matched, so a command like "sleep" can
    # no longer correlate solely because metadata contained "dhcp".
    metadata_hits: list[str] = []
    if command_matched:
        command_term_set = set(command_terms)
        for tok in metadata_terms:
            if tok in command_term_set or tok in LEXICAL_STOP_TOKENS or tok.isdigit() or len(tok) < 3:
                continue
            if lexical_token_in_event_text(tok, event_text, event_terms):
                metadata_hits.append(tok)
                _append_unique_token(matched_terms, tok)
                _append_unique_token(matched_metadata_terms, tok)
        if metadata_hits:
            val = min(METADATA_LEXICAL_MAX, METADATA_LEXICAL_PER_HIT * len(set(metadata_hits)))
            breakdown["metadata_lexical_match"] = val
            score += val

    matched_total = len(set(binary_hits)) + len(set(command_exact_hits)) + len(set(command_overlap_terms)) + len(set(metadata_hits))
    if command_matched and matched_total >= LEXICAL_MULTI_MIN_MATCHES:
        bonus = min(LEXICAL_MULTI_MAX, LEXICAL_MULTI_PER_MATCH * matched_total)
        breakdown["lexical_multi_signal_bonus"] = bonus
        score += bonus

    return score, breakdown, matched_terms, matched_command_terms, matched_metadata_terms


# Extract likely target IPs, networks, tokens, and configured host names from an
# attack command and metadata.  These target hints are later compared against
# event host/candidate_hosts/IPs for stronger evidence than generic text overlap.
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


# Score all non-time evidence for one attack/event pair.
# This combines lexical evidence, target host matches, literal IP matches,
# network membership, and a small source-type hint.
def content_overlap_score(attack: Attack, event: LogEvent) -> tuple[float, dict[str, float], list[str], list[str], list[str], list[str]]:
    breakdown: dict[str, float] = {}
    matched_hosts: list[str] = []
    score = 0.0

    lexical_score, lexical_breakdown, matched_lexical_terms, matched_command_terms, matched_metadata_terms = lexical_overlap_score(attack, event)
    score += lexical_score
    breakdown.update(lexical_breakdown)

    if attack.target_hosts:
        # Exact target-host evidence is strong: the attack was aimed at a known
        # host and the event belongs to that same host.
        if event.host in attack.target_hosts:
            breakdown["target_host_exact"] = TARGET_HOST_EXACT_SCORE
            score += TARGET_HOST_EXACT_SCORE
            matched_hosts.append(event.host)
        overlap = sorted(set(attack.target_hosts) & set(event.candidate_hosts))
        if overlap:
            breakdown["target_host_candidate"] = TARGET_HOST_CANDIDATE_SCORE
            score += TARGET_HOST_CANDIDATE_SCORE
            matched_hosts.extend(h for h in overlap if h not in matched_hosts)

    ip_hits = 0
    for ip_text in attack.target_ips:
        if ip_text in event.raw_line or ip_text in event.message:
            ip_hits += 1
    if ip_hits:
        val = min(IP_LITERAL_MAX, IP_LITERAL_BASE + IP_LITERAL_PER_HIT * ip_hits)
        breakdown["ip_literal_match"] = val
        score += val

    network_hits = 0
    # Network target matching lets an attack against 10.0.0.0/24 match an event
    # that contains a concrete IP such as 10.0.0.17.
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
        val = min(NETWORK_MATCH_MAX, NETWORK_MATCH_BASE + NETWORK_MATCH_PER_HIT * network_hits)
        breakdown["network_match"] = val
        score += val

    if attack.attack_type and attack.attack_type.lower() in event.source_type.lower():
        breakdown["source_type_hint"] = SOURCE_TYPE_HINT_SCORE
        score += SOURCE_TYPE_HINT_SCORE

    return score, breakdown, matched_hosts, matched_lexical_terms, matched_command_terms, matched_metadata_terms

# Score temporal proximity between an attack and event.
# The score decays linearly across the configured search window, with small
# bonuses for events shortly after an attack and context shortly before it.
def time_score(delta_seconds: float, window_before: float, window_after: float) -> tuple[float, dict[str, float]]:
    max_window = max(window_before, window_after, 1.0)
    # Linear decay: zero delta gets full time score, while events at the edge
    # of the window get little or no time score.
    decay = max(0.0, 1.0 - min(abs(delta_seconds), max_window) / max_window)
    base = TIME_PROXIMITY_MAX_SCORE * decay
    breakdown = {"time_proximity": base}
    if 0 <= delta_seconds <= min(POST_ATTACK_BONUS_WINDOW_SECONDS, window_after):
        breakdown["post_attack_bonus"] = POST_ATTACK_BONUS_SCORE
        base += POST_ATTACK_BONUS_SCORE
    elif -PRE_ATTACK_CONTEXT_WINDOW_SECONDS <= delta_seconds < 0:
        breakdown["pre_attack_context_bonus"] = PRE_ATTACK_CONTEXT_BONUS_SCORE
        base += PRE_ATTACK_CONTEXT_BONUS_SCORE
    return base, breakdown


# Score-breakdown keys that represent real lexical evidence from the attack
# entry appearing in the host log.  Target/IP/time/source-type evidence can make
# a lexical match stronger, but it should not create a correlation by itself.
LEXICAL_MATCH_SCORE_KEYS = (
    "binary_name_match",
    "lexical_exact_match",
    "lexical_token_overlap",
    "metadata_lexical_match",
    "lexical_multi_signal_bonus",
)


def lexical_score_from_breakdown(breakdown: dict[str, float]) -> float:
    """Return only the lexical portion of a score breakdown.

    The total correlation score also contains time, target-host, IP/network, and
    source-type hints.  This helper isolates the part that proves the attack-log
    text actually appears in the host-log text.
    """
    total = 0.0
    for key in LEXICAL_MATCH_SCORE_KEYS:
        try:
            total += float((breakdown or {}).get(key, 0.0))
        except Exception:
            pass
    return total


def has_lexical_match(correlation: Correlation) -> bool:
    """Require at least one lexical match before a correlation can survive.

    Without this gate, a row could be kept because of time proximity, host/IP
    hints, or source-type hints even though no attack-log token appeared in the
    host-log line.  Those non-lexical signals are useful as supporting evidence,
    but they are too weak to count as a match on their own.
    """
    command_terms = getattr(correlation, "matched_command_terms", None)
    if command_terms is not None:
        return bool(command_terms)
    return bool(getattr(correlation, "matched_lexical_terms", []))


# Decide whether a scored pair is worth keeping.
# This is the final gate after scoring.  It mixes strong lexical evidence, total
# score, target-host evidence, and IP/network evidence into a boolean decision.
def relevance_threshold(correlation: Correlation) -> bool:
    breakdown_keys = set(correlation.score_breakdown)

    # First require actual lexical evidence.  Time-only, host-only, IP-only, or
    # source-type-only matches are discarded even if their total score would have
    # crossed one of the thresholds below.
    if not has_lexical_match(correlation):
        return False

    # A binary match passes the threshold, but only after the lexical gate above.
    if "binary_name_match" in breakdown_keys:
        return True
    if "lexical_exact_match" in breakdown_keys and correlation.abs_delta_seconds <= MAX_TIME_DELTA_SECONDS:
        return True
    if correlation.score >= RELEVANCE_SCORE_THRESHOLD:
        return True
    if correlation.score >= RELEVANCE_TARGET_HOST_THRESHOLD and correlation.target_host_matches:
        return True
    if correlation.score >= RELEVANCE_IP_NETWORK_THRESHOLD and any(k in breakdown_keys for k in ("ip_literal_match", "network_match")):
        return True
    return False


# -------------------------- config loading/building -------------------------

# Recursively find files that look like attack logs under the attack root.
def discover_attack_files(root: Path) -> list[Path]:
    found: list[Path] = []
    # rglob("*") recursively walks the entire attack root.  Any matching suffix
    # or filename containing "attack" is treated as an attack-log candidate.
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in ATTACK_LOG_SUFFIXES or "attack" in path.name.lower()):
            found.append(path)
    return sorted(found)


# Decide whether a file should be considered a host log based on extension or
# log-related filename keywords.
def looks_like_log_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS or path.suffix.lower() == ".journal":
        return True
    name = path.name.lower()
    keywords = ("syslog", "messages", "audit", "suricata", "eve", "journal", "docker", "container")
    return any(k in name for k in keywords)


# Recursively find host-log files, optionally excluding anything inside the
# attack-log root so attack logs are not double-counted as host logs.
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


# Merge optional user JSON config with automatically discovered host profiles.
# User config can refine timezones, clock skew, aliases, IPs, and path hints
# without losing discovered hosts.
def load_config(config_path: Optional[Path], discovered_hosts: dict[str, HostProfile], default_timezone: str) -> ConfigBundle:
    # Copy discovered profiles so loading config does not mutate the discovery
    # result object passed by the caller.
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
            # Merge configured values into discovered values.  set() removes
            # duplicates; sorted() gives stable generated config output.
            existing.aliases = sorted(set(existing.aliases + [sanitize_host_name(x) for x in host_cfg.get("aliases", []) if str(x).strip()]))
            existing.ip_addresses = sorted(set(existing.ip_addresses + [str(x).strip() for x in host_cfg.get("ip_addresses", []) if str(x).strip()]))
            existing.path_hints = sorted(set(existing.path_hints + [sanitize_host_name(x) for x in host_cfg.get("path_hints", []) if str(x).strip()]))
            existing.notes = str(host_cfg.get("notes", existing.notes))
            config.hosts[key] = existing
    for host, profile in config.hosts.items():
        if not profile.timezone:
            profile.timezone = config.default_timezone
    return config


# Write the effective host configuration to disk.
# This gives the user a concrete file they can edit and pass back with
# --host-config on a later run.
def write_generated_config(path: Path, config: ConfigBundle) -> None:
    payload = {
        "default_timezone": config.default_timezone,
        "default_clock_skew_seconds": config.default_clock_skew_seconds,
        "default_attacker_timezone": (config.raw_config or {}).get("default_attacker_timezone", "UTC"),
        "default_utc_offset_hours": (config.raw_config or {}).get("default_utc_offset_hours", 0),
        "attacker_hosts": (config.raw_config or {}).get("attacker_hosts", {}),
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


# Make an initial host list from log file paths.
# This is a bootstrap step before explicit config is loaded; it lets the script
# work on directory trees that group logs by host.
def discover_hosts_from_logs(log_root: Path, attack_root: Optional[Path], default_timezone: str) -> dict[str, HostProfile]:
    hosts: dict[str, HostProfile] = {}
    for path in discover_log_files(log_root, attack_root):
        candidates = host_candidates_from_path(path, log_root)
        if not candidates:
            continue
        host = candidates[0]
        profile = hosts.setdefault(host, HostProfile(name=host, timezone=default_timezone))
        for hint in candidates:
            if hint and hint not in profile.path_hints:
                profile.path_hints.append(hint)
    return hosts


# ------------------------------- loading -----------------------------------

# Load one attack-log file into Attack objects.
# Each non-empty JSON object line with a start-datetime becomes one Attack.
# Invalid/non-matching lines are skipped.
def load_attack_file(path: Path, resolver: HostResolver, attack_root: Optional[Path] = None, config: Optional[Any] = None) -> list[Attack]:
    attacks: list[Attack] = []
    attacker_host = guess_attacker_host_from_path(path, attack_root or path.parent)

    raw_cfg: dict[str, Any] = {}
    if isinstance(config, dict):
        raw_cfg = config
    elif hasattr(config, "raw_config") and isinstance(getattr(config, "raw_config"), dict):
        raw_cfg = getattr(config, "raw_config")

    attacker_cfg = (raw_cfg.get("attacker_hosts", {}) or {}).get(attacker_host, {})
    attacker_timezone = str(
        attacker_cfg.get(
            "timezone",
            raw_cfg.get("default_attacker_timezone", "UTC"),
        )
    )
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
            parsed = parse_attack_datetime(ts, attacker_timezone)
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
            # Extract attack-side target hints immediately so later scoring can
            # compare them against parsed host-log hints.
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


# Convert a binary systemd journal file to text using journalctl.
# The rest of the parser only handles text lines, so binary journals are
# normalized through this external command first.
def run_journalctl_export(path: Path) -> list[str]:
    cmd = ["journalctl", f"--file={path}", "-o", "short-iso-precise", "--no-pager"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "journalctl failed")
    return result.stdout.splitlines()


def file_starts_with_systemd_journal_magic(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(8) == b"LPKSHHRH"
    except Exception:
        return False


def is_probably_binary_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:BINARY_SAMPLE_BYTES]
    except Exception:
        return False
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    control_bytes = 0
    for value in sample:
        if value in (9, 10, 13):
            continue
        if value < 32:
            control_bytes += 1
    return (control_bytes / len(sample)) >= BINARY_CONTROL_BYTE_RATIO


def should_try_journalctl(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        path.suffix.lower() == ".journal"
        or file_starts_with_systemd_journal_magic(path)
        or ("journal" in lower_name and is_probably_binary_file(path))
    )


# Load one host-log file into LogEvent objects.
# Text logs are read line by line.  Binary .journal files are first exported via
# journalctl.  Lines without parseable timestamps are skipped by default for performance.
# If include_untimestamped=True, they are loaded so content matching can find
# them; they receive zero time-correlation score later.
def load_log_file(path: Path, root: Path, default_year: int, resolver: HostResolver, include_untimestamped: bool = False) -> list[LogEvent]:
    events: list[LogEvent] = []
    path_host = resolver.host_from_path(path, root) or "unknown-host"

    def convert_line(line: str, line_number: int, source_type_override: Optional[str] = None) -> Optional[LogEvent]:
        # This nested function contains the common text-line -> LogEvent logic
        # used for both ordinary text logs and journalctl-exported lines.
        global UNPARSABLE_LINE_COUNT

        parsed = try_parse_line_timestamp(line, default_year)
        timestamp_missing = parsed is None

        line_host = guess_host_from_line(line)
        host = resolver.canonicalize_host(line_host or path_host)

        if parsed:
            normalized_ts = normalize_event_time(parsed, host, resolver)
            raw_timestamp = parsed.raw_text
            parser_name = parsed.parser_name
        else:
            # Count every line whose timestamp cannot be parsed.  Depending on
            # the CLI flag, either keep it for content-only scoring or drop it
            # immediately so it never reaches the expensive correlation stage.
            UNPARSABLE_LINE_COUNT += 1
            if not include_untimestamped:
                return None
            # Keep the line as a LogEvent instead of dropping it.  The sentinel
            # timestamp is only a placeholder; correlate() checks
            # extra["timestamp_missing"] and gives this event a zero time score.
            normalized_ts = UNKNOWN_TIMESTAMP_SENTINEL
            raw_timestamp = ""
            parser_name = "missing"

        source_type = source_type_override or detect_source_type(path, line)
        candidate_ips = extract_ips(line)
        candidate_tokens = extract_tokens(line)
        # Host candidates combine tokens from the line, IP mappings, and path
        # inference.  These are not guaranteed true hosts; they are evidence for
        # scoring and display.
        candidate_hosts = resolver.candidate_hosts_for_tokens(candidate_tokens + candidate_ips, path=path, root=root)
        if host not in candidate_hosts:
            candidate_hosts.insert(0, host)
        return LogEvent(
            event_id=f"{path}:{line_number}",
            timestamp=normalized_ts,
            raw_timestamp=raw_timestamp,
            host=host,
            source_type=source_type,
            file_path=str(path),
            line_number=line_number,
            message=preview_message_from_line(line),
            raw_line=line.rstrip("\n"),
            extra={"timestamp_parser": parser_name, "timestamp_missing": timestamp_missing},
            candidate_hosts=candidate_hosts,
            candidate_ips=candidate_ips,
        )

    global JOURNALCTL_CONVERTED_FILE_COUNT, BINARY_LOG_FILE_SKIPPED_COUNT

    if should_try_journalctl(path):
        try:
            lines = run_journalctl_export(path)
            JOURNALCTL_CONVERTED_FILE_COUNT += 1
        except Exception as exc:
            print(f"[warn] failed to export binary journal with journalctl: {path}: {exc}", file=sys.stderr)
            BINARY_LOG_FILE_SKIPPED_COUNT += 1
            return events
        for line_number, line in enumerate(lines, start=1):
            ev = convert_line(line, line_number, "journalctl-export")
            if ev:
                events.append(ev)
        return events

    if is_probably_binary_file(path):
        print(f"[warn] skipping binary-looking non-journal log file: {path}", file=sys.stderr)
        BINARY_LOG_FILE_SKIPPED_COUNT += 1
        return events

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            ev = convert_line(line, line_number)
            if ev:
                events.append(ev)
    return events


# Load every discovered attack file, warning and continuing if one file fails.
def load_all_attacks(attack_root: Path, resolver: HostResolver, config: Optional[dict[str, Any]] = None) -> list[Attack]:
    attacks: list[Attack] = []
    for path in discover_attack_files(attack_root):
        try:
            attacks.extend(load_attack_file(path, resolver, attack_root=attack_root, config=config))
        except Exception as exc:
            print(f"[warn] failed to read attack log: {path}: {exc}", file=sys.stderr)
    return sorted(attacks, key=lambda x: x.timestamp)


# Load every discovered host-log file, warning and continuing if one file fails.
def load_all_events(log_root: Path, attack_root: Optional[Path], default_year: int, resolver: HostResolver, include_untimestamped: bool = False) -> list[LogEvent]:
    events: list[LogEvent] = []
    for path in discover_log_files(log_root, attack_root):
        try:
            events.extend(load_log_file(path, log_root, default_year, resolver, include_untimestamped))
        except Exception:
            print(f"[warn] failed to read log file: {path}", file=sys.stderr)
    return sorted(events, key=lambda x: x.timestamp)


# ------------------------------ correlation --------------------------------

# Main correlation algorithm.
# For each attack, scan only events in the configured time window, score each
# candidate event, keep relevant matches, and retain the top N per attack.
def correlate(attacks: list[Attack], events: list[LogEvent], window_before: float, window_after: float, max_per_attack: int) -> list[Correlation]:
    correlations: list[Correlation] = []

    # Timestamped events keep the original efficient sliding-window scan.
    # Untimestamped events are kept separately because the window comparison
    # cannot apply to them; they are scored against each attack with time score
    # forced to zero.
    timed_events = [e for e in events if not (e.extra or {}).get("timestamp_missing")]
    untimed_events = [e for e in events if (e.extra or {}).get("timestamp_missing")]

    # Sort events once so each attack can scan a contiguous time window.
    # start_idx advances monotonically as attacks move forward in time, avoiding
    # a full scan from the beginning for every timestamped attack/event pair.
    events_sorted = sorted(timed_events, key=lambda e: e.timestamp)
    start_idx = 0

    def build_correlation(attack: Attack, event: LogEvent, force_zero_time_score: bool = False) -> Correlation:
        # The synthetic delta for untimestamped rows is deliberately larger
        # than the configured windows/cap.  That prevents relevance_threshold()
        # from treating a lexical match as time-close, while still keeping the
        # numeric output finite and JSON/CSV-friendly.
        if force_zero_time_score:
            delta = max(window_before, window_after, MAX_TIME_DELTA_SECONDS) + 1.0
            abs_delta = delta
            t_score = 0.0
            t_breakdown = {"time_proximity": 0.0}
        else:
            delta = (event.timestamp - attack.timestamp).total_seconds()
            abs_delta = abs(delta)
            t_score, t_breakdown = time_score(delta, window_before, window_after)

        c_score, c_breakdown, matched_hosts, matched_lexical_terms, matched_command_terms, matched_metadata_terms = content_overlap_score(attack, event)
        raw_lexical_score = lexical_score_from_breakdown(c_breakdown)

        # Content evidence is doubled relative to the raw content score.
        # Time still contributes for timestamped events, but lexical/target
        # evidence dominates the final total.  raw_lexical_score is recorded
        # separately so correlations with no attack-log text match can be
        # discarded by relevance_threshold().
        weighted_time_score = t_score
        weighted_content_score = c_score * CONTENT_SCORE_WEIGHT
        weighted_lexical_score = raw_lexical_score * CONTENT_SCORE_WEIGHT
        total = weighted_time_score + weighted_content_score
        breakdown = {
            **t_breakdown,
            **c_breakdown,
            "raw_lexical_score": raw_lexical_score,
            "weighted_time_score": weighted_time_score,
            "weighted_content_score": weighted_content_score,
            "weighted_lexical_score": weighted_lexical_score,
        }

        return Correlation(
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
            matched_lexical_terms=matched_lexical_terms,
            matched_command_terms=matched_command_terms,
            matched_metadata_terms=matched_metadata_terms,
        )

    for attack in sorted(attacks, key=lambda a: a.timestamp):
        # Build the broad user-configured time window around the attack.  A
        # later hard cap (MAX_TIME_DELTA_SECONDS) further restricts timestamped
        # candidates.
        lower = attack.timestamp - dt.timedelta(seconds=window_before)
        upper = attack.timestamp + dt.timedelta(seconds=window_after)

        # Discard timestamped events that are too old for this and all later
        # attacks.  Untimestamped events are handled after this window scan.
        while start_idx < len(events_sorted) and events_sorted[start_idx].timestamp < lower:
            start_idx += 1

        matches: list[Correlation] = []
        idx = start_idx

        while idx < len(events_sorted) and events_sorted[idx].timestamp <= upper:
            event = events_sorted[idx]
            delta = (event.timestamp - attack.timestamp).total_seconds()
            abs_delta = abs(delta)

            if abs_delta > MAX_TIME_DELTA_SECONDS:
                # Even inside the broad window, this strict cap rejects
                # timestamped events before spending time on content scoring.
                idx += 1
                continue

            corr = build_correlation(attack, event)
            if relevance_threshold(corr):
                matches.append(corr)
            idx += 1

        # Lines without parseable timestamps cannot be filtered by time.  By
        # default they are not loaded at all, because comparing every such line
        # against every attack can be very expensive.  If the user enables
        # --process-untimestamped-lines, they are scored here with zero time
        # contribution instead of being dropped.
        for event in untimed_events:
            corr = build_correlation(attack, event, force_zero_time_score=True)
            if relevance_threshold(corr):
                matches.append(corr)

        # Keep only the strongest matches for this attack.  Ties prefer smaller
        # time deltas, then stable host/file/line ordering.
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

# Convert an Attack dataclass into a JSON/CSV-friendly dictionary.
def attack_summary_row(attack: Attack) -> dict[str, Any]:
    return {
        "attack_id": attack.attack_id,
        "timestamp": attack.timestamp.isoformat(),
        "type": attack.attack_type,
        "cmd": attack.cmd,
        "source_file": attack.source_file,
        "line_number": attack.line_number,
        "raw_line": attack.raw_line,
        "attacker_host": attack.attacker_host,
        "metadata": attack.metadata,
        "target_ips": attack.target_ips,
        "target_networks": attack.target_networks,
        "target_tokens": attack.target_tokens,
        "target_hosts": attack.target_hosts,
    }


# Convert a LogEvent dataclass into a JSON-friendly dictionary.
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


# Convert a Correlation dataclass into a JSON/CSV-friendly dictionary.
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
        "matched_lexical_terms": getattr(c, "matched_lexical_terms", []),
        "matched_command_terms": getattr(c, "matched_command_terms", []),
        "matched_metadata_terms": getattr(c, "matched_metadata_terms", []),
        "attack_file": c.attack_file,
        "attack_line": c.attack_line,
        "attack_raw_line": c.attack_raw_line,
        "event_file": c.event_file,
        "event_line": c.event_line,
    }


def _as_list(value: Any) -> list[Any]:
    """Normalize JSON fields that should be lists when loading saved output."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_saved_datetime(value: Any) -> dt.datetime:
    """Parse saved ISO timestamps from correlations.json back into datetime objects."""
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = parse_iso_datetime(str(value))
    if not parsed:
        return dt.datetime.fromtimestamp(0, tz=UTC)
    return parsed.astimezone(UTC)


def attack_from_saved_row(row: dict[str, Any]) -> Attack:
    """Recreate an Attack object from the exported correlations.json attack row."""
    return Attack(
        attack_id=str(row.get("attack_id", "")),
        timestamp=_parse_saved_datetime(row.get("timestamp")),
        attack_type=str(row.get("type", row.get("attack_type", "unknown"))),
        cmd=str(row.get("cmd", row.get("attack_cmd", ""))),
        source_file=str(row.get("source_file", row.get("attack_file", ""))),
        line_number=int(row.get("line_number", row.get("attack_line", 0)) or 0),
        metadata=row.get("metadata", {}) if isinstance(row.get("metadata", {}), dict) else {},
        raw_line=str(row.get("raw_line", row.get("attack_raw_line", ""))),
        target_hosts=[str(x) for x in _as_list(row.get("target_hosts"))],
        target_ips=[str(x) for x in _as_list(row.get("target_ips"))],
        target_networks=[str(x) for x in _as_list(row.get("target_networks"))],
        target_tokens=[str(x) for x in _as_list(row.get("target_tokens"))],
        attacker_host=str(row.get("attacker_host", "unknown-attacker")),
    )


def correlation_from_saved_row(row: dict[str, Any]) -> Correlation:
    """Recreate a Correlation object from the exported correlations.json row."""
    breakdown = row.get("score_breakdown", {})
    if isinstance(breakdown, str):
        try:
            breakdown = json.loads(breakdown)
        except Exception:
            breakdown = {}
    if not isinstance(breakdown, dict):
        breakdown = {}
    return Correlation(
        correlation_id=str(row.get("correlation_id", "")),
        attack_id=str(row.get("attack_id", "")),
        event_id=str(row.get("event_id", "")),
        attacker_host=str(row.get("attacker_host", "unknown-attacker")),
        attack_time=_parse_saved_datetime(row.get("attack_time")),
        event_time=_parse_saved_datetime(row.get("event_time")),
        delta_seconds=float(row.get("delta_seconds", 0.0) or 0.0),
        abs_delta_seconds=float(row.get("abs_delta_seconds", abs(float(row.get("delta_seconds", 0.0) or 0.0))) or 0.0),
        attack_file=str(row.get("attack_file", "")),
        attack_line=int(row.get("attack_line", 0) or 0),
        attack_raw_line=str(row.get("attack_raw_line", "")),
        event_file=str(row.get("event_file", "")),
        event_line=int(row.get("event_line", 0) or 0),
        host=str(row.get("host", "unknown-host")),
        attack_type=str(row.get("attack_type", "unknown")),
        attack_cmd=str(row.get("attack_cmd", "")),
        attack_targets=[str(x) for x in _as_list(row.get("attack_targets"))],
        target_host_matches=[str(x) for x in _as_list(row.get("target_host_matches"))],
        event_message=str(row.get("event_message", "")),
        event_source_type=str(row.get("event_source_type", "")),
        score=float(row.get("score", 0.0) or 0.0),
        score_breakdown={str(k): float(v) for k, v in breakdown.items() if isinstance(v, (int, float))},
        matched_lexical_terms=[str(x) for x in _as_list(row.get("matched_lexical_terms"))],
        matched_command_terms=[str(x) for x in _as_list(row.get("matched_command_terms"))],
        matched_metadata_terms=[str(x) for x in _as_list(row.get("matched_metadata_terms"))],
    )


def load_existing_outputs(out_dir: Path) -> tuple[list[Attack], list[Correlation], dict[str, Any]]:
    """Load previously computed correlations from out_dir/correlations.json.

    This supports a UI-only review mode that skips attack/log discovery, parsing,
    scoring, and export.  The browser only needs Attack and Correlation objects,
    so those are reconstructed from the saved JSON rows.
    """
    path = out_dir / "correlations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    attacks = [attack_from_saved_row(x) for x in data.get("attacks", []) if isinstance(x, dict)]
    correlations = [correlation_from_saved_row(x) for x in data.get("correlations", []) if isinstance(x, dict)]
    known_attack_ids = {a.attack_id for a in attacks}
    for c in correlations:
        if c.attack_id not in known_attack_ids:
            attacks.append(
                Attack(
                    attack_id=c.attack_id,
                    timestamp=c.attack_time,
                    attack_type=c.attack_type,
                    cmd=c.attack_cmd,
                    source_file=c.attack_file,
                    line_number=c.attack_line,
                    metadata={},
                    raw_line=c.attack_raw_line,
                    attacker_host=c.attacker_host,
                )
            )
            known_attack_ids.add(c.attack_id)
    return sorted(attacks, key=lambda a: a.timestamp), correlations, data.get("summary", {}) if isinstance(data.get("summary", {}), dict) else {}


# Write a Python object as pretty JSON with UTF-8 output.
def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# Write correlations as a flat CSV.
# Lists and dictionaries are stringified so spreadsheet tools can open the file.
def write_correlation_csv(path: Path, correlations: list[Correlation]) -> None:
    fieldnames = [
        "correlation_id", "attack_id", "event_id", "attacker_host", "attack_time", "event_time", "delta_seconds",
        "abs_delta_seconds", "host", "attack_type", "attack_cmd", "attack_targets", "target_host_matches",
        "event_source_type", "event_message", "score", "score_breakdown", "matched_lexical_terms", "matched_command_terms", "matched_metadata_terms", "attack_file", "attack_line",
        "attack_raw_line", "event_file", "event_line",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        # extrasaction="ignore" protects the CSV writer if correlation_row()
        # contains fields not listed in fieldnames.
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in correlations:
            try:
                row = correlation_row(c)
                row["attack_targets"] = ";".join(str(x) for x in row.get("attack_targets", []))
                row["target_host_matches"] = ";".join(str(x) for x in row.get("target_host_matches", []))
                row["score_breakdown"] = json.dumps(row.get("score_breakdown", {}), ensure_ascii=False, sort_keys=True)
                row["matched_lexical_terms"] = ";".join(str(x) for x in row.get("matched_lexical_terms", []))
                row["matched_command_terms"] = ";".join(str(x) for x in row.get("matched_command_terms", []))
                row["matched_metadata_terms"] = ";".join(str(x) for x in row.get("matched_metadata_terms", []))
                row["attack_raw_line"] = str(row.get("attack_raw_line", "")).replace(chr(0), "")
                row["event_message"] = str(row.get("event_message", "")).replace(chr(0), "")
                writer.writerow(row)
            except Exception as exc:
                print(f"[warn] failed to write correlation row for {getattr(c, 'correlation_id', '<unknown>')}: {exc}", file=sys.stderr)
                continue


# Write a readable text report organized by attack step.
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
# Write all output artifacts: global JSON/CSV/text, generated config, per-host
# JSON/CSV/text files, and a small summary JSON.
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
                "unparsable_lines": UNPARSABLE_LINE_COUNT,
                "journalctl_converted_files": JOURNALCTL_CONVERTED_FILE_COUNT,
                "binary_log_files_skipped": BINARY_LOG_FILE_SKIPPED_COUNT,
                "created_at": dt.datetime.now(tz=UTC).isoformat(),
            },
            "attacks": [attack_summary_row(a) for a in attacks],
            "events": [event_summary_row(e) for e in events],
            "correlations": [correlation_row(c) for c in correlations],
        },
    )
    write_correlation_csv(out_dir / "correlations.csv", correlations)
    write_human_summary(out_dir / "correlations_human.txt", attacks, correlations)

    # Per-host exports let an analyst inspect evidence host by host instead of
    # reading one global correlation file.
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
            "unparsable_lines": UNPARSABLE_LINE_COUNT,
            "journalctl_converted_files": JOURNALCTL_CONVERTED_FILE_COUNT,
            "binary_log_files_skipped": BINARY_LOG_FILE_SKIPPED_COUNT,
            "per_host": host_summary,
            "created_at": dt.datetime.now(tz=UTC).isoformat(),
            "max_time_delta_seconds": MAX_TIME_DELTA_SECONDS,
        },
    )



# ---------------------------------- tui ------------------------------------

# Remove NUL/control characters before previewing text in files or curses.
# Terminals can behave badly when raw control bytes are displayed, and the same
# cleanup is useful for both context previews and UI rendering.
def sanitize_preview_text(value: str) -> str:
    value = str(value).replace(chr(0), "")
    cleaned = []
    for ch in value:
        code = ord(ch)
        if ch == "\t" or code >= 32:
            cleaned.append(ch)
        else:
            cleaned.append("?")
    return "".join(cleaned)


# Read a small window of source-file lines around a matched log line for preview.
# This powers the ncurses UI and human-readable context display.
def read_context_lines(path: str, line_number: int, radius: int = 3) -> list[str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return [f"[missing file] {path}"]
    start = max(1, line_number - radius)
    end = line_number + radius
    out: list[str] = []

    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for idx, line in enumerate(fh, start=1):
                if idx < start:
                    continue
                if idx > end:
                    break
                prefix = ">" if idx == line_number else " "
                out.append(f"{prefix}{idx:6d} {sanitize_preview_text(line.rstrip())}")
    except Exception as exc:
        out.append(f"[unable to preview] {exc}")
    return out


def _collect_string_values(value: Any) -> list[str]:
    """Return string leaves from parsed attack-log JSON values, not JSON keys.

    This keeps green UI highlighting tied to evidence that actually came from
    an attack-log entry value, such as the command, attack type, metadata values,
    IPs, or target strings.  It intentionally avoids JSON field names like
    ``cmd`` or ``metadata`` because those are schema words, not evidence.
    """
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            values.extend(_collect_string_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_string_values(child))
    elif isinstance(value, (int, float)):
        values.append(str(value))
    return values


# Very small UI-only stoplist.  This is intentionally much smaller than
# LEXICAL_STOP_TOKENS because UI highlighting should show command words like
# curl, sudo, bash, and nmap in green when they came from the attack log.
# The broader scoring stoplist is still used for correlation scoring; this only
# affects what the human sees in the preview pane.
UI_HIGHLIGHT_STOP_TOKENS = {"the", "and", "for", "with", "from", "into", "that", "this", "false", "true", "null"}


def _highlight_tokens_from_attack_value(text: str) -> list[str]:
    """Extract display-highlight tokens from an attack-log value.

    This deliberately does not call extract_tokens(), because extract_tokens()
    removes common command words such as curl/nmap/bash.  Those words are too
    common for scoring, but they are exactly the evidence the UI should mark
    green when they appear in a matched host-log line.
    """
    out: list[str] = []
    for token in HOST_TOKEN_RE.findall(str(text)):
        st = sanitize_host_name(token)
        if len(st) < 3 or st.isdigit() or st in UI_HIGHLIGHT_STOP_TOKENS:
            continue
        if st not in out:
            out.append(st)
    for ip_text in extract_ips(str(text)):
        if ip_text not in out:
            out.append(ip_text)
    return out


# Build the list of attack-log tokens to highlight in host-log preview lines.
# Green is reserved for lexical evidence from attack-log entry values only.
# Generic host-log syntax is highlighted blue elsewhere, and derived host guesses
# are not added here unless they literally appeared in the attack-log value text.
def _preview_keywords(corr: Optional[Correlation]) -> list[str]:
    if not corr:
        return []

    # Prefer the exact scoring matches.  This makes the UI line up with the
    # lexical gate: green in host-log context means "this exact attack-log token
    # is why the correlation survived", not merely "this word appeared somewhere
    # in the attack JSON".
    matched_terms = [sanitize_host_name(x) for x in getattr(corr, "matched_lexical_terms", []) or []]
    matched_terms = [x for x in matched_terms if x]
    if matched_terms:
        out: list[str] = []
        for term in matched_terms:
            if term not in out:
                out.append(term)
        return out[:80]

    # Backward-compatible fallback for older correlations.json files that do not
    # contain matched_lexical_terms yet.  New correlations should not normally
    # reach this path.
    out: list[str] = []
    raw_attack_line = getattr(corr, "attack_raw_line", "") or ""

    sources: list[str] = []
    try:
        parsed = json.loads(raw_attack_line)
    except Exception:
        parsed = None

    if parsed is not None:
        sources.extend(_collect_string_values(parsed))
    else:
        sources.append(raw_attack_line)

    if getattr(corr, "attack_cmd", ""):
        sources.append(corr.attack_cmd)
    if getattr(corr, "attack_type", ""):
        sources.append(corr.attack_type)

    for source in sources:
        for piece in _highlight_tokens_from_attack_value(source):
            if piece not in out:
                out.append(piece)

    return out[:80]


SEARCH_ENCODING_MODES = ("utf8", "hex", "utf16")


def _compact_hex(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _encoded_search_needles(query: str, mode: str) -> list[str]:
    if not query:
        return []
    if mode == "utf8":
        return [query.lower()]
    if mode == "hex":
        # Accept either a literal hex query like "636d64" or a normal string
        # that should be converted to its UTF-8 byte representation.
        compact = _compact_hex(query)
        needles = []
        if compact and len(compact) % 2 == 0:
            needles.append(compact)
        needles.append(query.encode("utf-8", errors="replace").hex())
        return sorted(set(needles), key=len, reverse=True)
    if mode == "utf16":
        # Include both common byte orders.  This is useful when logs contain
        # command text as a hex dump of UTF-16 data.
        return sorted({
            query.encode("utf-16le", errors="replace").hex(),
            query.encode("utf-16be", errors="replace").hex(),
        }, key=len, reverse=True)
    return [query.lower()]


def _search_matches_line(line: str, query: str, mode: str) -> bool:
    if not query:
        return False
    safe = sanitize_preview_text(line)
    lowered = safe.lower()
    if mode == "utf8":
        return query.lower() in lowered

    compact_line_hex_text = _compact_hex(lowered)
    line_utf8_hex = safe.encode("utf-8", errors="replace").hex()
    for needle in _encoded_search_needles(query, mode):
        if not needle:
            continue
        if needle in compact_line_hex_text or needle in line_utf8_hex:
            return True
    return False


def _search_spans(line: str, query: str, mode: str) -> list[tuple[int, int, str]]:
    if not query:
        return []
    safe = sanitize_preview_text(line)
    lowered = safe.lower()
    spans: list[tuple[int, int, str]] = []

    if mode == "utf8":
        needle = query.lower()
        pos = 0
        while needle:
            idx = lowered.find(needle, pos)
            if idx == -1:
                break
            spans.append((idx, idx + len(needle), "bold"))
            pos = idx + len(needle)
        return spans

    # For encoded searches, there is usually no clean character-position mapping
    # from the encoded byte pattern back to the displayed text.  When a line
    # matches through its hex/UTF-16 representation, mark the whole displayed
    # line as a search hit using bold/reverse styling rather than green.
    if _search_matches_line(safe, query, mode):
        return [(0, len(safe), "bold")]
    return []


def _correlation_log_text(corr: Correlation) -> str:
    pieces = [corr.event_message or ""]
    pieces.extend(read_context_lines(corr.event_file, corr.event_line, radius=0))
    return "\n".join(pieces)


# Render one line with simple keyword highlighting.
# This older helper is kept alongside the newer semantic highlighter.
def _render_highlighted_line(win, y: int, x: int, width: int, line: str, keywords: list[str], highlight_attr: int) -> None:
    safe = sanitize_preview_text(line)
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



# Sum just the lexical portions of a correlation's score.
# The UI uses this to visually emphasize correlations with above-average
# content evidence for the currently selected attack.
def correlation_lexical_score(corr: Correlation) -> float:
    return lexical_score_from_breakdown(corr.score_breakdown or {})


# Compute the average lexical score across a list of correlations.
def average_lexical_score(correlations: list[Correlation]) -> float:
    if not correlations:
        return 0.0
    vals = [correlation_lexical_score(c) for c in correlations]
    return sum(vals) / len(vals) if vals else 0.0


# Build the right-hand preview pane text for the currently selected correlation.
# Collapsed mode shows the most important details; expanded mode includes the
# full event message and scoring breakdown.
def build_preview_lines(corr: Optional[Correlation], collapsed: bool = True) -> list[str]:
    if not corr:
        return ["No selection"]

    lines: list[str] = [
        f"Host:  {corr.host}",
        f"Attacker: {getattr(corr, 'attacker_host', 'unknown-attacker')}",
        f"Time:  {corr.event_time.isoformat()}",
        f"Delta: {corr.delta_seconds:.3f}s    Score: {corr.score:.2f}",
        f"Command: {corr.attack_cmd}",
        f"Matched command tokens: {', '.join(getattr(corr, 'matched_command_terms', []) or ['<none>'])}",
        f"Matched metadata tokens: {', '.join(getattr(corr, 'matched_metadata_terms', []) or ['<none>'])}",
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
        lines.append(sanitize_preview_text(corr.event_message))
        lines.append("Scoring breakdown:")
        pretty = pp.pformat(breakdown, width=88, compact=False, sort_dicts=True)
        lines.extend(sanitize_preview_text(pretty).splitlines())

    return lines




# Generic host-log syntax highlights.  These used to be green; they are now blue
# so green can be reserved for direct attack-log lexical matches.
HILITE_BLUE_PATTERNS = [
    r'\bname="[^"]+"',
    r"\bcomm=[^\s]+",
    r"\bexe=[^\s]+",
    r"\bcmd=[^\s].*$",
    r"\b(?:sudo|curl|wget|nc|ncat|netcat|nmap|ssh|scp|ftp|python|python3|bash|sh|zsh|perl|ruby|php|busybox|systemctl|iptables|ip|ss|netstat|tcpdump|socat)\b",
    r"\b(?:/[A-Za-z0-9._-]+)+\b",
    r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b",
]


# Find spans worth highlighting even if they are not attack keywords.
# Examples include executables, paths, IP addresses, and error words.
def _collect_semantic_spans(line: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    safe = sanitize_preview_text(line)

    for pat in HILITE_BLUE_PATTERNS:
        for m in re.finditer(pat, safe):
            spans.append((m.start(), m.end(), "blue"))

    for m in re.finditer(r'\b(?:error|failed|failure|denied|invalid|refused|blocked|drop(?:ped)?|alert)\b', safe, flags=re.I):
        spans.append((m.start(), m.end(), "bold"))

    return spans


# Merge overlapping highlight spans while respecting priority.
# Green keyword matches should win over blue semantic matches, which should win
# over generic bold/error highlighting.
def _merge_spans(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    if not spans:
        return []

    # Higher priority wins at every character position.  This fixes the case
    # where a broad blue semantic span, such as ``cmd=...`` or a full path,
    # starts before a green lexical match and would otherwise occupy the region
    # first.  Green is attack-log evidence, so it must always overpower blue.
    priority = {"blue": 1, "bold": 2, "green": 3}
    spans = [s for s in spans if s[0] < s[1]]
    if not spans:
        return []

    max_end = max(e for _s, e, _kind in spans)
    chosen: list[Optional[str]] = [None] * max_end

    for s, e, kind in spans:
        kind_priority = priority.get(kind, 0)
        for pos in range(max(0, s), min(e, max_end)):
            current = chosen[pos]
            if current is None or kind_priority > priority.get(current, 0):
                chosen[pos] = kind

    merged: list[tuple[int, int, str]] = []
    pos = 0
    while pos < max_end:
        kind = chosen[pos]
        if kind is None:
            pos += 1
            continue
        end = pos + 1
        while end < max_end and chosen[end] == kind:
            end += 1
        merged.append((pos, end, kind))
        pos = end

    return merged


# Render one curses line with both attack-keyword and semantic highlighting.
# It walks through the merged spans and writes normal/highlighted chunks in order.
def _render_semantic_highlighted_line(
    win,
    y: int,
    x: int,
    width: int,
    line: str,
    keywords: list[str],
    blue_attr: int,
    green_attr: int,
    bold_attr: int,
    search_query: str = "",
    search_encoding: str = "utf8",
    forced_green_spans: Optional[list[tuple[int, int]]] = None,
) -> None:
    safe = sanitize_preview_text(line)
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

    for s_idx, e_idx in forced_green_spans or []:
        spans.append((max(0, s_idx), min(len(safe), e_idx), "green"))

    spans.extend(_collect_semantic_spans(safe))
    spans.extend(_search_spans(safe, search_query, search_encoding))
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

# ---------------------------------------------------------------------------
# ncurses browser for interactive review.
#
# The browser presents three panes:
#   left:   attack steps
#   middle: correlations for the selected attack
#   right:  detailed preview/context for the selected correlation
# It does not change correlation results; it is only a viewer over the data
# produced by correlate().
# ---------------------------------------------------------------------------
class CorrelationBrowser:
    # Build lookup indexes once so repeated correlation checks are fast.
    # These maps/lists are used for alias normalization, direct IP lookup,
    # CIDR-network lookup, and path-hint matching.
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

    # Return the currently selected Attack, or None when there are no attacks.
    def current_attack(self) -> Optional[Attack]:
        if not self.attacks:
            return None
        return self.attacks[self.attack_idx]

    # Return correlations belonging to the currently selected attack.
    def current_correlations(self) -> list[Correlation]:
        attack = self.current_attack()
        if not attack:
            return []
        return self.by_attack.get(attack.attack_id, [])

    # Return the selected correlation and clamp the index into valid range.
    def current_correlation(self) -> Optional[Correlation]:
        rows = self.current_correlations()
        if not rows:
            return None
        self.corr_idx = max(0, min(self.corr_idx, len(rows) - 1))
        return rows[self.corr_idx]

    # Start curses safely; curses.wrapper restores the terminal on exit/crash.
    def run(self) -> None:
        curses.wrapper(self._main)

    def _prompt_search(self, stdscr, current_query: str) -> str:
        # A small one-line search prompt.  It uses curses' built-in line editor
        # so Backspace/Enter behave normally in most terminals.
        max_y, max_x = stdscr.getmaxyx()
        prompt = "Search logs: "
        stdscr.move(max_y - 1, 0)
        stdscr.clrtoeol()
        stdscr.addnstr(max_y - 1, 0, prompt, max_x - 1, curses.A_STANDOUT)
        curses.echo()
        try:
            curses.curs_set(1)
        except Exception:
            pass
        try:
            raw = stdscr.getstr(max_y - 1, len(prompt), max(1, max_x - len(prompt) - 1))
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = current_query
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except Exception:
                pass
        return text

    def _jump_to_next_search_match(self, search_query: str, search_encoding: str) -> bool:
        # Search within the correlations for the currently selected attack.
        # Matching is done against the stored event preview plus the exact host-log
        # line read from disk, so it searches log evidence rather than attack text.
        rows = self.current_correlations()
        if not rows or not search_query:
            return False
        start = self.corr_idx
        for step in range(1, len(rows) + 1):
            idx = (start + step) % len(rows)
            if _search_matches_line(_correlation_log_text(rows[idx]), search_query, search_encoding):
                self.corr_idx = idx
                return True
        return False

    # Draw a bordered selectable list pane.
    # Used for both the attack list and the correlation list.
    def _draw_list(
        self,
        win,
        title: str,
        rows: list[str],
        selected: int,
        top: int,
        highlighted: Optional[set[int]] = None,
        highlight_attr: Optional[int] = None,
        border_attr: int = curses.A_NORMAL,
    ) -> int:
        height, width = win.getmaxyx()
        try:
            win.attron(border_attr)
            win.box()
            win.addnstr(0, 2, f" {title} ", width - 4, curses.A_BOLD | border_attr)
            win.attroff(border_attr)
        except Exception:
            win.box()
            win.addnstr(0, 2, f" {title} ", width - 4, curses.A_BOLD)
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

    # Draw a bordered scrollable text pane with wrapping and highlighting.
    # Used for the right-hand event preview.
    def _draw_text(
        self,
        win,
        title: str,
        lines: list[str],
        top: int = 0,
        keywords: Optional[list[str]] = None,
        search_query: str = "",
        search_encoding: str = "utf8",
        border_attr: int = curses.A_NORMAL,
    ) -> int:
        height, width = win.getmaxyx()
        inner_width = max(1, width - 2)
        max_rows = max(0, height - 2)
        try:
            win.attron(border_attr)
            win.box()
            win.attroff(border_attr)
        except Exception:
            win.box()

        rendered: list[tuple[str, bool, Optional[tuple[int, int]]]] = []
        previous_blank = False
        for line in lines:
            safe_line = sanitize_preview_text(line)
            is_hostlog_line = bool(re.match(r"^[ >]\s*\d+\s", safe_line))
            command_value_start = len("Command: ") if safe_line.startswith("Command: ") else None
            if safe_line == "":
                if not previous_blank:
                    rendered.append(("", False, None))
                previous_blank = True
                continue
            previous_blank = False
            start_idx = 0
            # Manual wrapping: curses does not automatically wrap safely inside
            # our boxed pane, so long lines are sliced to the pane width.  Keep
            # a side-band flag saying whether the slice came from an actual
            # host-log context line; only those slices may receive green
            # attack-token highlighting.  The Command line is special: its
            # command value is original attack-log text, so it should be green
            # in the preview even though it is not a host-log context line.
            while start_idx < len(safe_line):
                end_idx = start_idx + inner_width
                forced_green: Optional[tuple[int, int]] = None
                if command_value_start is not None:
                    local_start = max(0, command_value_start - start_idx)
                    local_end = min(inner_width, len(safe_line) - start_idx)
                    if local_start < local_end:
                        forced_green = (local_start, local_end)
                rendered.append((safe_line[start_idx:end_idx], is_hostlog_line, forced_green))
                start_idx += inner_width

        if top < 0:
            top = 0
        max_top = max(0, len(rendered) - max_rows)
        if top > max_top:
            top = max_top

        status = f" {title} [{top + 1}-{min(len(rendered), top + max_rows)}/{max(len(rendered), 1)}] "
        win.addnstr(0, 2, status, width - 4, curses.A_BOLD | border_attr)

        keywords = keywords or []

        for i in range(max_rows):
            idx = top + i
            if idx >= len(rendered):
                break
            rendered_text, is_hostlog_line, forced_green = rendered[idx]
            rendered_line = rendered_text.ljust(inner_width)
            # Host-log context lines receive green attack-token matches.  The
            # Command line gets a forced green span for the original attack
            # command value.  Other preview text can still receive blue syntax
            # or bold search highlighting, but not green lexical highlighting.
            line_keywords = keywords if is_hostlog_line else []
            forced_green_spans = [forced_green] if forced_green else None
            _render_semantic_highlighted_line(
                win,
                i + 1,
                1,
                inner_width,
                rendered_line,
                line_keywords,
                getattr(self, "preview_blue_attr", curses.A_BOLD),
                getattr(self, "preview_green_attr", curses.A_BOLD),
                getattr(self, "preview_bold_attr", curses.A_BOLD),
                search_query,
                search_encoding,
                forced_green_spans,
            )
        return top

    # Main event loop for the curses UI.
    # It lays out the three panes, renders them, reads a key, updates indexes/scroll
    # state, and repeats until the user quits.
    def _main(self, stdscr) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_BLUE, -1)
            curses.init_pair(3, curses.COLOR_RED, -1)  # Active-pane border.
            self.preview_green_attr = curses.color_pair(1) | curses.A_BOLD
            self.preview_blue_attr = curses.color_pair(2) | curses.A_BOLD
            self.preview_bold_attr = curses.A_BOLD | curses.A_REVERSE
            self.correlation_highlight_attr = curses.color_pair(2) | curses.A_BOLD
            self.selected_pane_border_attr = curses.color_pair(3) | curses.A_BOLD
        except Exception:
            self.preview_green_attr = curses.A_BOLD
            self.preview_blue_attr = curses.A_BOLD
            self.preview_bold_attr = curses.A_BOLD | curses.A_REVERSE
            self.correlation_highlight_attr = curses.A_BOLD
            self.selected_pane_border_attr = curses.A_BOLD | curses.A_REVERSE
        attack_top = 0
        corr_top = 0
        preview_top = 0
        preview_collapsed = True
        selected_pane = 0  # 0=attacks, 1=correlations, 2=preview.
        search_query = ""
        search_encoding_idx = 0
        search_status = ""
        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()
            # Recompute layout on every loop so terminal resizes are handled
            # naturally.
            header = "Attack / Log Correlator  q:quit  TAB/left-right:pane  /:search  e:encoding  n:next  up-down:active pane  z:collapse"
            stdscr.addnstr(0, 0, header.ljust(max_x), max_x - 1, curses.A_STANDOUT)
            mid_w = max(34, max_x // 5)
            side_total = max_x - mid_w
            left_w = side_total // 2
            right_w = max_x - left_w - mid_w
            body_h = max(1, max_y - 2)
            attack_win = stdscr.derwin(body_h, left_w, 1, 0)
            corr_win = stdscr.derwin(body_h, mid_w, 1, left_w)
            preview_win = stdscr.derwin(body_h, right_w, 1, left_w + mid_w)
            def pane_title(idx: int, title: str) -> str:
                return ("> " if selected_pane == idx else "  ") + title

            def pane_border_attr(idx: int) -> int:
                return getattr(self, "selected_pane_border_attr", curses.A_BOLD) if selected_pane == idx else curses.A_NORMAL

            attack_rows = []
            highlighted_attack_rows: set[int] = set()
            attack_corr_counts = {a.attack_id: len(self.by_attack.get(a.attack_id, [])) for a in self.attacks}
            attack_score_totals = {
                a.attack_id: sum(float(c.score or 0.0) for c in self.by_attack.get(a.attack_id, []))
                for a in self.attacks
            }
            for idx, a in enumerate(self.attacks):
                cnt = attack_corr_counts.get(a.attack_id, 0)
                total_score = attack_score_totals.get(a.attack_id, 0.0)
                if cnt > 0:
                    highlighted_attack_rows.add(idx)
                attack_rows.append(
                    f"{idx+1:3d} {cnt:3d} total={total_score:7.1f} {a.attacker_host[:12]:<12} "
                    f"{a.timestamp.strftime('%Y-%m-%d %H:%M:%S')} {a.attack_type:<8} {a.cmd[:32]}"
                )
            attack_top = self._draw_list(
                attack_win,
                pane_title(0, f"Attacks ({len(self.attacks)})"),
                attack_rows,
                self.attack_idx,
                attack_top,
                highlighted=highlighted_attack_rows,
                highlight_attr=getattr(self, "correlation_highlight_attr", curses.A_BOLD),
                border_attr=pane_border_attr(0),
            )
            corr_rows = []
            attack = self.current_attack()
            correlations = self.current_correlations()
            lexical_avg = average_lexical_score(correlations)
            highlighted_corr_rows: set[int] = set()
            for idx, c in enumerate(correlations):
                lex_score = correlation_lexical_score(c)
                if lex_score > lexical_avg:
                    highlighted_corr_rows.add(idx)
                corr_rows.append(
                    f"{c.host:<16} s={c.score:6.1f} lx={lex_score:6.1f} dt={c.delta_seconds:8.2f}s {c.event_message[:70]}"
                )
            corr_top = self._draw_list(
                corr_win,
                pane_title(1, f"Correlations ({len(correlations)})"),
                corr_rows,
                self.corr_idx,
                corr_top,
                highlighted=highlighted_corr_rows,
                highlight_attr=getattr(self, "correlation_highlight_attr", curses.A_BOLD),
                border_attr=pane_border_attr(1),
            )
            corr = self.current_correlation()
            preview = build_preview_lines(corr, collapsed=preview_collapsed)
            preview_title = pane_title(2, "Event Preview (collapsed)" if preview_collapsed else "Event Preview (expanded)")
            preview_top = self._draw_text(
                preview_win,
                preview_title,
                preview,
                preview_top,
                _preview_keywords(corr),
                search_query,
                SEARCH_ENCODING_MODES[search_encoding_idx],
                border_attr=pane_border_attr(2),
            )
            footer = (
                f"Search[{SEARCH_ENCODING_MODES[search_encoding_idx]}]: "
                f"{search_query or '<empty>'}  {search_status}"
            )
            stdscr.addnstr(max_y - 1, 0, footer.ljust(max_x), max_x - 1, curses.A_STANDOUT)
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord("q"), 27):
                break
            if ch in (ord("\t"), 9):
                selected_pane = (selected_pane + 1) % 3
            elif ch == ord("/"):
                search_query = self._prompt_search(stdscr, search_query)
                search_status = ""
                if search_query:
                    found = self._jump_to_next_search_match(search_query, SEARCH_ENCODING_MODES[search_encoding_idx])
                    search_status = "match selected" if found else "no match"
                    preview_top = 0
            elif ch in (ord("e"), ord("E")):
                search_encoding_idx = (search_encoding_idx + 1) % len(SEARCH_ENCODING_MODES)
                search_status = f"encoding={SEARCH_ENCODING_MODES[search_encoding_idx]}"
            elif ch in (ord("n"), ord("N")):
                if search_query:
                    found = self._jump_to_next_search_match(search_query, SEARCH_ENCODING_MODES[search_encoding_idx])
                    search_status = "match selected" if found else "no match"
                    preview_top = 0
            elif ch == curses.KEY_LEFT:
                selected_pane = (selected_pane - 1) % 3
            elif ch == curses.KEY_RIGHT:
                selected_pane = (selected_pane + 1) % 3
            elif ch == curses.KEY_UP:
                if selected_pane == 0:
                    self.attack_idx = max(0, self.attack_idx - 1)
                    self.corr_idx = 0
                    preview_top = 0
                elif selected_pane == 1:
                    self.corr_idx = max(0, self.corr_idx - 1)
                    preview_top = 0
                else:
                    preview_top = max(0, preview_top - 1)
            elif ch == curses.KEY_DOWN:
                if selected_pane == 0:
                    self.attack_idx = min(max(0, len(self.attacks) - 1), self.attack_idx + 1)
                    self.corr_idx = 0
                    preview_top = 0
                elif selected_pane == 1:
                    self.corr_idx = min(max(0, len(correlations) - 1), self.corr_idx + 1)
                    preview_top = 0
                else:
                    preview_top += 1
            elif ch == curses.KEY_NPAGE:
                preview_top += max(1, preview_win.getmaxyx()[0] - 3)
            elif ch == curses.KEY_PPAGE:
                preview_top = max(0, preview_top - max(1, preview_win.getmaxyx()[0] - 3))
            elif ch in (ord("z"), ord("Z")):
                preview_collapsed = not preview_collapsed
                preview_top = 0


# --------------------------------- cli -------------------------------------

# Define the command-line interface and parse arguments.
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Correlate attack logs against heterogeneous host logs.")
    p.add_argument(
        "--root",
        required=True,
        help="Working directory containing attacklogs, hostlogs, and output subdirectories",
    )
    p.add_argument(
        "--view-existing",
        action="store_true",
        help="Load out-dir/correlations.json and open the browser without recomputing correlations",
    )
    p.add_argument("--host-config", help="Optional JSON config for host timezones, skew, aliases, and IPs")
    p.add_argument("--default-timezone", default="Europe/Vienna", help="Default timezone for naive host logs")
    p.add_argument("--window-before", type=float, default=60.0, help="Seconds before attack to include")
    p.add_argument("--window-after", type=float, default=240.0, help="Seconds after attack to include")
    p.add_argument(
        "--max-time-delta",
        type=float,
        default=MAX_TIME_DELTA_SECONDS,
        help=(
            "Strict maximum absolute timestamp difference, in seconds, for timestamped "
            "attack/event pairs before content scoring is attempted. Default: %(default)s"
        ),
    )
    p.add_argument("--max-per-attack", type=int, default=30, help="Maximum saved correlations per attack")
    p.add_argument("--default-year", type=int, default=CURRENT_YEAR_FALLBACK, help="Fallback year for yearless timestamps")
    p.add_argument(
        "--process-untimestamped-lines",
        action="store_true",
        help="Also load log lines with no parseable timestamp for content-only scoring; slower on noisy logs",
    )
    p.add_argument("--no-ui", action="store_true", help="Write outputs only")
    return p.parse_args()


def ensure_work_dirs(root: Path) -> tuple[Path, Path, Path]:
    """
    Ensure the standard correlator working directories exist below root.

    Returns:
        (attacklogs_dir, hostlogs_dir, output_dir)
    """
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    attacklogs_dir = root / "attacklogs"
    hostlogs_dir = root / "hostlogs"
    output_dir = root / "output"

    for directory in (attacklogs_dir, hostlogs_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return attacklogs_dir, hostlogs_dir, output_dir

# Top-level program flow:
# parse CLI -> discover/load config -> load attacks/events -> correlate ->
# export outputs -> optionally open the interactive browser.
def main() -> int:
    global MAX_TIME_DELTA_SECONDS

    args = parse_args()
    if args.max_time_delta < 0:
        print("[error] --max-time-delta must be non-negative", file=sys.stderr)
        return 2
    MAX_TIME_DELTA_SECONDS = float(args.max_time_delta)

    attack_root, log_root, out_dir = ensure_work_dirs(Path(args.root))
    host_config_path = Path(args.host_config).expanduser().resolve() if args.host_config else None

    if args.view_existing:
        attacks, correlations, saved_summary = load_existing_outputs(out_dir)
        summary = {
            "mode": "view-existing",
            "attacks": len(attacks),
            "correlations": len(correlations),
            "out_dir": str(out_dir),
            "loaded_from": str(out_dir / "correlations.json"),
            "saved_summary": saved_summary,
        }
        print(json.dumps(summary, indent=2))
        if not args.no_ui:
            try:
                CorrelationBrowser(attacks, correlations).run()
            except Exception:
                print("[error] curses UI crashed", file=sys.stderr)
                traceback.print_exc()
        return 0

    # First infer host/attacker names from file layout.  The optional config
    # loaded next can correct or enrich these guesses.
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
    raw_cfg.setdefault("default_attacker_timezone", "UTC")
    raw_cfg.setdefault("default_utc_offset_hours", 0)
    for attacker in discovered_attacker_hosts:
        raw_cfg["attacker_hosts"].setdefault(attacker, {
            "timezone": raw_cfg.get("default_attacker_timezone", "UTC"),
            "utc_offset_hours": raw_cfg.get("default_utc_offset_hours", 0),
            "notes": "Set timezone to UTC, Europe/Vienna, etc.; utc_offset_hours is an additional legacy correction",
        })

    resolver = HostResolver(config)

    # The core pipeline.  Nothing is correlated until both sides have been
    # normalized into Attack and LogEvent objects.
    attacks = load_all_attacks(attack_root, resolver, config=config)
    # attacks may reveal additional hostnames via IP mapping in config; reload not necessary
    events = load_all_events(log_root, attack_root, args.default_year, resolver, include_untimestamped=args.process_untimestamped_lines)
    correlations = correlate(attacks, events, args.window_before, args.window_after, args.max_per_attack)
    export_outputs(out_dir, config, attacks, events, correlations)

    summary = {
        "attacks": len(attacks),
        "events": len(events),
        "correlations": len(correlations),
        "unparsable_lines": UNPARSABLE_LINE_COUNT,
        "journalctl_converted_files": JOURNALCTL_CONVERTED_FILE_COUNT,
        "binary_log_files_skipped": BINARY_LOG_FILE_SKIPPED_COUNT,
        "untimestamped_lines_loaded": args.process_untimestamped_lines,
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
