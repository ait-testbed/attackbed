variable "elastic_image" {
  type        = string
  description = "image of the elastic host"
}

variable "elastic_flavor" {
  type        = string
  description = "flavor of the elastic host"
  default     = "m1.large"
}

variable "elastic_userdata" {
  type        = string
  description = "Userdata for the elastic virtual machine"
  default     = null
}
