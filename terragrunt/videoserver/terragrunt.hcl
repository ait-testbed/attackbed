terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

dependency "bootstrap" {
  config_path = "../bootstrap"
  mock_outputs = {
    network_ids = { for name in ["internet", "lan", "dmz", "admin", "user"] : name => "00000000-0000-0000-0000-000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["destroy"]
  mock_outputs_merge_strategy_with_state  = "shallow"
}

inputs = {
  network_ids = dependency.bootstrap.outputs.network_ids
}

include {
  path = find_in_parent_folders("root.hcl")
}
