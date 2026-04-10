variable "opensearch_image" {
  type        = string
  description = "image of the opensearch host"
}

variable "opensearch_flavor" {
  type        = string
  description = "flavor of the opensearch host"
  default     = "d2-8"
}

variable "opensearch_userdata" {
  type        = string
  description = "Userdata for the opensearch virtual machine"
  default     = null
}
