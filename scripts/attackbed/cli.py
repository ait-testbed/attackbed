"""Build Packer images and deploy AttackBed scenarios."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import yaml

from .images import active_image, build_image, latest_images, required_recipes
from .ssh import write_ssh_config

ROOT = Path(__file__).resolve().parents[2]


def connect():
    import openstack
    return openstack.connect()


def save_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def resume_directory(runs, requested):
    if requested == "latest":
        jobs = sorted(path for path in runs.glob("run-*") if (path / "run.json").is_file())
        if not jobs:
            raise ValueError("No runs to resume")
        return jobs[-1]
    if not re.fullmatch(r"run-[A-Za-z0-9-]+", requested):
        raise ValueError("Invalid run ID")
    directory = runs / requested
    if not (directory / "run.json").is_file():
        raise ValueError(f"Unknown run: {requested}")
    return directory


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", help="Scenario from terragrunt/scenarios.yaml")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--build", action="store_true", help="Build required images using Packer")
    source.add_argument("--images", type=Path, help="Reuse a saved images.json")
    parser.add_argument("--resume", nargs="?", const="latest", metavar="RUN_ID")
    parser.add_argument("--copies", type=int, default=1)
    parser.add_argument("--prefix", default="lab")
    parser.add_argument("--parallel-copies", type=int, default=4)
    parser.add_argument("--tofu-parallelism", type=int)
    args = parser.parse_args(argv)
    if args.copies < 1 or args.parallel_copies < 1 or (args.tofu_parallelism is not None and args.tofu_parallelism < 1):
        parser.error("Parallelism and copy counts must be positive")

    runs = root / "runs"
    if args.resume is not None:
        if args.scenario or args.build or args.images:
            parser.error("--resume does not accept a scenario, --build or --images")
        directory = resume_directory(runs, args.resume)
        job = json.loads((directory / "run.json").read_text())
    else:
        if not args.scenario:
            parser.error("scenario is required unless --resume is used")
        scenarios = yaml.safe_load((root / "terragrunt/scenarios.yaml").read_text())
        if args.scenario not in scenarios:
            parser.error(f"Unknown scenario: {args.scenario}")
        units = list(dict.fromkeys(scenarios[args.scenario]))
        if "bootstrap" not in units:
            parser.error("Scenario must include bootstrap")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", args.prefix):
            parser.error("Invalid deployment prefix")
        directory = runs / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
        directory.mkdir(parents=True, mode=0o700)
        job = {
            "scenario": args.scenario,
            "units": units,
            "deployments": [f"{args.prefix}-{n:03d}" for n in range(1, args.copies + 1)],
            "mode": "build" if args.build else "file" if args.images else "latest",
            "source_images": str(args.images.expanduser().resolve()) if args.images else None,
            "parallel_copies": args.parallel_copies,
            "tofu_parallelism": args.tofu_parallelism,
            "deployed": False,
            "complete": False,
        }
        save_json(directory / "run.json", job)

    if job["complete"]:
        print(f"Already complete: {directory}")
        return 0
    print(f"Run: {directory}", flush=True)
    conn = connect()
    recipes = required_recipes(root, job["units"])
    images_file = directory / "images.json"
    images = json.loads(images_file.read_text()) if images_file.exists() else {}
    if job["mode"] == "build":
        (directory / "logs").mkdir(mode=0o700, exist_ok=True)
        for role, recipe in recipes.items():
            if role in images:
                active_image(conn, images[role]["id"])
                continue
            print(f"Building {role} ({recipe})", flush=True)
            images[role] = build_image(conn, root, recipe, directory / "logs" / f"{recipe}.log")
            save_json(images_file, images)
    elif not images_file.exists():
        if job["mode"] == "latest":
            images = latest_images(conn, root, recipes)
        else:
            source_file = Path(job["source_images"])
            images = json.loads(source_file.read_text())
        images = {role: active_image(conn, images[role]["id"]) for role in recipes}
        save_json(images_file, images)

    if not job["deployed"]:
        env = os.environ.copy()
        env["ATTACKBED_IMAGES_FILE"] = str(images_file.resolve())
        cmd = [sys.executable, str(root / "terragrunt/deploy_scenario.py"), job["scenario"], "apply", "--yes",
               "--parallel-copies", str(job["parallel_copies"])]
        for name in job["deployments"]:
            cmd += ["--deployment", name]
        if job["tofu_parallelism"] is not None:
            cmd += ["--tofu-parallelism", str(job["tofu_parallelism"])]
        subprocess.run(cmd, cwd=root, env=env, check=True)
        job["deployed"] = True
        save_json(directory / "run.json", job)

    write_ssh_config(conn, job["deployments"], directory / "ssh_config")
    job["complete"] = True
    save_json(directory / "run.json", job)
    print(f"SSH: ssh -F {directory / 'ssh_config'} {job['deployments'][0]}-mgmt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
