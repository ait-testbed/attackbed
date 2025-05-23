variable "userpc_image" {
  type        = string
  description = "image of the userpc host"
}

variable "userpc_flavor" {
  type        = string
  description = "flavor of the userpc host"
  default     = "d2-2"
}

variable "userpc_userdata" {
  type        = string
  description = "Userdata for the userpc virtual machine"
  default     = null
}

variable "user_cidr" {
  type        = string
  description = "CIDR of the user subnet"
  default     = "192.168.50.0/24"
}
