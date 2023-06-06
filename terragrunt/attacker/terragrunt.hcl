terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  attacker_image = "atb-attacker-image-2023-05-25T14-34-37Z"
} 


include {
  path = find_in_parent_folders()
}
