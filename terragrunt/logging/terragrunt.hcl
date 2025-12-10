terraform {
    source = ".//module"

    extra_arguments "parallelism" {
      commands  = ["apply"]
      arguments = ["-parallelism=${get_env("TF_VAR_parallelism", "10")}"]
    }
}

inputs = {
  sshkey = "testbed-key"
  opensearch_image = "atb-opensearch-image-2024-11-18T17-51-20Z"
  kafka_image = "atb-kafka-image-2024-11-19T14-15-49Z"
  logstash_image = "atb-logstash-image-2024-12-05T12-51-50Z"
}


include {
  path = find_in_parent_folders("root.hcl")
}
