variable "webcam_image" {
  type        = string
  description = "image of the webcam host"
}

variable "webcam_flavor" {
  type        = string
  description = "flavor of the webcam host"
  default     = "m1.small"
}

variable "webcam_userdata" {
  type        = string
  description = "Userdata for the webcam virtual machine"
  default     = null
}



