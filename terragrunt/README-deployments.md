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
python3 terragrunt/deploy_scenario.py demo apply --copies 3 --parallelism 2 --yes
python3 terragrunt/deploy_scenario.py demo plan --deployment lab-002
python3 terragrunt/deploy_scenario.py demo destroy --copies 3 --parallelism 2 --yes
```

Use `--deployment` repeatedly to select explicit IDs, or use `--copies N` and
`--prefix` for IDs such as `lab-001` through `lab-00N`. `--parallelism` limits
the number of concurrent deployment workers, and thus concurrent Terragrunt
processes. Each Terragrunt process retains OpenTofu's usual resource-level
parallelism.

A new lab's workload plans may require bootstrap outputs to exist first. To
plan bootstrap alone, run Terragrunt directly in `terragrunt/bootstrap` with
`ATTACKBED_DEPLOYMENT_ID` set.

No deployment manifests are stored. Select the same scenario units when
tearing down a deployment. Failed operations stop that lab without affecting
other lab workers, and a failed workload destroy leaves its bootstrap intact.
Destroy does not remove the local `.terragrunt-cache`.

The script expects the usual OpenStack/GitLab environment and `terragrunt`,
OpenTofu, and the OpenStack CLI (for gateway attachment) on `PATH`.
