import datetime as dt

from attacklog_correlator import cli


def test_try_parse_line_timestamp_finds_audit_epoch_inside_line():
    line = "type=EXECVE msg=audit(1710000000.125:123): argc=2 a0=\"sleep\" a1=\"1\""

    parsed = cli.try_parse_line_timestamp(line, default_year=2026)

    assert parsed is not None
    assert parsed.parser_name == "auditd-epoch"
    assert parsed.naive is False
    assert parsed.timestamp_utc == dt.datetime.fromtimestamp(1710000000.125, tz=cli.UTC)


def test_try_parse_line_timestamp_finds_apache_timestamp_not_at_line_start():
    line = '10.0.0.5 - - [27/May/2026:13:01:57 +0200] "GET /payload.sh HTTP/1.1" 200 612'

    parsed = cli.try_parse_line_timestamp(line, default_year=2026)

    assert parsed is not None
    assert parsed.parser_name == "apache-nginx"
    assert parsed.naive is False
    assert parsed.timestamp_utc == dt.datetime(2026, 5, 27, 11, 1, 57, tzinfo=cli.UTC)


def test_parse_json_line_timestamp_accepts_epoch_milliseconds():
    parsed = cli.parse_json_line_timestamp('{"time": 1710000000123, "message": "hello"}', 2026)

    assert parsed is not None
    assert parsed.parser_name == "json:time:epoch"
    assert parsed.timestamp_utc == dt.datetime.fromtimestamp(1710000000.123, tz=cli.UTC)


def test_parse_attack_datetime_interprets_naive_time_in_attacker_timezone():
    parsed = cli.parse_attack_datetime("2026-05-27T13:01:57", "Europe/Vienna")

    assert parsed == dt.datetime(2026, 5, 27, 11, 1, 57, tzinfo=cli.UTC)


def test_parse_attack_datetime_respects_existing_offset_over_attacker_timezone():
    parsed = cli.parse_attack_datetime("2026-05-27T13:01:57+00:00", "Europe/Vienna")

    assert parsed == dt.datetime(2026, 5, 27, 13, 1, 57, tzinfo=cli.UTC)
