variable "kafka_image" {
  type        = string
  description = "image of the kafka host"
}

variable "kafka_flavor" {
  type        = string
  description = "flavor of the kafka host"
  default     = "m1.large"
}

variable "kafka_userdata" {
  type        = string
  description = "Userdata for the kafka virtual machine"
  default     = null
}
