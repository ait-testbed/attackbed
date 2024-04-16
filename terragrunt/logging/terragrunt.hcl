terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  attacker_image = "atb-attacker-image-2023-08-24T12-53-52Z"
} 


include {
  path = find_in_parent_folders()
}
