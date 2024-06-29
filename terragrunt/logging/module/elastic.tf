

locals {
    ext_elastic_userdata_file = var.elastic_userdata == null ? "${path.module}/scripts/default.yml" : var.elastic_userdata
}

####################################################################
#
# CREATE INSTANCE for "Elastic"
#
data "template_file" "userdata_elastic" {
  template = "${file("${local.ext_elastic_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitelastic" {
  count         = local.ext_elastic_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_elastic.rendered
  }
}

data "openstack_images_image_v2" "elastic-image" {
  name        = var.elastic_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "elastic" {
  name        = "opensearch"
  flavor_name = var.elastic_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.elastic-image.id
  user_data    = local.ext_elastic_userdata_file == null ? null : data.template_cloudinit_config.cloudinitelastic[0].rendered

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.lan_cidr,11)
  }

}
