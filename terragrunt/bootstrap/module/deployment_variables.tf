variable "deployment_id" {
  type        = string
  description = "Name of this AttackBed deployment"

  validation {
    condition = can(regex("^[a-z][a-z0-9-]*-[0-9]{3}$", var.deployment_id)) && (
      try(tonumber(regex("[0-9]{3}$", var.deployment_id)), 0) >= 1 &&
      try(tonumber(regex("[0-9]{3}$", var.deployment_id)), 999) <= 500
    )
    error_message = "Deployment ID must end in a three-digit number from 001 to 500 (e.g. lab-001)."
  }
}
