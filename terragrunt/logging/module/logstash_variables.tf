variable "logstash_image" {
  type        = string
  description = "image of the logstash host"
}

variable "logstash_flavor" {
  type        = string
  description = "flavor of the logstash host"
  default     = "m1.large"
}

variable "logstash_userdata" {
  type        = string
  description = "Userdata for the logstash virtual machine"
  default     = null
}
