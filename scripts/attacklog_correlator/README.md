# Attack Log Correlator

`attacklog-correlator` correlates AttackMate-style JSON attack logs with heterogeneous Linux host logs. It discovers attack-log files and host-log files, normalizes timestamps, infers candidate target hosts, scores lexical and timing evidence, exports JSON/CSV summaries, and optionally opens an ncurses browser for reviewing the matches.

The tool uses only the Python standard library at runtime. For binary systemd journal files, it shells out to `journalctl`.

## Installation for development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Basic usage

```bash
attacklog-correlator \
  --attack-root /path/to/attacklogs \
  --log-root /path/to/hostlogs \
  --out-dir /path/to/output
```

Run without the ncurses UI:

```bash
attacklog-correlator \
  --attack-root /path/to/attacklogs \
  --log-root /path/to/hostlogs \
  --out-dir /path/to/output \
  --no-ui
```

Review previously computed output without reparsing or rescoring:

```bash
attacklog-correlator --out-dir /path/to/output --view-existing
```

## Important options

- `--host-config`: JSON config for host timezones, aliases, clock skew, IP addresses, and attacker timezones.
- `--default-timezone`: timezone for naive host-log timestamps.
- `--window-before` / `--window-after`: broad correlation time window around each attack.
- `--max-time-delta`: strict maximum absolute timestamp delta for timestamped attack/log pairs before content scoring is attempted; defaults to `0.3`.
- `--max-per-attack`: maximum saved correlations per attack step.
- `--process-untimestamped-lines`: opt in to loading lines that have no parseable timestamp. By default, those lines are counted but skipped for performance.
- `--view-existing`: open `correlations.json` from `--out-dir` without recomputing.

## Host and attacker timezone config

The generated config can be edited and reused with `--host-config`:

```json
{
  "default_timezone": "Europe/Vienna",
  "default_attacker_timezone": "UTC",
  "hosts": {
    "fileshare": {
      "timezone": "Europe/Vienna",
      "clock_skew_seconds": 0.0,
      "aliases": [],
      "ip_addresses": [],
      "path_hints": ["fileshare"],
      "notes": ""
    }
  },
  "attacker_hosts": {
    "attacker-utc": {
      "timezone": "UTC",
      "utc_offset_hours": 0
    },
    "attacker-vienna": {
      "timezone": "Europe/Vienna",
      "utc_offset_hours": 0
    }
  }
}
```

Attack timestamps with explicit offsets keep their own offset. Naive attack timestamps are interpreted using the matching attacker timezone.

## Outputs

The output directory contains:

- `correlations.json`: full machine-readable result.
- `correlations.csv`: flat table for spreadsheets.
- `correlations_human.txt`: text report for review.
- `summary.json`: counts and run metadata.
- `host_config.generated.json`: discovered host config template.
- `per_host/`: per-host JSON/CSV/text views.

## Development checks

```bash
python -m py_compile src/attacklog_correlator/cli.py
pytest
```
