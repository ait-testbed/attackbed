variable "ghostsserver_image" {
  type        = string
  description = "image of the ghostsserver host"
}

variable "ghostsserver_flavor" {
  type        = string
  description = "flavor of the ghostsserver host"
  default     = "d2-2"
}

variable "ghostsserver_userdata" {
  type        = string
  description = "Userdata for the ghostsserver virtual machine"
  default     = null
}


