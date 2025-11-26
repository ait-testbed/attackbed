variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "dmz_cidr" {
  type        = string
  description = "CIDR of the dmz subnet"
  default     = "172.17.100.0/24"
}

variable "contact" {
  description = "Email of the person responsible for this instance (required for resource tracking)"
  type        = string

  validation {
    condition     = length(trimspace(var.contact)) > 0
    error_message = "The 'contact' variable must be provided"
  }
}
