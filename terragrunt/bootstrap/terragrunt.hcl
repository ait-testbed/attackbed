terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  host_userdata = "firewallinit.yml"
  ext_router = "taq-router" 
  sshkey = "testbed-key"
  inetdns_image = "Ubuntu 22.04"
  inetfw_image = "atb-fw-inet-lan-dmz-image-2023-08-24T13-50-01Z"
  mgmt_image = "Ubuntu 22.04"
  floating_pool = "AECID-provider-network"
} 


include {
  path = find_in_parent_folders()
}
