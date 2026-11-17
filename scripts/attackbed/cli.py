"""Build Packer images and manage AttackBed deployments."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

import yaml

from . import deploy
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

def run_terragrunt(root, args, run_dir=None, images_file=None, debug=False):
    previous_images = os.environ.get("ATTACKBED_IMAGES_FILE")
    if run_dir is not None:
        if images_file is not None:
            os.environ["ATTACKBED_IMAGES_FILE"] = str(images_file.resolve())
        else:
            os.environ.pop("ATTACKBED_IMAGES_FILE", None)
    if debug:
        args = [*args, "--debug"]
    try:
        result = deploy.main(args, root / "terragrunt", run_dir=run_dir)
    finally:
        if run_dir is not None:
            if previous_images is None:
                os.environ.pop("ATTACKBED_IMAGES_FILE", None)
            else:
                os.environ["ATTACKBED_IMAGES_FILE"] = previous_images
    if result:
        raise RuntimeError(f"Terragrunt {args[1]} failed; see the run log")


def make_parser():
    parser = argparse.ArgumentParser(description="Build images and manage AttackBed deployments.")
    commands = parser.add_subparsers(dest="action", required=True)

    build = commands.add_parser("build", help="Build scenario images without deploying")
    build.add_argument("scenario", help="Scenario from config/scenarios.yaml")
    build.add_argument("--debug", action="store_true", help="Stream Packer diagnostic output")

    deploy_cmd = commands.add_parser("deploy", help="Deploy scenario using existing or newly built images")
    deploy_cmd.add_argument("scenario", help="Scenario from config/scenarios.yaml")
    source = deploy_cmd.add_mutually_exclusive_group()
    source.add_argument("--build", action="store_true", help="Build images before deploying")
    source.add_argument("--images", type=Path, metavar="FILE", help="Use image selection from JSON file")
    deploy_cmd.add_argument("--copies", type=int, default=1, metavar="N", help="Deploy PREFIX-001 through PREFIX-N (default: 1)")
    deploy_cmd.add_argument("--prefix", default="lab", help="Deployment name prefix (default: lab)")
    deploy_cmd.add_argument("--parallel-copies", type=int, default=4, metavar="N", help="Concurrent deployments (default: 4)")
    deploy_cmd.add_argument("--tofu-parallelism", type=int, metavar="N", help="OpenTofu operations per unit")
    deploy_cmd.add_argument("--debug", action="store_true", help="Stream full Packer and Terragrunt output")

    resume = commands.add_parser("resume", help="Resume a run; defaults to the latest")
    resume.add_argument("run_id", nargs="?", default="latest", metavar="RUN_ID", help="Saved run ID (default: latest)")
    resume.add_argument("--debug", action="store_true", help="Stream full Packer and Terragrunt output")

    destroy_cmd = commands.add_parser("destroy", help="Destroy a saved run or scenario copies")
    destroy_cmd.add_argument("target", help="RUN_ID or scenario name")
    destroy_cmd.add_argument("--copies", type=int, metavar="N", help="Destroy PREFIX-001 through PREFIX-N")
    destroy_cmd.add_argument("--prefix", default="lab", help="Deployment name prefix (default: lab)")
    destroy_cmd.add_argument("--parallel-copies", type=int, metavar="N", help="Concurrent deployments")
    destroy_cmd.add_argument("--tofu-parallelism", type=int, metavar="N", help="OpenTofu operations per unit")
    destroy_cmd.add_argument("--debug", action="store_true", help="Stream full Terragrunt output")

    return parser


def destroy(args, root, parser):
    job = None
    directory = None
    if args.target.startswith("run-"):
        if args.copies is not None or args.prefix != "lab":
            parser.error("RUN_ID cannot be combined with --copies or --prefix")
        directory = resume_directory(root / "runs", args.target)
        job = json.loads((directory / "run.json").read_text())
        if job["action"] == "build":
            parser.error("Build-only runs have no infrastructure to destroy")
        if job.get("destroyed"):
            print(f"Already destroyed: {directory}")
            return 0
        scenario = job["scenario"]
        selection = []
        for name in job["deployments"]:
            selection += ["--deployment", name]
        parallel_copies = args.parallel_copies or job["parallel_copies"]
        tofu_parallelism = args.tofu_parallelism if args.tofu_parallelism is not None else job["tofu_parallelism"]
    else:
        if args.copies is None:
            parser.error("Destroying a scenario requires --copies")
        scenario = args.target
        selection = ["--copies", str(args.copies), "--prefix", args.prefix]
        parallel_copies = args.parallel_copies or 4
        tofu_parallelism = args.tofu_parallelism

    command = [scenario, "destroy", "--parallel-copies", str(parallel_copies), *selection]
    if tofu_parallelism is not None:
        command += ["--tofu-parallelism", str(tofu_parallelism)]
    images_file = directory / "images.json" if directory is not None else None
    if images_file is not None and not images_file.is_file():
        images_file = None
    run_terragrunt(root, command, directory, images_file, args.debug)
    if job is not None:
        job["deployed"] = False
        job["destroyed"] = True
        save_json(directory / "run.json", job)
    return 0


def main(argv=None, root=ROOT):
    parser = make_parser()
    args = parser.parse_args(argv)

    if args.action in ("deploy", "destroy"):
        if args.copies is not None and args.copies < 1:
            parser.error("--copies must be positive")
        if args.parallel_copies is not None and args.parallel_copies < 1:
            parser.error("--parallel-copies must be positive")
        if args.tofu_parallelism is not None and args.tofu_parallelism < 1:
            parser.error("--tofu-parallelism must be positive")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", args.prefix):
            parser.error("Invalid deployment prefix")

    if args.action == "destroy":
        return destroy(args, root, parser)

    runs = root / "runs"
    if args.action == "resume":
        directory = resume_directory(runs, args.run_id)
        job = json.loads((directory / "run.json").read_text())
        if job.get("destroyed"):
            parser.error("This run was destroyed; start a new run")
    else:
        scenarios = yaml.safe_load((root / "config/scenarios.yaml").read_text())
        if args.scenario not in scenarios:
            parser.error(f"Unknown scenario: {args.scenario}")
        units = list(dict.fromkeys(scenarios[args.scenario]))
        if "bootstrap" not in units:
            parser.error("Scenario must include bootstrap")
        directory = runs / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
        directory.mkdir(parents=True, mode=0o700)
        build_images = args.action == "build" or args.build
        image_source = args.images if args.action == "deploy" else None
        job = {
            "action": args.action,
            "scenario": args.scenario,
            "units": units,
            "deployments": ([f"{args.prefix}-{n:03d}" for n in range(1, args.copies + 1)]
                            if args.action == "deploy" else []),
            "mode": "build" if build_images else "file" if image_source else "latest",
            "source_images": str(image_source.expanduser().resolve()) if image_source else None,
            "parallel_copies": args.parallel_copies if args.action == "deploy" else None,
            "tofu_parallelism": args.tofu_parallelism if args.action == "deploy" else None,
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
        packer_logs = directory / "logs" / "packer"
        packer_logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        for role, recipe in recipes.items():
            if role in images:
                active_image(conn, images[role]["id"])
                continue
            print(f"Building {role} ({recipe})", flush=True)
            images[role] = build_image(conn, root, recipe, packer_logs / f"{recipe}.log", debug=args.debug)
            save_json(images_file, images)
    elif not images_file.exists():
        if job["mode"] == "latest":
            images = latest_images(conn, root, recipes)
        else:
            source_file = Path(job["source_images"])
            images = json.loads(source_file.read_text())
        images = {role: active_image(conn, images[role]["id"]) for role in recipes}
        save_json(images_file, images)

    if job["action"] == "build":
        job["complete"] = True
        save_json(directory / "run.json", job)
        print(f"Images: {images_file}")
        return 0

    if not job["deployed"]:
        command = [job["scenario"], "apply", "--parallel-copies", str(job["parallel_copies"])]
        for name in job["deployments"]:
            command += ["--deployment", name]
        if job["tofu_parallelism"] is not None:
            command += ["--tofu-parallelism", str(job["tofu_parallelism"])]
        run_terragrunt(root, command, directory, images_file, args.debug)
        job["deployed"] = True
        save_json(directory / "run.json", job)

    write_ssh_config(conn, job["deployments"], directory / "ssh_config")
    job["complete"] = True
    save_json(directory / "run.json", job)
    print(f"SSH: ssh -F {directory / 'ssh_config'} {job['deployments'][0]}-mgmt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
