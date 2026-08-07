import json
from pathlib import Path

from attacklog_correlator import cli


def test_discover_hosts_uses_only_top_level_host_folder_for_hints(tmp_path: Path):
    log_root = tmp_path / "hostlogs"
    fileshare_log = log_root / "fileshare" / "var" / "log" / "apt" / "history.log"
    inetfw_log = log_root / "inetfw" / "var" / "log" / "apt" / "history.log"
    fileshare_log.parent.mkdir(parents=True)
    inetfw_log.parent.mkdir(parents=True)
    fileshare_log.write_text("", encoding="utf-8")
    inetfw_log.write_text("", encoding="utf-8")

    hosts = cli.discover_hosts_from_logs(log_root, None, "Europe/Vienna")

    assert sorted(hosts) == ["fileshare", "inetfw"]
    assert hosts["fileshare"].path_hints == ["fileshare"]
    assert hosts["inetfw"].path_hints == ["inetfw"]


def test_random_top_level_identifier_is_not_discovered_as_host(tmp_path: Path):
    log_root = tmp_path / "hostlogs"
    random_log = log_root / "550e8400-e29b-41d4-a716-446655440000" / "var" / "log" / "syslog"
    random_log.parent.mkdir(parents=True)
    random_log.write_text("", encoding="utf-8")

    hosts = cli.discover_hosts_from_logs(log_root, None, "Europe/Vienna")

    assert hosts == {}


def test_systemd_journal_magic_is_detected_even_without_journal_suffix(tmp_path: Path):
    path = tmp_path / "user-1000"
    path.write_bytes(b"LPKSHHRH" + b"\x00" * 32)

    assert cli.file_starts_with_systemd_journal_magic(path) is True
    assert cli.should_try_journalctl(path) is True


def test_binary_non_journal_file_is_detected_but_not_treated_as_journal(tmp_path: Path):
    path = tmp_path / "capture.pcap"
    path.write_bytes(b"\xd4\xc3\xb2\xa1" + b"\x00" * 64)

    assert cli.is_probably_binary_file(path) is True
    assert cli.should_try_journalctl(path) is False


def test_load_existing_outputs_reconstructs_attacks_and_correlations(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    payload = {
        "summary": {"attack_count": 1, "correlation_count": 1},
        "attacks": [
            {
                "attack_id": "attack:1",
                "timestamp": "2026-05-27T12:00:00+00:00",
                "type": "execution",
                "cmd": "sleep 5",
                "source_file": "attack.jsonl",
                "line_number": 1,
                "raw_line": '{"cmd":"sleep 5"}',
                "metadata": {},
                "attacker_host": "attacker",
            }
        ],
        "correlations": [
            {
                "correlation_id": "attack:1|event:1",
                "attack_id": "attack:1",
                "event_id": "event:1",
                "attacker_host": "attacker",
                "attack_time": "2026-05-27T12:00:00+00:00",
                "event_time": "2026-05-27T12:00:00+00:00",
                "delta_seconds": 0.0,
                "abs_delta_seconds": 0.0,
                "host": "target",
                "attack_type": "execution",
                "attack_cmd": "sleep 5",
                "attack_targets": [],
                "target_host_matches": [],
                "event_source_type": "auditd",
                "event_message": 'comm="sleep"',
                "score": 100.0,
                "score_breakdown": {"binary_name_match": 65.0},
                "matched_lexical_terms": ["sleep"],
                "matched_command_terms": ["sleep"],
                "matched_metadata_terms": [],
                "attack_file": "attack.jsonl",
                "attack_line": 1,
                "attack_raw_line": '{"cmd":"sleep 5"}',
                "event_file": "audit.log",
                "event_line": 1,
            }
        ],
    }
    (out_dir / "correlations.json").write_text(json.dumps(payload), encoding="utf-8")

    attacks, correlations, summary = cli.load_existing_outputs(out_dir)

    assert len(attacks) == 1
    assert len(correlations) == 1
    assert attacks[0].cmd == "sleep 5"
    assert correlations[0].matched_command_terms == ["sleep"]
    assert summary["correlation_count"] == 1
