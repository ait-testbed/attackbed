# Attack Log Correlator

`attacklog-correlator` correlates AttackMate-style JSON attack logs with heterogeneous Linux host logs. It discovers attack-log files and host-log files, normalizes timestamps, infers candidate target hosts, scores lexical and timing evidence, exports JSON/CSV summaries, and optionally opens an ncurses browser for reviewing the matches.

## Basic usage

The `--root` working directory contains the `attacklogs`, `hostlogs`, and `output` subdirectories. Missing subdirectories are created automatically.

Put the attackmate log files in folders named after the attacker hosts in `root/attacklogs`, so e.g. `root/attacklogs/attacker/attackmate.json`, and the hostlogs in `root/hostlogs/inetfw/..` accordingly. Then run it with `uv run attacklog-correlator --root root`.

Be aware if your machines were set to different timezones during data collection: the first run of the program will generate the file `output/host_config.generated.json`, where you can adapt time zone differences. For the next run, save that file to a different path, e.g. `output/host_config.json`, and pass it as an argument via `--host-config output/host_config.json`, as the generated json is overwritten each run. This is intended behavior.

```bash
uv run attacklog-correlator --root /path/to/workdir
```

Review previously computed output without reparsing or rescoring:

```bash
uv run attacklog-correlator --root /path/to/workdir --view-existing
```

## Important options

- `--host-config`: JSON config for host timezones, aliases, clock skew, IP addresses, and attacker timezones.
- `--max-time-delta`: strict maximum absolute timestamp delta for timestamped attack/log pairs before content scoring is attempted; defaults to `0.3`.
- `--default-timezone`: timezone for naive host-log timestamps.
- `--window-before` / `--window-after`: broad correlation time window around each attack.
- `--max-per-attack`: maximum saved correlations per attack step.
- `--process-untimestamped-lines`: opt in to loading lines that have no parseable timestamp. By default, those lines are counted but skipped for performance.
- `--view-existing`: open `correlations.json` from the working directory's `output` subdirectory without recomputing.

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

## Installation for development

```bash
uv sync --extra dev
```

## Development checks

```bash
uv run python -m py_compile src/attacklog_correlator/cli.py
uv run --extra dev pytest
```
