terraform {
  source = ".//module"

  extra_arguments "parallelism" {
    commands  = ["apply"]
    arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
  }
}

inputs = {
  sshkey        = "testbed-key"
  corpdns_image = "atb-corpdns-image-2026-02-26T08-11-32Z"
}


include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependencies {
  paths = ["../bootstrap"]
}
