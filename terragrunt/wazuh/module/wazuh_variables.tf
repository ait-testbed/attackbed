variable "wazuh_image" {
  type        = string
  description = "image of the wazuh host"
}

variable "wazuh_flavor" {
  type        = string
  description = "flavor of the wazuh host"
  default     = "d2-2"
}

variable "wazuh_userdata" {
  type        = string
  description = "Userdata for the wazuh virtual machine"
  default     = null
}


