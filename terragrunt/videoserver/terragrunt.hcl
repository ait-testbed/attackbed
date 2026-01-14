terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  dnsserver_image = "atb-corpdns-image-2023-08-24T13-25-37Z"
  videoserver_image = "atb-videoserver-image-2023-08-25T13-54-02Z"
  adminpc_image = "atb-adminpc-image-2023-08-24T12-25-50Z"
} 


include {
  path = find_in_parent_folders("root.hcl")
}
