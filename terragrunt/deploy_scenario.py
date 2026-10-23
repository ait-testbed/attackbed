#!/usr/bin/env python3
"""Run independent AttackBed deployments using the existing Terragrunt units."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock

import yaml


ROOT = Path(__file__).resolve().parent
PRINT_LOCK = Lock()


def scenario_units(root, scenario):
    with (root / "scenarios.yaml").open() as stream:
        scenarios = yaml.safe_load(stream)
    if scenario not in scenarios:
        raise ValueError(f"Unknown scenario: {scenario}")

    units = list(dict.fromkeys(scenarios[scenario]))
    if "bootstrap" not in units:
        raise ValueError(f"Scenario {scenario} must include bootstrap")
    units.remove("bootstrap")
    units.insert(0, "bootstrap")
    for unit in units:
        if not (root / unit / "terragrunt.hcl").is_file():
            raise ValueError(f"Unknown Terragrunt unit: {unit}")
    return units


def run_unit(root, deployment_id, unit, action, tofu_parallelism=None):
    env = os.environ.copy()
    env["ATTACKBED_DEPLOYMENT_ID"] = deployment_id
    cmd = ["terragrunt", action, "--non-interactive"]
    if tofu_parallelism is not None:
        cmd.append(f"-parallelism={tofu_parallelism}")
    if action in ("apply", "destroy"):
        cmd.append("-auto-approve")

    label = f"{deployment_id}/{unit}"
    secrets = [env.get(key) for key in (
        "CR_GITLAB_ACCESS_TOKEN", "OS_PASSWORD", "OS_APPLICATION_CREDENTIAL_SECRET",
        "TF_HTTP_PASSWORD",
    )]
    with PRINT_LOCK:
        print(f"[{label}] {action}", flush=True)
    try:
        with subprocess.Popen(
            cmd, cwd=root / unit, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        ) as process:
            for line in process.stdout:
                for secret in secrets:
                    if secret:
                        line = line.replace(secret, "[REDACTED]")
                with PRINT_LOCK:
                    print(f"[{label}] {line}", end="", flush=True)
            return process.wait()
    except OSError as exc:
        print(f"[{label}] {exc}", file=sys.stderr)
        return 1


def run_deployment(root, deployment_id, units, action, runner=run_unit, tofu_parallelism=None):
    order = reversed(units) if action == "destroy" else units
    for unit in order:
        if runner(root, deployment_id, unit, action, tofu_parallelism) != 0:
            print(f"[{deployment_id}] Stopped after failed {unit} {action}", file=sys.stderr)
            return 1
    return 0


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", help="Scenario from scenarios.yaml")
    parser.add_argument("action", choices=("plan", "apply", "destroy"))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--copies", type=int, help="Select PREFIX-001 through PREFIX-N")
    selection.add_argument("--deployment", action="append", help="Deployment ID (repeatable)")
    parser.add_argument("--prefix", default="lab", help="Prefix for --copies")
    parser.add_argument("--parallel-copies", type=int, default=4, help="Concurrent deployments")
    parser.add_argument("--tofu-parallelism", type=int, help="OpenTofu operations per unit")
    parser.add_argument("--yes", action="store_true", help="Confirm apply or destroy")
    args = parser.parse_args(argv)

    if args.copies is not None and args.copies < 1:
        parser.error("--copies must be positive")
    if args.parallel_copies < 1:
        parser.error("--parallel-copies must be positive")
    if args.tofu_parallelism is not None and args.tofu_parallelism < 1:
        parser.error("--tofu-parallelism must be positive")
    if args.action in ("apply", "destroy") and not args.yes:
        parser.error("apply and destroy require --yes")
    for variable in ("TG_DOWNLOAD_DIR", "TF_DATA_DIR"):
        if os.environ.get(variable):
            parser.error(f"Unset {variable} to preserve cache isolation")

    names = args.deployment or [
        f"{args.prefix}-{index:03d}" for index in range(1, args.copies + 1)
    ]
    if any(not re.fullmatch(r"[a-z][a-z0-9-]*", name) for name in names):
        parser.error("Deployment IDs must be lowercase letters, digits or hyphens")
    names = list(dict.fromkeys(names))
    units = scenario_units(root, args.scenario)

    with ThreadPoolExecutor(max_workers=args.parallel_copies) as executor:
        results = list(executor.map(
            lambda name: run_deployment(
                root, name, units, args.action, tofu_parallelism=args.tofu_parallelism
            ), names
        ))
    return int(any(results))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
