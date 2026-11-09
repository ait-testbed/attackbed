# Parallel AttackBed deployments

`deploy_scenario.py` runs the existing Terragrunt units for multiple independent
AttackBed deployments. It does not generate or copy Terragrunt configurations.
Each deployment uses its own state, OpenStack resources and cache, selected by
`ATTACKBED_DEPLOYMENT_ID`.

Install the repository's Python requirements in your active virtual environment:

```sh
uv pip install -r requirements.txt
```

Configure the units for each scenario in `terragrunt/scenarios.yaml`.
Bootstrap runs first when applying and last when destroying. Units within one
lab run sequentially; different labs run in parallel.

From the repository root:

```sh
python3 terragrunt/deploy_scenario.py demo apply --copies 3 --parallel-copies 2 --tofu-parallelism 3 --yes
python3 terragrunt/deploy_scenario.py demo plan --deployment lab-002
python3 terragrunt/deploy_scenario.py demo destroy --copies 3 --parallel-copies 2 --tofu-parallelism 3 --yes
```

Use `--deployment` repeatedly to select explicit IDs, or use `--copies N` and
`--prefix` for IDs such as `lab-001` through `lab-00N`. `--parallel-copies`
limits the number of concurrent deployments.
`--tofu-parallelism` overrides the Terragrunt `apply` setting (from
`TF_VAR_parallelism`, default 10), or passes `-parallelism=N` to `plan` and
`destroy`. When omitted, the existing settings apply. These two controls are
independent.

For OVHcloud, bootstrap explicitly assigns five vRack VLAN IDs per deployment:
`1000 + (N - 1) * 5` for internet, followed by LAN, DMZ, admin, and user.
Deployment IDs must end in `001`–`500`. The numeric suffix must be unique
across deployments, including different prefixes or regions sharing a vRack.
Ensure the calculated VLANs are unused (including any manual test networks).
Changing existing networks to explicit VLANs may require their replacement.

A new lab's workload plans may require bootstrap outputs to exist first. To
plan bootstrap alone, run Terragrunt directly in `terragrunt/bootstrap` with
`ATTACKBED_DEPLOYMENT_ID` set.

No deployment manifests are stored. Select the same scenario units when
tearing down a deployment. Failed operations stop that lab without affecting
other lab workers, and a failed workload destroy leaves its bootstrap intact.
Destroy does not remove the local `.terragrunt-cache`.

The script expects the usual OpenStack/GitLab environment and `terragrunt`,
OpenTofu, and the OpenStack CLI (for gateway attachment) on `PATH`.
