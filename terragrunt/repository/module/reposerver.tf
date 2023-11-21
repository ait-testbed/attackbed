locals {
    ext_reposerver_userdata_file = var.reposerver_userdata == null ? "${path.module}/scripts/default.yml" : var.reposerver_userdata
}

####################################################################
#
# CREATE INSTANCE for "REPOSERVER"
#
data "template_file" "userdata_reposerver" {
  template = "${file("${local.ext_reposerver_userdata_file}")}"
  vars = {
      dns_server_address = cidrhost(var.dmz_cidr, var.reposerver_dns)
  }
}

data "template_cloudinit_config" "cloudinitreposerver" {
  count         = local.ext_reposerver_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_reposerver.rendered
  }
}

data "openstack_images_image_v2" "reposerver-image" {
  name        = var.reposerver_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "reposerver" {
  name        = "reposerver"
  flavor_name = var.reposerver_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.reposerver-image.id
  user_data    = local.ext_reposerver_userdata_file == null ? null : data.template_cloudinit_config.cloudinitreposerver[0].rendered

  network {
    name = "dmz"
    fixed_ip_v4 = cidrhost(var.dmz_cidr,122)
  }

}
