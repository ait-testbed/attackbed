terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  docker_image = "atb-docker-image-2025-04-25T15-42-30Z"
} 


include {
  path = find_in_parent_folders("root.hcl")
}
