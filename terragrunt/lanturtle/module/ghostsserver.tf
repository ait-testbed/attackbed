locals {
    ext_ghostsserver_userdata_file = var.ghostsserver_userdata == null ? "${path.module}/scripts/default.yml" : var.ghostsserver_userdata
}

####################################################################
#
# CREATE INSTANCE for "ghostsserver"
#
data "template_file" "userdata_ghostsserver" {
  template = "${file("${local.ext_ghostsserver_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitghostsserver" {
  count         = local.ext_ghostsserver_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_ghostsserver.rendered
  }
}

data "openstack_images_image_v2" "ghostsserver-image" {
  name        = var.ghostsserver_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "ghostsserver" {
  name        = "ghostsserver"
  flavor_name = var.ghostsserver_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.ghostsserver-image.id
  user_data    = local.ext_ghostsserver_userdata_file == null ? null : data.template_cloudinit_config.cloudinitghostsserver[0].rendered

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.lan_cidr,122)
  }

}
