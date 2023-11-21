variable "reposerver_image" {
  type        = string
  description = "image of the reposerver host"
}

variable "reposerver_flavor" {
  type        = string
  description = "flavor of the reposerver host"
  default     = "m1.medium"
}

variable "reposerver_userdata" {
  type        = string
  description = "Userdata for the reposerver virtual machine"
  default     = null
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}

variable "reposerver_dns" {
  type        = string
  description = "DNS-Server to use. Only the last ip-segment"
  default     = "254"
}
