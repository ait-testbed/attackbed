

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
            "--root",
            "work",
            "--max-time-delta",
            "2.5",
        ],
    )

    args = cli.parse_args()
    assert args.root == "work"
    assert args.max_time_delta == 2.5


def test_tui_starts_on_attacks_and_arrows_switch_panes(monkeypatch):
    from attacklog_correlator import cli

    class FakeScreen:
        def __init__(self):
            self.keys = [cli.curses.KEY_RIGHT, cli.curses.KEY_LEFT, ord("q")]

        def keypad(self, _enabled):
            pass

        def erase(self):
            pass

        def getmaxyx(self):
            return 24, 120

        def addnstr(self, *_args):
            pass

        def derwin(self, *_args):
            return object()

        def refresh(self):
            pass

        def getch(self):
            return self.keys.pop(0)

    active_panes = []
    browser = cli.CorrelationBrowser([], [])

    def record_list(_win, title, _rows, _selected, top, **_kwargs):
        if title.startswith("> "):
            active_panes.append(title[2:].split(" (", 1)[0])
        return top

    def record_preview(_win, title, _lines, top=0, *_args, **_kwargs):
        if title.startswith("> "):
            active_panes.append("Preview")
        return top

    monkeypatch.setattr(cli.curses, "curs_set", lambda _visibility: None)
    monkeypatch.setattr(cli.curses, "start_color", lambda: None)
    monkeypatch.setattr(cli.curses, "use_default_colors", lambda: None)
    monkeypatch.setattr(cli.curses, "init_pair", lambda *_args: None)
    monkeypatch.setattr(cli.curses, "color_pair", lambda _pair: 0)
    monkeypatch.setattr(browser, "_draw_list", record_list)
    monkeypatch.setattr(browser, "_draw_text", record_preview)

    browser._main(FakeScreen())

    assert active_panes == ["Attacks", "Correlations", "Attacks"]
