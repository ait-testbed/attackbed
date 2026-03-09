terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  dnsserver_image = "atb-corpdns-image-2026-02-26T08-11-32Z"
  videoserver_image = "atb-videoserver-image-2026-02-27T13-46-11Z"
  adminpc_image = "atb-adminpc-image-2026-02-26T13-54-41Z"
  webcam_image = "atb-webcam-image-2026-02-27T14-26-04Z"
} 


include {
  path = find_in_parent_folders("root.hcl")
}
