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
  videoserver_image = "aincept-videoserver-image-2023-04-20T09-48-55Z"
} 


include {
  path = find_in_parent_folders()
}
