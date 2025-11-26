locals {
    ext_docker_userdata_file = var.docker_userdata == null ? "${path.module}/scripts/default.yml" : var.docker_userdata
}

####################################################################
#
# CREATE INSTANCE for "VIDEOSERVER"
#
data "template_file" "userdata_docker" {
  template = "${file("${local.ext_docker_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitdocker" {
  count         = local.ext_docker_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_docker.rendered
  }
}

data "openstack_images_image_v2" "docker-image" {
  name        = var.docker_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "docker" {
  name        = "docker"
  flavor_name = var.docker_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.docker-image.id
  user_data    = local.ext_docker_userdata_file == null ? null : data.template_cloudinit_config.cloudinitdocker[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    name = "dmz"
    fixed_ip_v4 = cidrhost(var.dmz_cidr,125)
  }

}
