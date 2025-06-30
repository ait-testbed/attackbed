terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  videoserver_image = "atb-videoserver-image-2024-07-09T11-00-42Z"
  adminpc_image = "atb-adminpc-image-2024-07-03T11-47-38Z"
  attacker_image = "atb-attacker-image-2024-07-03T11-58-41Z"
}


include {
  path = find_in_parent_folders()
}
