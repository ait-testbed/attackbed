#!/usr/bin/env python3
"""Run independent AttackBed deployments using the existing Terragrunt units."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parent
PRINT_LOCK = Lock()


def scenario_units(root, scenario):
    with (root.parent / "config/scenarios.yaml").open() as stream:
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


def run_unit(root, deployment_id, unit, action, tofu_parallelism=None, log_file=None, debug=False):
    env = os.environ.copy()
    env["ATTACKBED_DEPLOYMENT_ID"] = deployment_id
    cmd = ["terragrunt", action, "--non-interactive"]
    if tofu_parallelism is not None:
        if action == "apply":
            # terragrunt.hcl supplies the apply flag; avoid passing it twice.
            env["TF_VAR_parallelism"] = str(tofu_parallelism)
        else:
            cmd.append(f"-parallelism={tofu_parallelism}")
    if action in ("apply", "destroy"):
        cmd.append("-auto-approve")

    label = f"{deployment_id}/{unit}"
    tail = deque(maxlen=40)
    secrets = [env.get(key) for key in (
        "CR_GITLAB_ACCESS_TOKEN", "OS_PASSWORD", "OS_APPLICATION_CREDENTIAL_SECRET",
        "TF_HTTP_PASSWORD",
    )]
    with PRINT_LOCK:
        print(f"[{label}] {action} started", flush=True)
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
                    if log_file is not None:
                        log_file.write(f"[{label}] {line}")
                        log_file.flush()
                    tail.append(line)
                    if debug:
                        print(f"[{label}] {line}", end="", flush=True)
            returncode = process.wait()
    except OSError as exc:
        with PRINT_LOCK:
            print(f"[{label}] FAILED: {exc}", file=sys.stderr)
            if log_file is not None:
                log_file.write(f"[{label}] FAILED: {exc}\n")
        return 1

    with PRINT_LOCK:
        if returncode == 0:
            print(f"[{label}] OK", flush=True)
        else:
            print(f"[{label}] FAILED (exit code {returncode})", file=sys.stderr)
            if not debug:
                print("".join(tail), end="", file=sys.stderr)
            if log_file is not None:
                print(f"Full log: {root / 'attackbed.log'}", file=sys.stderr)
    return returncode


def delete_deployment_states(deployment_id, units):
    base = os.environ["GITLAB_STATE_REPOSITORY"].rstrip("/")
    token = os.environ["CR_GITLAB_ACCESS_TOKEN"]
    path = urlsplit(base)
    if path.scheme != "https" or not re.fullmatch(r"/api/v4/projects/[^/]+/terraform/state", path.path):
        raise ValueError("GITLAB_STATE_REPOSITORY must be an HTTPS GitLab Terraform state API URL")
    prefix = "_".join((
        os.environ["OS_PROJECT_NAME"], os.environ["OS_USER_DOMAIN_NAME"],
        os.environ.get("OS_REGION_NAME", "default"), deployment_id,
    ))
    for unit in units:
        state_name = f"{prefix}_{unit}"
        url = f"{base}/{quote(state_name, safe='')}"
        headers = {"PRIVATE-TOKEN": token}
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                state = json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                continue  # Already absent; no state to remove.
            raise
        if not isinstance(state, dict) or not isinstance(state.get("resources"), list):
            raise ValueError(f"Unexpected Terraform state format: {state_name}")
        if any(resource.get("mode") != "data" and resource.get("instances")
               for resource in state["resources"]):
            raise RuntimeError(f"GitLab state still tracks resources: {state_name}")
        try:
            with urlopen(Request(url, headers=headers, method="DELETE"), timeout=30):
                pass
        except HTTPError as exc:
            if exc.code != 404:
                raise
        with PRINT_LOCK:
            print(f"[{deployment_id}] deleted state {state_name}", flush=True)


def run_deployment(root, deployment_id, units, action, runner=run_unit,
                   tofu_parallelism=None, log_file=None, debug=False):
    order = reversed(units) if action == "destroy" else units
    for unit in order:
        if runner(root, deployment_id, unit, action, tofu_parallelism, log_file, debug) != 0:
            with PRINT_LOCK:
                print(f"[{deployment_id}] Stopped after failed {unit} {action}", file=sys.stderr)
            return 1
    if action == "destroy":
        try:
            delete_deployment_states(deployment_id, units)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            with PRINT_LOCK:
                message = f"[{deployment_id}] Infrastructure destroyed; state cleanup failed: {exc}"
                print(message, file=sys.stderr)
                if log_file is not None:
                    log_file.write(message + "\n")
            return 1
    return 0


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", help="Scenario from config/scenarios.yaml")
    parser.add_argument("action", choices=("plan", "apply", "destroy"))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--copies", type=int, help="Select PREFIX-001 through PREFIX-N")
    selection.add_argument("--deployment", action="append", help="Deployment ID (repeatable)")
    parser.add_argument("--prefix", default="lab", help="Prefix for --copies")
    parser.add_argument("--parallel-copies", type=int, default=4, help="Concurrent deployments")
    parser.add_argument("--tofu-parallelism", type=int, help="OpenTofu operations per unit")
    parser.add_argument("--debug", action="store_true", help="Stream full Terragrunt output")
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

    if args.action == "destroy":
        for variable in ("GITLAB_STATE_REPOSITORY", "CR_GITLAB_ACCESS_TOKEN", "OS_PROJECT_NAME", "OS_USER_DOMAIN_NAME"):
            if not os.environ.get(variable):
                parser.error(f"{variable} is required to delete GitLab states after destroy")

    log_path = root / "attackbed.log"
    log_path.touch(mode=0o600)
    log_path.chmod(0o600)
    with log_path.open("w") as log_file:
        with ThreadPoolExecutor(max_workers=args.parallel_copies) as executor:
            results = list(executor.map(
                lambda name: run_deployment(
                    root, name, units, args.action, log_file=log_file,
                    debug=args.debug, tofu_parallelism=args.tofu_parallelism
                ), names
            ))
    print(f"Log: {log_path}")
    return int(any(results))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
