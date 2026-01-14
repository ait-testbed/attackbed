terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  ext_router = "taq-router" 
  sshkey = "testbed-key"
  target_image=""
} 


include {
  path = find_in_parent_folders("root.hcl")
}
