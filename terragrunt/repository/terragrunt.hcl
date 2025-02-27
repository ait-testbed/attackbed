terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  reposerver_image = "atb-repository-2025-02-24T13-16-52Z"
  adminpc_iamge = "atb-adminpc-image-2025-02-06T12-22-47Z"
  linuxshare_image = "image atb-linuxshare-2025-02-24T14-36-42Z"
} 


include {
  path = find_in_parent_folders()
}
