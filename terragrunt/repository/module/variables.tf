variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "contact" {
  description = "Username of the person responsible for this instance (required for resource tracking)"
  type        = string
  default = "unknown contact"
}
