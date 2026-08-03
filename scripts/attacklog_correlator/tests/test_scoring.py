import datetime as dt

from attacklog_correlator import cli


def _correlation_with_breakdown(breakdown):
    now = dt.datetime(2026, 1, 1, tzinfo=cli.UTC)
    return cli.Correlation(
        correlation_id="attack|event",
        attack_id="attack",
        event_id="event",
        attacker_host="attacker",
        attack_time=now,
        event_time=now,
        delta_seconds=0.0,
        abs_delta_seconds=0.0,
        attack_file="attack.jsonl",
        attack_line=1,
        attack_raw_line='{"cmd":"curl http://target/payload.sh"}',
        event_file="syslog",
        event_line=1,
        host="target",
        attack_type="execution",
        attack_cmd="curl http://target/payload.sh",
        attack_targets=["target"],
        target_host_matches=["target"],
        event_message="target accepted connection",
        event_source_type="syslog-like",
        score=100.0,
        score_breakdown=breakdown,
        matched_lexical_terms=list(breakdown),
    )


def test_relevance_threshold_rejects_no_lexical_evidence():
    corr = _correlation_with_breakdown({"time_proximity": 40.0, "target_host_exact": 45.0})
    corr.matched_lexical_terms = []

    assert cli.has_lexical_match(corr) is False
    assert cli.relevance_threshold(corr) is False


def test_relevance_threshold_allows_command_lexical_evidence():
    corr = _correlation_with_breakdown({"time_proximity": 40.0, "lexical_exact_match": 20.0})
    corr.matched_lexical_terms = ["payload"]
    corr.matched_command_terms = ["payload"]

    assert cli.has_lexical_match(corr) is True
    assert cli.relevance_threshold(corr) is True


def test_relevance_threshold_rejects_metadata_only_evidence():
    corr = _correlation_with_breakdown({"time_proximity": 40.0, "metadata_lexical_match": 3.0})
    corr.matched_lexical_terms = ["dhcp"]
    corr.matched_metadata_terms = ["dhcp"]
    corr.matched_command_terms = []

    assert cli.has_lexical_match(corr) is False
    assert cli.relevance_threshold(corr) is False
