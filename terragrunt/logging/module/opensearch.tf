

locals {
    ext_opensearch_userdata_file = var.opensearch_userdata == null ? "${path.module}/scripts/default.yml" : var.opensearch_userdata
}

####################################################################
#
# CREATE INSTANCE for "opensearch"
#
data "template_file" "userdata_opensearch" {
  template = "${file("${local.ext_opensearch_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitopensearch" {
  count         = local.ext_opensearch_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_opensearch.rendered
  }
}

data "openstack_images_image_v2" "opensearch-image" {
  name        = var.opensearch_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "opensearch" {
  name        = "opensearch"
  flavor_name = var.opensearch_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.opensearch-image.id
  user_data    = local.ext_opensearch_userdata_file == null ? null : data.template_cloudinit_config.cloudinitopensearch[0].rendered

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.lan_cidr,11)
  }

}
