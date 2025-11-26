variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "lan_cidr" {
  type        = string
  description = "CIDR of the server subnet"
  default     = "192.168.100.0/24"
}

variable "contact" {
  description = "Username of the person responsible for this instance (required for resource tracking)"
  type        = string
  default = "unknown contact"
}
