terraform {
  backend "http" {}
}

locals {
  ext_dns_userdata_file = var.ext_dns_userdata == null ? "${path.module}/scripts/dns.yml" : var.ext_dns_userdata
  fw_userdata_file    = var.fw_userdata == null ? "${path.module}/scripts/firewallinit.yml" : var.fw_userdata
  mgmt_userdata_file    = var.mgmt_userdata == null ? "${path.module}/scripts/mgmtinit.yml" : var.mgmt_userdata
}


data "openstack_networking_router_v2" "router" {
  name = var.ext_router
}

###################################################################
#
# CREATE NETWORK "Internet"
#
resource "openstack_networking_network_v2" "internet" {
  name           = "internet"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "internet_subnet" {
  name       = "internet_subnet"
  network_id = "${openstack_networking_network_v2.internet.id}"
  cidr       = var.subnet_cidrs["inet"]
  dns_nameservers = var.inet_dns
  ip_version = 4
}

resource "openstack_networking_router_interface_v2" "router_interface_inet" {
  router_id = data.openstack_networking_router_v2.router.id
  subnet_id = "${openstack_networking_subnet_v2.internet_subnet.id}"
}

####################################################################
#
# CREATE INSTANCE for "Internet-DNS"
#
data "template_file" "userdata_dns" {
  template = "${file("${local.ext_dns_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitdns" {
  count         = local.ext_dns_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_dns.rendered
  }
}

data "openstack_images_image_v2" "inet-dns-image" {
  name        = var.inetdns_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "inet-dns" {
  name        = "inetdns"
  flavor_name = var.inetdns_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.inet-dns-image.id
  user_data    = local.ext_dns_userdata_file == null ? null : data.template_cloudinit_config.cloudinitdns[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    name = "internet"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"],514)
  }

  depends_on = [
     openstack_networking_network_v2.internet,
  ]

}

###################################################################
#
# CREATE NETWORK "LAN"
#
resource "openstack_networking_network_v2" "lan" {
  name           = "lan"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "lan_subnet" {
  name       = "lan_subnet"
  network_id = "${openstack_networking_network_v2.lan.id}"
  cidr       = var.subnet_cidrs["lan"]
  ip_version = 4
  gateway_ip = cidrhost(var.subnet_cidrs["lan"],254)
  dns_nameservers = [cidrhost(var.subnet_cidrs["lan"],254)]

  # make the allocation_pool smaller for gateway_ip
  allocation_pool {
    start = cidrhost(var.subnet_cidrs["lan"],20)
    end   = cidrhost(var.subnet_cidrs["lan"],200)
  }
}

###################################################################
#
# CREATE NETWORK "DMZ"
#
resource "openstack_networking_network_v2" "dmz" {
  name           = "dmz"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "dmz_subnet" {
  name       = "dmz_subnet"
  network_id = "${openstack_networking_network_v2.dmz.id}"
  cidr       = var.subnet_cidrs["dmz"]
  ip_version = 4
  gateway_ip = cidrhost(var.subnet_cidrs["dmz"],254)
  dns_nameservers = [cidrhost(var.subnet_cidrs["dmz"],254)]


  # make the allocation_pool smaller for gateway_ip
  allocation_pool {
    start = cidrhost(var.subnet_cidrs["dmz"],20)
    end   = cidrhost(var.subnet_cidrs["dmz"],200)
  }
}

###################################################################
#
# CREATE NETWORK "ADMIN"
#
resource "openstack_networking_network_v2" "admin" {
  name           = "admin"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "admin_subnet" {
  name       = "admin_subnet"
  network_id = "${openstack_networking_network_v2.admin.id}"
  cidr       = var.subnet_cidrs["admin"]
  ip_version = 4
  gateway_ip = cidrhost(var.subnet_cidrs["admin"],254)
  dns_nameservers = [cidrhost(var.subnet_cidrs["admin"],254)]


  # make the allocation_pool smaller for gateway_ip
  allocation_pool {
    start = cidrhost(var.subnet_cidrs["admin"],20)
    end   = cidrhost(var.subnet_cidrs["admin"],200)
  }
}

###################################################################
#
# CREATE NETWORK "USER"
#
resource "openstack_networking_network_v2" "user" {
  name           = "user"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "user_subnet" {
  name       = "user_subnet"
  network_id = "${openstack_networking_network_v2.user.id}"
  cidr       = var.subnet_cidrs["user"]
  ip_version = 4
  gateway_ip = cidrhost(var.subnet_cidrs["user"],254)
  dns_nameservers = [cidrhost(var.subnet_cidrs["user"],254)]


  # make the allocation_pool smaller for gateway_ip
  allocation_pool {
    start = cidrhost(var.subnet_cidrs["user"],20)
    end   = cidrhost(var.subnet_cidrs["user"],200)
  }
}



####################################################################
#
# CREATE INSTANCE for "Internet-Firewall"
#
data "template_file" "userdata_inetfw" {
  template = "${file("${local.fw_userdata_file}")}"
  vars = {
      dns_server_address = "${openstack_compute_instance_v2.inet-dns.access_ip_v4}"
  }
}

data "template_cloudinit_config" "cloudinitinetfw" {
  count         = local.fw_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_inetfw.rendered
  }
}

data "openstack_images_image_v2" "inet-fw-image" {
  name        = var.inetfw_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "inet-fw" {
  name        = "inetfw"
  flavor_name = var.inetfw_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.inet-fw-image.id
  user_data    = local.fw_userdata_file == null ? null : data.template_cloudinit_config.cloudinitinetfw[0].rendered

    metadata = {
    contact = var.contact
  }

  network {
    name = "internet"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"],254)
  }

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["lan"],254)
  }

  network {
    name = "dmz"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["dmz"],254)
  }

  network {
    name = "admin"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["admin"],254)
  }

  network {
    name = "user"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["user"],254)
  }

  depends_on = [
     openstack_compute_instance_v2.inet-dns,
     openstack_networking_network_v2.dmz,
     openstack_networking_network_v2.internet,
     openstack_networking_network_v2.lan,
     openstack_networking_network_v2.admin,
     openstack_networking_network_v2.user
  ]
}


####################################################################
#
# CREATE INSTANCE for "Management Host"
#
data "template_file" "userdata_mgmt" {
  template = "${file("${local.mgmt_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitmgmt" {
  count         = local.mgmt_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_mgmt.rendered
  }
}

data "openstack_images_image_v2" "mgmt-image" {
  name        = var.mgmt_image
  most_recent = true
}

locals {
  mgmt_ips = {
    internet = cidrhost(var.subnet_cidrs["inet"], 201)
    lan      = cidrhost(var.subnet_cidrs["lan"], 201)
    dmz      = cidrhost(var.subnet_cidrs["dmz"], 201)
    admin    = cidrhost(var.subnet_cidrs["admin"], 201)
    user    = cidrhost(var.subnet_cidrs["user"], 201)
  }
}

resource "openstack_compute_instance_v2" "mgmt" {
  name        = "mgmt"
  flavor_name = var.mgmt_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.mgmt-image.id
  user_data    = local.mgmt_userdata_file == null ? null : data.template_cloudinit_config.cloudinitmgmt[0].rendered

    metadata = {
    contact = var.contact
  }

  network {
    name = "internet"
    fixed_ip_v4 = local.mgmt_ips.internet
  }

  network {
    name = "lan"
    fixed_ip_v4 = local.mgmt_ips.lan
  }

  network {
    name = "dmz"
    fixed_ip_v4 = local.mgmt_ips.dmz
  }

  network {
    name = "admin"
    fixed_ip_v4 = local.mgmt_ips.admin
  }

  network {
    name = "user"
    fixed_ip_v4 = local.mgmt_ips.user
  }

  depends_on = [
     openstack_networking_network_v2.dmz,
     openstack_networking_network_v2.internet,
     openstack_networking_network_v2.lan,
     openstack_networking_network_v2.admin,
     openstack_networking_network_v2.user
  ]
}

data "openstack_networking_port_v2" "mgmt"{
  fixed_ip =  local.mgmt_ips.internet
    depends_on = [
      openstack_compute_instance_v2.mgmt  
  ]
}

### a floating ip with this description has to be already allocated to the project 
### (via horizon dashboard or openstack sdk) and not assigned to any other host 

data "openstack_networking_floatingip_v2" "mgmt" {
  description = "mgmt"
}

resource "openstack_networking_floatingip_associate_v2" "mgmt" {
  floating_ip = data.openstack_networking_floatingip_v2.mgmt.address
  port_id     = data.openstack_networking_port_v2.mgmt.id

  depends_on = [
     data.openstack_networking_port_v2.mgmt,
     data.openstack_networking_floatingip_v2.mgmt
  ]
}


locals {
    ext_dnsserver_userdata_file = var.dnsserver_userdata == null ? "${path.module}/scripts/corpdns.yml" : var.dnsserver_userdata
}

####################################################################
#
# CREATE INSTANCE for "DNS-Server"
#
data "template_file" "userdata_dnsserver" {
  template = "${file("${local.ext_dnsserver_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitdnsserver" {
  count         = local.ext_dnsserver_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_dnsserver.rendered
  }
}

data "openstack_images_image_v2" "dnsserver-image" {
  name        = var.dnsserver_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "dnsserver" {
  name        = "corpdns"
  flavor_name = var.dnsserver_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.dnsserver-image.id
  user_data    = local.ext_dnsserver_userdata_file == null ? null : data.template_cloudinit_config.cloudinitdnsserver[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    name = "internet"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"], 233)
    
  }

  depends_on = [
    openstack_networking_network_v2.internet,
  ]
}