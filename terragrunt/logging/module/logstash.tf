

locals {
    ext_logstash_userdata_file = var.logstash_userdata == null ? "${path.module}/scripts/default.yml" : var.logstash_userdata
}

####################################################################
#
# CREATE INSTANCE for "Logstash"
#
data "template_file" "userdata_logstash" {
  template = "${file("${local.ext_logstash_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitlogstash" {
  count         = local.ext_logstash_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_logstash.rendered
  }

  part {
    filename     = "hostname.cfg"
    content_type = "text/cloud-config"
    content      = "#cloud-config\nhostname: logstash\npreserve_hostname: false\n"
  }
}

data "openstack_images_image_v2" "logstash-image" {
  name        = var.logstash_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "logstash" {
  name        = "${var.deployment_id}-logstash"
  flavor_name = var.logstash_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.logstash-image.id
  user_data    = local.ext_logstash_userdata_file == null ? null : data.template_cloudinit_config.cloudinitlogstash[0].rendered

  metadata = {
    contact = var.contact
  }
  
  network {
    uuid        = var.network_ids["lan"]
    fixed_ip_v4 = cidrhost(var.lan_cidr,12)
  }

}
