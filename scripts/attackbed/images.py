"""Build or discover OpenStack images for the requested Terraform units."""

import json
from pathlib import Path
import re
import subprocess
from uuid import UUID

import yaml


def required_recipes(root, units):
    recipes = yaml.safe_load((root / "config/image-recipes.yaml").read_text())
    variables = set()
    for unit in units:
        for path in (root / "terragrunt" / unit / "module").glob("*.tf"):
            variables.update(re.findall(r'variable\s+"(\w+_image)"', path.read_text()))
    return {name: recipes[name] for name in sorted(variables & recipes.keys())}


def recipe_config(root, recipe, build=False):
    directory = root / "packer" / recipe
    example = directory / "default.json.example"
    shared = root / "packer" / "defaults.json"
    local = directory / "default.json"
    config = {}
    overrides = {}
    for path in (example, shared, local):
        if path.is_file():
            values = json.loads(path.read_text())
            if not isinstance(values, dict):
                raise ValueError(f"{path} must contain a JSON object")
            config.update(values)
            if path != example:
                overrides.update(values)
    if build and any(not overrides.get(key) for key in ("network", "floating_ip_pool")):
        raise ValueError(f"Configure network and floating_ip_pool in {shared} or {local}")
    if not config:
        raise ValueError(f"Missing Packer configuration for {recipe}")
    return config


def active_image(conn, image_id):
    image = conn.image.get_image(image_id)
    if not image or image.status.lower() != "active":
        raise ValueError(f"Image {image_id} is missing or not active")
    return {"id": image.id, "name": image.name}


def latest_images(conn, root, recipes):
    available = list(conn.image.images())
    selected = {}
    for role, recipe in recipes.items():
        config = recipe_config(root, recipe)
        prefix = config["image_name"]
        matches = [image for image in available if image.status.lower() == "active"
                   and (image.name == prefix or (config.get("timestamp_image", True)
                        and image.name.startswith(prefix + "-")))]
        if not matches:
            raise ValueError(f"No active image found for {role} ({prefix}); use --build")
        image = max(matches, key=lambda entry: entry.created_at or "")
        selected[role] = {"id": image.id, "name": image.name}
    return selected


def build_image(conn, root, recipe, log_path):
    config = recipe_config(root, recipe, build=True)
    directory = root / "packer" / recipe
    subprocess.run(
        ["ansible-galaxy", "role", "install", "-r", "playbook/requirements.yml", "-p", "playbook/roles"],
        cwd=directory, check=True,
    )
    subprocess.run(["packer", "init", "."], cwd=directory, check=True)
    config_file = log_path.with_suffix(".vars.json")
    config_file.touch(mode=0o600)
    config_file.chmod(0o600)
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    image_id = None
    log_path.touch(mode=0o600)
    log_path.chmod(0o600)
    with log_path.open("a", buffering=1) as logfile:
        logfile.write(f"\n--- Packer build: {recipe} ---\n")
        with subprocess.Popen(
            ["packer", "-machine-readable", "build", f"-var-file={config_file.resolve()}", "."],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ) as process:
            for line in process.stdout:
                logfile.write(line)
                fields = line.rstrip("\n").split(",", 5)
                if len(fields) == 6 and fields[2] == "artifact" and fields[4] == "id":
                    value = fields[5].strip().rsplit(":", 1)[-1]
                    try:
                        image_id = str(UUID(value))
                    except ValueError:
                        pass
                if len(fields) >= 5 and fields[2] == "ui" and fields[3] in ("say", "message", "error"):
                    print(fields[4], flush=True)
            if process.wait():
                raise RuntimeError(f"Packer {recipe} failed; see {log_path}")
    if image_id is None:
        raise RuntimeError(f"Packer {recipe} returned no image UUID; see {log_path}")
    return active_image(conn, image_id)
