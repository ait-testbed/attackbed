terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  host_userdata = "firewallinit.yml"
  ext_router = "aecid-testbed-router" 
  sshkey = "testbed-key"
  inetdns_image = "ubuntu-2204"
  inetfw_image = "atb-fw-inet-lan-dmz-image-2023-06-09T14-03-06Z"
  mgmt_image = "ubuntu-2204"
  floating_pool = "provider-aecid-208"
} 


include {
  path = find_in_parent_folders()
}
