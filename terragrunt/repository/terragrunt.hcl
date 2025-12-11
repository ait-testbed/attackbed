terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  reposerver_image = "atb-repository-image-2023-10-11T12-22-24Z"
} 


include {
  path = find_in_parent_folders("root.hcl")
}
