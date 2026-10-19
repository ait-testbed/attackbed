locals {
  deployment_id = get_env("ATTACKBED_DEPLOYMENT_ID")
  defaults      = jsondecode(read_tfvars_file("${get_repo_root()}/terragrunt/defaults.tfvars"))
  tfvars_file   = "${get_repo_root()}/terragrunt/terraform.tfvars"
  overrides     = fileexists(local.tfvars_file) ? jsondecode(read_tfvars_file(local.tfvars_file)) : {}
  state_name    = "${get_env("OS_PROJECT_NAME")}_${get_env("OS_USER_DOMAIN_NAME")}_${get_env("OS_REGION_NAME", "default")}_${local.deployment_id}_${path_relative_to_include()}"
  state_address = "${get_env("GITLAB_STATE_REPOSITORY")}/${local.state_name}"
}

download_dir = "${get_repo_root()}/.terragrunt-cache/${local.deployment_id}/${path_relative_to_include()}"

terraform {
  copy_terraform_lock_file = false
}

inputs = merge(local.defaults, local.overrides, {
  deployment_id = local.deployment_id
})

remote_state {
  backend = "http"
  config = {
    address        = local.state_address
    lock_address   = "${local.state_address}/lock"
    unlock_address = "${local.state_address}/lock"
    username       = "${get_env("GITLAB_USERNAME")}"
    password       = "${get_env("CR_GITLAB_ACCESS_TOKEN")}"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = "5"
  }
}
