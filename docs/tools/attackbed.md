# AttackBed CLI

Run from the repository root with `uv run attackbed`. Requires OpenStack and GitLab state credentials, Packer, Ansible, Terragrunt, and OpenTofu.

## Commands

```sh
uv run attackbed build demo                    # Build required Packer images only
uv run attackbed deploy demo --copies 2        # Deploy with latest matching images
uv run attackbed deploy demo --build --copies 2
uv run attackbed deploy demo --images runs/RUN_ID/images.json
uv run attackbed resume                        # Resume latest run
uv run attackbed resume RUN_ID
uv run attackbed destroy RUN_ID
uv run attackbed destroy demo --copies 2
```

Use `attackbed --help` and `attackbed ACTION --help` for all options.

- `--prefix NAME`: deployment IDs `NAME-001`, `NAME-002`, etc. (default: `lab`).
- `--parallel-copies N`: concurrent labs (default: 4).
- `--tofu-parallelism N`: OpenTofu parallelism per unit (otherwise uses the Terragrunt setting).
- `--debug`: stream full Terragrunt output or Packer diagnostics.
- Deploy and destroy run without confirmation. A run-ID destroy uses saved deployment names; scenario/copies destroy does **not** update a saved run.
- Resume continues the original action; resuming a `build` never deploys.

## Configuration

`config/scenarios.yaml` selects Terragrunt units; `config/image-recipes.yaml` maps Terraform image variables to Packer directories. The CLI builds each required recipe once, or selects the latest active Glance image by recipe `image_name` prefix. Image variables without a Packer recipe use their Terragrunt defaults.

Set shared Packer options in ignored `packer/defaults.json` (copy `defaults.json.example`). Merge order: `packer/RECIPE/default.json.example` → `packer/defaults.json` → optional ignored `packer/RECIPE/default.json`. The recipe override wins; common settings include build network, floating IP pool, and build flavor. Direct Packer invocations do not use this merge.

Deployment settings live in `terragrunt/defaults.tfvars` and optional ignored `terragrunt/terraform.tfvars`.

## Runs and networking

Each invocation saves `runs/RUN_ID/run.json`, image selections in `images.json`, and logs under `logs/` (`packer/RECIPE.log`, `apply.log`, `destroy.log`). Retries append. Successful deployment also writes `ssh_config`. Build-only runs create no OpenStack deployment VMs. A saved image selection can be reused with `deploy --images`.

Bootstrap creates five vRack networks per deployment with VLANs `1000 + (N - 1) * 5` through `+4`, where `N` is the deployment ID's three-digit suffix (`001`–`500`). **Prefixes do not isolate VLANs:** `lab-001` and `test-001` collide. Do not reuse suffixes within the same vRack. Use the same scenario when destroying, including after partial failures.

After successful destroy, the orchestrator deletes empty GitLab Terraform states; it refuses to delete states that still track managed resources. Glance images and logs remain.

Advanced standalone commands use `uv run python -m attackbed.deploy SCENARIO {plan,apply,destroy} --copies N` and write their own run logs. `plan` is not a top-level CLI action.

