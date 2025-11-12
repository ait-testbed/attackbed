variable "floating_pool" {
  type        = string
  description = "Pool for floating ip-addresses"
}

variable "target_userdata" {
  type        = string
  description = "Userdata for the target virtual machine"
  default     = null
}

variable "ext_router" {
  type        = string
  description = "name of the external router"
}

variable "target_flavor" {
  type        = string
  description = "flavor of the target"
  default     = "d2-2"
}

variable "target_image" {
  type        = string
  description = "image of the target"
}

variable "target2_image" {
  type        = string
  description = "image of the target"
}

variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "inet_dns" {
  type        = list(string)
  description = "dns servers to configure for the internet"
  default     = ["1.1.1.1","8.8.8.8"] 
}

variable "subnet_cidrs" {
  type        = map(string)
  description = "CIDRs for various subnets"
  default = {
    dmz   = "172.17.100.0/24"
    user = "192.168.50.0/24"
  }
}


variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}
