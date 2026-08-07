#!/usr/bin/env bash

# Run a named set of Terragrunt units with the Terragrunt 1.x CLI.
set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage:
  ./deploy_scenario.sh <scenario> <plan|apply|destroy>

Scenarios:
  core    bootstrap
  attack  bootstrap + attacker
  video   bootstrap + videoserver
  demo    bootstrap + attacker + videoserver
EOF
}

[[ $# -eq 2 ]] || {
    usage
    exit 2
}

scenario=$1
command=$2

case "$command" in
    plan | apply | destroy)
        ;;
    *)
        printf 'Unsupported command: %s\n' "$command" >&2
        exit 2
        ;;
esac

# To add a scenario, add one case in the form:
#   name) units=(directory-one directory-two) ;;
case "$scenario" in
    core)
        units=(bootstrap)
        ;;
    attack)
        units=(bootstrap attacker)
        ;;
    video)
        units=(bootstrap videoserver)
        ;;
    demo)
        units=(bootstrap attacker videoserver)
        ;;
    *)
        printf 'Unknown scenario: %s\n' "$scenario" >&2
        usage >&2
        exit 2
        ;;
esac

args=(run --all --queue-strict-include)

for unit in "${units[@]}"; do
    args+=(--queue-include-dir "$unit")
done

# `--` separates Terragrunt flags from the Terraform/OpenTofu command.
args+=(-- "$command")

printf 'Running: terragrunt'
printf ' %q' "${args[@]}"
printf '\n'

exec terragrunt "${args[@]}"
