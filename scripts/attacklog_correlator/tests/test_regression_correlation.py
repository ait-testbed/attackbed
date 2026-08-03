import datetime as dt

from attacklog_correlator import cli

NOW = dt.datetime(2026, 5, 27, 12, 0, 0, tzinfo=cli.UTC)


def make_attack(cmd: str = "sleep 5") -> cli.Attack:
    return cli.Attack(
        attack_id="attack:1",
        timestamp=NOW,
        attack_type="execution",
        cmd=cmd,
        source_file="attack.jsonl",
        line_number=1,
        metadata={},
        raw_line=f'{{"cmd":"{cmd}"}}',
        target_ips=["10.0.0.5"] if "10.0.0.5" in cmd else [],
        attacker_host="attacker",
    )


def make_event(message: str, seconds_after: float = 0.0) -> cli.LogEvent:
    return cli.LogEvent(
        event_id=f"event:{seconds_after}",
        timestamp=NOW + dt.timedelta(seconds=seconds_after),
        raw_timestamp="2026-05-27T12:00:00Z",
        host="target",
        source_type="generic-text",
        file_path="host.log",
        line_number=1,
        message=message,
        raw_line=message,
        extra={},
        candidate_hosts=["target"],
        candidate_ips=cli.extract_ips(message),
    )


def test_time_only_event_is_not_correlated():
    correlations = cli.correlate([make_attack("sleep 5")], [make_event("unrelated system log")], 60, 60, 10)

    assert correlations == []


def test_ip_only_event_is_not_correlated_without_command_match():
    attack = make_attack("curl http://10.0.0.5/payload.sh")
    event = make_event("connection from 10.0.0.5 accepted")

    correlations = cli.correlate([attack], [event], 60, 60, 10)

    assert correlations == []


def test_command_match_creates_correlation_and_records_matched_command_token():
    attack = make_attack("sleep 5")
    event = make_event("audit: comm=\"sleep\" argc=2")

    correlations = cli.correlate([attack], [event], 60, 60, 10)

    assert len(correlations) == 1
    assert "sleep" in correlations[0].matched_command_terms
    assert correlations[0].matched_metadata_terms == []


def test_max_time_delta_global_caps_timestamped_matches(monkeypatch):
    attack = make_attack("sleep 5")
    event = make_event("audit: comm=\"sleep\" argc=2", seconds_after=0.5)

    monkeypatch.setattr(cli, "MAX_TIME_DELTA_SECONDS", 0.3)
    assert cli.correlate([attack], [event], 60, 60, 10) == []

    monkeypatch.setattr(cli, "MAX_TIME_DELTA_SECONDS", 1.0)
    assert len(cli.correlate([attack], [event], 60, 60, 10)) == 1
