variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}
