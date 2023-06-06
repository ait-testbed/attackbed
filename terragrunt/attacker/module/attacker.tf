

locals {
    ext_attacker_userdata_file = var.attacker_userdata == null ? "${path.module}/scripts/default.yml" : var.attacker_userdata
}

####################################################################
#
# CREATE INSTANCE for "Attacker"
#
data "template_file" "userdata_attacker" {
  template = "${file("${local.ext_attacker_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitattacker" {
  count         = local.ext_attacker_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_attacker.rendered
  }
}

data "openstack_images_image_v2" "attacker-image" {
  name        = var.attacker_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "attacker" {
  name        = "attacker"
  flavor_name = var.attacker_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.attacker-image.id
  user_data    = local.ext_attacker_userdata_file == null ? null : data.template_cloudinit_config.cloudinitattacker[0].rendered

  network {
    name = "internet"
  }

}
