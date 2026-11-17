locals {
    ext_linuxshare_userdata_file = var.linuxshare_userdata == null ? "${path.module}/scripts/default.yml" : var.linuxshare_userdata
}

####################################################################
#
# CREATE INSTANCE for "LINUXSHARE"
#
data "template_file" "userdata_linuxshare" {
  template = "${file("${local.ext_linuxshare_userdata_file}")}"
  vars = {
      dns_server_address = cidrhost(var.lan_cidr, var.linuxshare_dns)
  }
}

data "template_cloudinit_config" "cloudinitlinuxshare" {
  count         = local.ext_linuxshare_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_linuxshare.rendered
  }

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: linuxshare\npreserve_hostname: false\n"
  }
}

data "openstack_images_image_v2" "linuxshare-image" {
  name        = var.linuxshare_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "linuxshare" {
  name        = "${var.deployment_id}-linuxshare"
  flavor_name = var.linuxshare_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.linuxshare-image.id
  user_data    = local.ext_linuxshare_userdata_file == null ? null : data.template_cloudinit_config.cloudinitlinuxshare[0].rendered

  metadata = {
    contact = var.contact
  }
  
  network {
    uuid        = var.network_ids["lan"]
    fixed_ip_v4 = cidrhost(var.lan_cidr,23)
  }

}
