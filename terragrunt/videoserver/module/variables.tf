variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}

variable "contact" {
  description = "Username of the person responsible for this instance (required for resource tracking)"
  type        = string
  default = "unknown contact"
}
