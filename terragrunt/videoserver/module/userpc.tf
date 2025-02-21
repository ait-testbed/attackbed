locals {
    ext_userpc_userdata_file = var.userpc_userdata == null ? "${path.module}/scripts/default.yml" : var.userpc_userdata
}

####################################################################
#
# CREATE INSTANCE for "USERPC"
#
data "template_file" "userdata_userpc" {
  template = "${file("${local.ext_userpc_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinituserpc" {
  count         = local.ext_userpc_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_userpc.rendered
  }
}

data "openstack_images_image_v2" "userpc-image" {
  name        = var.userpc_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "userpc" {
  name        = "userpc1"
  flavor_name = var.userpc_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.userpc-image.id
  user_data    = local.ext_userpc_userdata_file == null ? null : data.template_cloudinit_config.cloudinituserpc[0].rendered

  network {
    name = "user"
    fixed_ip_v4 = cidrhost(var.user_cidr,21)
  }

}
