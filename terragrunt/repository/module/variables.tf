variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "contact" {
  description = "Email of the person responsible for this instance (required for resource tracking)"
  type        = string

  validation {
    condition     = length(trimspace(var.contact)) > 0
    error_message = "The 'contact' variable must be provided"
  }
}
