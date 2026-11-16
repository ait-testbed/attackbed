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



def destroy(argv, root):
    parser = argparse.ArgumentParser(prog="attackbed destroy", description="Destroy AttackBed deployments.")
    parser.add_argument("target", help="Scenario or saved RUN_ID")
    parser.add_argument("--copies", type=int, help="Destroy PREFIX-001 through PREFIX-N")
    parser.add_argument("--prefix", default="lab")
    parser.add_argument("--parallel-copies", type=int)
    parser.add_argument("--tofu-parallelism", type=int)
    parser.add_argument("--yes", action="store_true", help="Confirm infrastructure destruction")
    args = parser.parse_args(argv)
    if not args.yes:
        parser.error("destroy requires --yes")
    if args.copies is not None and args.copies < 1:
        parser.error("--copies must be positive")
    if args.parallel_copies is not None and args.parallel_copies < 1:
        parser.error("--parallel-copies must be positive")
    if args.tofu_parallelism is not None and args.tofu_parallelism < 1:
        parser.error("--tofu-parallelism must be positive")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", args.prefix):
        parser.error("Invalid deployment prefix")

    job = None
    directory = None
    if args.target.startswith("run-"):
        if args.copies is not None or args.prefix != "lab":
            parser.error("Run ID cannot be combined with --copies or --prefix")
        directory = resume_directory(root / "runs", args.target)
        job = json.loads((directory / "run.json").read_text())
        if job.get("destroyed"):
            print(f"Already destroyed: {directory}")
            return 0
        scenario = job["scenario"]
        selection = [item for name in job["deployments"] for item in ("--deployment", name)]
        parallel_copies = args.parallel_copies or job["parallel_copies"]
        tofu_parallelism = args.tofu_parallelism if args.tofu_parallelism is not None else job["tofu_parallelism"]
    else:
        if args.copies is None:
            parser.error("Destroying a scenario requires --copies")
        scenario = args.target
        selection = ["--copies", str(args.copies), "--prefix", args.prefix]
        parallel_copies = args.parallel_copies or 4
        tofu_parallelism = args.tofu_parallelism

    cmd = [sys.executable, str(root / "terragrunt/deploy_scenario.py"), scenario, "destroy", "--yes",
           "--parallel-copies", str(parallel_copies), *selection]
    if tofu_parallelism is not None:
        cmd += ["--tofu-parallelism", str(tofu_parallelism)]
    env = os.environ.copy()
    if directory is not None:
        env.pop("ATTACKBED_IMAGES_FILE", None)
        images_file = directory / "images.json"
        if images_file.is_file():
            env["ATTACKBED_IMAGES_FILE"] = str(images_file.resolve())
    subprocess.run(cmd, cwd=root, env=env, check=True)
    if job is not None:
        job["deployed"] = False
        job["destroyed"] = True
        save_json(directory / "run.json", job)
    return 0

def main(argv=None, root=ROOT):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "destroy":
        return destroy(argv[1:], root)
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog="Destroy: attackbed destroy SCENARIO --copies N --yes, or destroy RUN_ID --yes")
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
        if job.get("destroyed"):
            parser.error("This run was destroyed; start a new run")
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
