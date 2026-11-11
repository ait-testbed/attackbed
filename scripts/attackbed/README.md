# AttackBed CLI

Run from the repository root with `uv run attackbed` (requires Packer, Ansible, Terragrunt,
OpenTofu, OpenStack credentials and the existing GitLab state credentials).

```sh
uv run attackbed demo --build --copies 2
uv run attackbed demo --copies 2
uv run attackbed demo --images runs/RUN_ID/images.json --copies 5
uv run attackbed --resume
uv run attackbed --resume RUN_ID
```

`--build` builds each scenario-required Packer image once in OpenStack; every
Packer recipe in `scripts/attackbed/recipes.yaml` needs its own ignored
`packer/RECIPE/default.json` (based on `default.json.example`) configured for
the **target cloud**. Before `packer init` and `packer build`, the CLI installs
Ansible Galaxy roles from each recipe's `playbook/requirements.yml` into its own
ignored `playbook/roles/` directory.

Without `--build` or `--images`, it selects the newest active Glance image
matching each recipe's `image_name` prefix. Images without a recipe (currently
`mgmt_image` and `inetdns_image`) retain their existing Terragrunt defaults.
A missing required image is an error, not a silent substitution.

Each run stores its image UUIDs/names, progress, and logs under `runs/RUN_ID/`.
Resume skips successfully built images and retries deployments using OpenTofu
state. A resumed run always uses its saved image selections, never newer ones.
Existing labs with the same names may be modified; use `--prefix` when you
want a separate deployment set.

`--parallel-copies` defaults to 4; `--tofu-parallelism` has no CLI default and
uses the existing Terragrunt HCL default when omitted. After deployment,
`runs/RUN_ID/ssh_config` provides per-lab SSH aliases (management VM via
floating IP, other VMs via ProxyJump). SSH assumes `ubuntu` except Debian
videoserver/linuxshare images; edit the generated config if your images differ.
