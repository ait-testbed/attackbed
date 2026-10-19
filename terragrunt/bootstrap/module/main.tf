terraform {
  backend "http" {}
}

locals {
  ext_dns_userdata_file = var.ext_dns_userdata == null ? "${path.module}/scripts/dns.yml" : var.ext_dns_userdata
  fw_userdata_file    = var.fw_userdata == null ? "${path.module}/scripts/firewallinit.yml" : var.fw_userdata
  mgmt_userdata_file    = var.mgmt_userdata == null ? "${path.module}/scripts/mgmtinit.yml" : var.mgmt_userdata
  ext_dnsserver_userdata_file = var.corpdns_userdata == null ? "${path.module}/scripts/corpdns.yml" : var.corpdns_userdata
}


data "openstack_networking_network_v2" "external" {
  name     = var.floating_pool
  external = true
}

resource "openstack_networking_router_v2" "router" {
  name           = "${var.deployment_id}-router"
  admin_state_up = true
}

# Retry Neutron gateway updates separately from router creation.
resource "terraform_data" "router_gateway" {
  triggers_replace = {
    router_id  = openstack_networking_router_v2.router.id
    network_id = data.openstack_networking_network_v2.external.id
  }

  provisioner "local-exec" {
    command = "python3 \"${path.module}/scripts/router_gateway.py\" attach"
    environment = {
      ROUTER_ID  = self.triggers_replace.router_id
      NETWORK_ID = self.triggers_replace.network_id
    }
  }

  provisioner "local-exec" {
    when    = destroy
    command = "python3 \"${path.module}/scripts/router_gateway.py\" detach"
    environment = {
      ROUTER_ID  = self.triggers_replace.router_id
      NETWORK_ID = self.triggers_replace.network_id
    }
  }
}

###################################################################
#
# CREATE NETWORK "Internet"
#
resource "openstack_networking_network_v2" "internet" {
  name           = "${var.deployment_id}-internet"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "internet_subnet" {
  name       = "${var.deployment_id}-internet_subnet"
  network_id = "${openstack_networking_network_v2.internet.id}"
  cidr       = var.subnet_cidrs["inet"]
  dns_nameservers = var.inet_dns
  ip_version = 4
  allocation_pool {
    start = cidrhost(var.subnet_cidrs["inet"],20)
    end   = cidrhost(var.subnet_cidrs["inet"],200)
  }
}

resource "openstack_networking_router_interface_v2" "router_interface_inet" {
  router_id  = openstack_networking_router_v2.router.id
  subnet_id  = "${openstack_networking_subnet_v2.internet_subnet.id}"
  depends_on = [terraform_data.router_gateway]
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

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: inetdns\npreserve_hostname: false\n"
  }
}

