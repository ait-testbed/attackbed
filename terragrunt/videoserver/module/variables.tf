variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}


variable "admin_cidr" {
  type        = string
  description = "CIDR of the admin subnet"
  default     = "10.12.0.0/24 "
}

variable "user_cidr" {
  type        = string
  description = "CIDR of the user subnet"
  default     = "10.11.0.0/16"
}