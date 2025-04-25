variable "docker_image" {
  type        = string
  description = "image of the docker host"
}

variable "docker_flavor" {
  type        = string
  description = "flavor of the docker host"
  default     = "d2-2"
}

variable "docker_userdata" {
  type        = string
  description = "Userdata for the docker virtual machine"
  default     = null
}


