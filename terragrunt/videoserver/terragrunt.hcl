terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  dnsserver_image = "atb-corpdns-image-2023-05-31T13-10-03Z"
  videoserver_image = "atb-videoserver-image-2023-06-06T12-51-17Z"
} 


include {
  path = find_in_parent_folders()
}
