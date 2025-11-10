variable "attacker_image" {
  type        = string
  description = "image of the attacker host"
}

variable "attacker_flavor" {
  type        = string
  description = "flavor of the attacker host"
  default     = "r3-16"
}

variable "attacker_userdata" {
  type        = string
  description = "Userdata for the attacker virtual machine"
  default     = null
}
