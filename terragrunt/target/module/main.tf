
terraform {
  backend "http" {}
}

locals {
    ext_target_userdata_file = var.target_userdata == null ? "${path.module}/scripts/default.yml" : var.target_userdata
    ext_target2_userdata_file = var.target_userdata == null ? "${path.module}/scripts/default.yml" : var.target_userdata
}

####################################################################
#
# CREATE INSTANCE for "Target"
#
data "template_file" "userdata_target" {
  template = "${file("${local.ext_target_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinittarget" {
  count         = local.ext_target_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_target.rendered
  }
}

data "openstack_images_image_v2" "target-image" {
  name        = var.target_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "target" {
  name        = "target"
  flavor_name = var.target_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.target-image.id
  user_data    = local.ext_target_userdata_file == null ? null : data.template_cloudinit_config.cloudinittarget[0].rendered

  network {
    name = "internet"
    fixed_ip_v4 = "192.42.1.175"
  }

}


####################################################################
#
# CREATE INSTANCE for "Target2"
#


data "openstack_images_image_v2" "target2-image" {
  name        = var.target2_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "target2" {
  name        = "target"
  flavor_name = var.target_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.target2-image.id
  user_data    = local.ext_target2_userdata_file == null ? null : data.template_cloudinit_config.cloudinittarget[0].rendered

  network {
    name = "internet"
    fixed_ip_v4 = "192.42.1.176"
  }

}