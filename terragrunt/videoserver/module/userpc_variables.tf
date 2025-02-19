variable "userpc_image" {
  type        = string
  description = "image of the userpc host"
}

variable "userpc_flavor" {
  type        = string
  description = "flavor of the userpc host"
  default     = "m1.small"
}

variable "userpc_userdata" {
  type        = string
  description = "Userdata for the userpc virtual machine"
  default     = null
}

variable "user_cidr" {
  type        = string
  description = "CIDR of the user subnet"
  default     = TODO
}