data "openstack_images_image_v2" "inet-dns-image" {
  name        = var.inetdns_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "inet-dns" {
  name        = "${var.deployment_id}-inetdns"
  flavor_name = var.inetdns_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.inet-dns-image.id
  user_data    = local.ext_dns_userdata_file == null ? null : data.template_cloudinit_config.cloudinitdns[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    uuid        = openstack_networking_network_v2.internet.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"],514)
  }

  depends_on = [
     openstack_networking_router_interface_v2.router_interface_inet,
     openstack_networking_subnet_v2.internet_subnet,
  ]

}

###################################################################
#
# CREATE NETWORK "LAN"
#
resource "openstack_networking_network_v2" "lan" {
  name           = "${var.deployment_id}-lan"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "lan_subnet" {
  name       = "${var.deployment_id}-lan_subnet"
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
  name           = "${var.deployment_id}-dmz"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "dmz_subnet" {
  name       = "${var.deployment_id}-dmz_subnet"
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
  name           = "${var.deployment_id}-admin"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "admin_subnet" {
  name       = "${var.deployment_id}-admin_subnet"
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
  name           = "${var.deployment_id}-user"
  port_security_enabled = "false"
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "user_subnet" {
  name       = "${var.deployment_id}-user_subnet"
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

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: inetfw\npreserve_hostname: false\n"
  }
}

data "openstack_images_image_v2" "inet-fw-image" {
  name        = var.inetfw_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "inet-fw" {
  name        = "${var.deployment_id}-inetfw"
  flavor_name = var.inetfw_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.inet-fw-image.id
  user_data    = local.fw_userdata_file == null ? null : data.template_cloudinit_config.cloudinitinetfw[0].rendered

    metadata = {
    contact = var.contact
  }

  network {
    uuid        = openstack_networking_network_v2.internet.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"],254)
  }

  network {
    uuid        = openstack_networking_network_v2.lan.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["lan"],254)
  }

  network {
    uuid        = openstack_networking_network_v2.dmz.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["dmz"],254)
  }

  network {
    uuid        = openstack_networking_network_v2.admin.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["admin"],254)
  }

  network {
    uuid        = openstack_networking_network_v2.user.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["user"],254)
  }

  depends_on = [
     openstack_compute_instance_v2.inet-dns,
     openstack_networking_subnet_v2.dmz_subnet,
     openstack_networking_subnet_v2.internet_subnet,
     openstack_networking_subnet_v2.lan_subnet,
     openstack_networking_subnet_v2.admin_subnet,
     openstack_networking_subnet_v2.user_subnet
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

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: mgmt\npreserve_hostname: false\n"
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
  name        = "${var.deployment_id}-mgmt"
  flavor_name = var.mgmt_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.mgmt-image.id
  user_data    = local.mgmt_userdata_file == null ? null : data.template_cloudinit_config.cloudinitmgmt[0].rendered

    metadata = {
    contact = var.contact
  }

  network {
    uuid        = openstack_networking_network_v2.internet.id
    fixed_ip_v4 = local.mgmt_ips.internet
  }

  network {
    uuid        = openstack_networking_network_v2.lan.id
    fixed_ip_v4 = local.mgmt_ips.lan
  }

  network {
    uuid        = openstack_networking_network_v2.dmz.id
    fixed_ip_v4 = local.mgmt_ips.dmz
  }

  network {
    uuid        = openstack_networking_network_v2.admin.id
    fixed_ip_v4 = local.mgmt_ips.admin
  }

  network {
    uuid        = openstack_networking_network_v2.user.id
    fixed_ip_v4 = local.mgmt_ips.user
  }

  depends_on = [
     openstack_networking_router_interface_v2.router_interface_inet,
     openstack_networking_subnet_v2.dmz_subnet,
     openstack_networking_subnet_v2.internet_subnet,
     openstack_networking_subnet_v2.lan_subnet,
     openstack_networking_subnet_v2.admin_subnet,
     openstack_networking_subnet_v2.user_subnet
  ]
}

data "openstack_networking_port_v2" "mgmt" {
  network_id = openstack_networking_network_v2.internet.id
  device_id  = openstack_compute_instance_v2.mgmt.id
  fixed_ip   = local.mgmt_ips.internet
    depends_on = [
      openstack_compute_instance_v2.mgmt  
  ]
}


resource "openstack_networking_floatingip_v2" "mgmt" {
  pool        = var.floating_pool
  description = "${var.deployment_id}-mgmt"
  depends_on  = [terraform_data.router_gateway]
}

resource "openstack_networking_floatingip_associate_v2" "mgmt" {
  floating_ip = openstack_networking_floatingip_v2.mgmt.address
  port_id     = data.openstack_networking_port_v2.mgmt.id

  depends_on = [
     data.openstack_networking_port_v2.mgmt,
     openstack_networking_router_interface_v2.router_interface_inet
  ]
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

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: corpdns\npreserve_hostname: false\n"
  }
}

data "openstack_images_image_v2" "dnsserver-image" {
  name        = var.corpdns_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "dnsserver" {
  name        = "${var.deployment_id}-corpdns"
  flavor_name = var.corpdns_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.dnsserver-image.id
  user_data    = local.ext_dnsserver_userdata_file == null ? null : data.template_cloudinit_config.cloudinitdnsserver[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    uuid        = openstack_networking_network_v2.internet.id
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"], 233)
    
  }

  depends_on = [
    openstack_networking_router_interface_v2.router_interface_inet,
    openstack_networking_subnet_v2.internet_subnet,
  ]
}
