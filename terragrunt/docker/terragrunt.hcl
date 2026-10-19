terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

dependency "bootstrap" {
  config_path = "../bootstrap"
}

inputs = {
  network_ids = dependency.bootstrap.outputs.network_ids
}

include {
  path = find_in_parent_folders("root.hcl")
}
