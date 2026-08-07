locals {
  ext_corpdns_userdata_file = var.corpdns_userdata == null ? "${path.module}/scripts/default.yml" : var.corpdns_userdata
}

####################################################################
#
# CREATE INSTANCE for "DNS-Server"
#
data "template_file" "userdata_corpdns" {
  template = file("${local.ext_corpdns_userdata_file}")
}

data "template_cloudinit_config" "cloudinitcorpdns" {
  count         = local.ext_corpdns_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_corpdns.rendered
  }
}

data "openstack_images_image_v2" "corpdns-image" {
  name        = var.corpdns_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "corpdns" {
  name        = "corpdns"
  flavor_name = var.corpdns_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.corpdns-image.id
  user_data   = local.ext_corpdns_userdata_file == null ? null : data.template_cloudinit_config.cloudinitcorpdns[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    name        = "internet"
    fixed_ip_v4 = cidrhost(var.subnet_cidrs["inet"], 233)
  }
}
