variable "deployment_id" {
  type        = string
  description = "Name of this AttackBed deployment"
}

variable "network_ids" {
  type        = map(string)
  description = "Network UUIDs from this deployment's bootstrap"
}
