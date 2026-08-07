variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "corpdns_image" {
  type        = string
  description = "image of the corpdns-server host"
}

variable "corpdns_flavor" {
  type        = string
  description = "flavor of the corpdns-server host"
  default     = "d2-2"
}

variable "corpdns_userdata" {
  type        = string
  description = "Userdata for the corpdns-server virtual machine"
  default     = null
}

variable "subnet_cidrs" {
  type        = map(string)
  description = "CIDRs for various subnets"
  default = {
    inet = "192.42.0.0/16"
  }
}

variable "contact" {
  description = "Username of the person responsible for this instance (required for resource tracking)"
  type        = string
  default     = "unknown contact"
}
