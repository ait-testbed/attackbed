variable "floating_pool" {
  type        = string
  description = "Pool for floating ip-addresses"
}

variable "client_userdata" {
  type        = string
  description = "Userdata for the client virtual machine"
  default     = null
}

variable "ext_router" {
  type        = string
  description = "name of the external router"
}

variable "client_flavor" {
  type        = string
  description = "flavor of the client"
  default     = "d2-2"
}

variable "client_image" {
  type        = string
  description = "image of the client"
}

variable "client_dns" {
  type        = string
  description = "DNS-Server to use. Only the last ip-segment"
  default     = "254"
}

variable "sshkey" {
  type        = string
  description = "ssh-key for administration"
}

variable "inet_dns" {
  type        = list(string)
  description = "dns servers to configure for the internet"
  default     = ["1.1.1.1","8.8.8.8"] 
}

variable "subnet_cidrs" {
  type        = map(string)
  description = "CIDRs for various subnets"
  default = {
    dmz   = "172.17.100.0/24"
    user = "192.168.50.0/24"
  }
}

variable "fw_proxy_port" {
  description = "The proxy server address"
  type        = string
  default     = "192.168.50.254:3128"
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

