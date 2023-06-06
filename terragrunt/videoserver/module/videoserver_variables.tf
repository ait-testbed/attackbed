variable "videoserver_image" {
  type        = string
  description = "image of the videoserver host"
}

variable "videoserver_flavor" {
  type        = string
  description = "flavor of the videoserver host"
  default     = "m1.small"
}

variable "videoserver_userdata" {
  type        = string
  description = "Userdata for the videoserver virtual machine"
  default     = null
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}
