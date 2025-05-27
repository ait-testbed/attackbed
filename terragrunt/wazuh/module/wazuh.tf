locals {
    ext_wazuh_userdata_file = var.wazuh_userdata == null ? "${path.module}/scripts/default.yml" : var.wazuh_userdata
}

####################################################################
#
# CREATE INSTANCE for "VIDEOSERVER"
#
data "template_file" "userdata_wazuh" {
  template = "${file("${local.ext_wazuh_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitwazuh" {
  count         = local.ext_wazuh_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_wazuh.rendered
  }
}

data "openstack_images_image_v2" "wazuh-image" {
  name        = var.wazuh_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "wazuh" {
  name        = "wazuh"
  flavor_name = var.wazuh_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.wazuh-image.id
  user_data    = local.ext_wazuh_userdata_file == null ? null : data.template_cloudinit_config.cloudinitwazuh[0].rendered

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.lan_cidr,130)
  }

}
