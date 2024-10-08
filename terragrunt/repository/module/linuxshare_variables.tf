variable "linuxshare_image" {
  type        = string
  description = "image of the linuxshare host"
}

variable "linuxshare_flavor" {
  type        = string
  description = "flavor of the linuxshare host"
  default     = "d2-4"
}

variable "linuxshare_userdata" {
  type        = string
  description = "Userdata for the linuxshare virtual machine"
  default     = null
}

variable "lan_cidr" {
  type        = string
  description = "CIDR of the lan subnet"
  default     = "192.168.100.0/24"
}

variable "linuxshare_dns" {
  type        = string
  description = "DNS-Server to use. Only the last ip-segment"
  default     = "254"
}
