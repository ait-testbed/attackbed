terraform {
  backend "http" {}
}

locals {
  client_userdata_file = var.client_userdata == null ? "${path.module}/scripts/default.yml" : var.client_userdata
}


data "openstack_networking_router_v2" "router" {
  name = var.ext_router
}


####################################################################
#
# CREATE INSTANCE for "CLIENT"
#
data "template_file" "userdata_client" {
  template = "${file("${local.client_userdata_file}")}"
  vars = {
      dns_server_address = "${openstack_compute_instance_v2.inet-dns.access_ip_v4}"
  }
}



data "template_cloudinit_config" "cloudinitclient" {
  count         = local.client_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_client.rendered
  }
}

data "openstack_images_image_v2" "client-image" {
  name        = var.client_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "client" {
  name        = "client"
  flavor_name = var.client_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.client-image.id
  user_data    = local.client_userdata_file == null ? null : data.template_cloudinit_config.cloudinitclient[0].rendered


  network {
    name = "dmz"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["dmz"],100)
  }

}


