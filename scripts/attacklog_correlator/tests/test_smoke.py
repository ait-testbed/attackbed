

def test_json_schema_keys_do_not_become_lexical_matches():
    import datetime as dt
    from attacklog_correlator import cli

    attack = cli.Attack(
        attack_id="a1",
        timestamp=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
        attack_type="execution",
        cmd="sudo nmcli device set wlan1 managed",
        source_file="attack.jsonl",
        line_number=1,
        metadata={},
        raw_line='{"type":"execution","cmd":"sudo nmcli device set wlan1 managed"}',
        attacker_host="attacker",
    )
    event = cli.LogEvent(
        event_id="e1",
        timestamp=attack.timestamp,
        raw_timestamp="",
        host="target",
        source_type="generic-text",
        file_path="host.log",
        line_number=1,
        message="host log contains the word type but no command tokens",
        raw_line="host log contains the word type but no command tokens",
        extra={},
        candidate_hosts=["target"],
        candidate_ips=[],
    )

    assert "type" not in cli.extract_attack_lexical_terms(attack)
    assert cli.lexical_overlap_score(attack, event)[2] == []


def test_parse_args_accepts_max_time_delta(monkeypatch):
    from attacklog_correlator import cli

    monkeypatch.setattr(
        "sys.argv",
        [
            "attacklog-correlator",
            "--attack-root",
            "attacks",
            "--log-root",
            "logs",
            "--out-dir",
            "out",
            "--max-time-delta",
            "2.5",
        ],
    )

    args = cli.parse_args()
    assert args.max_time_delta == 2.5
