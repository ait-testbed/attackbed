

locals {
    ext_kafka_userdata_file = var.kafka_userdata == null ? "${path.module}/scripts/default.yml" : var.kafka_userdata
}

####################################################################
#
# CREATE INSTANCE for "Kafka"
#
data "template_file" "userdata_kafka" {
  template = "${file("${local.ext_kafka_userdata_file}")}"
}

data "template_cloudinit_config" "cloudinitkafka" {
  count         = local.ext_kafka_userdata_file == null ? 0 : 1
  gzip          = false
  base64_encode = false

  part {
    filename     = "init.cfg"
    content_type = "text/cloud-config"
    content      = data.template_file.userdata_kafka.rendered
  }
}

data "openstack_images_image_v2" "kafka-image" {
  name        = var.kafka_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "kafka" {
  name        = "kafka"
  flavor_name = var.kafka_flavor
  key_pair    = var.sshkey
  image_id    = data.openstack_images_image_v2.kafka-image.id
  user_data    = local.ext_kafka_userdata_file == null ? null : data.template_cloudinit_config.cloudinitkafka[0].rendered

  metadata = {
    contact = var.contact
  }

  network {
    name = "lan"
    fixed_ip_v4 = cidrhost(var.lan_cidr,10)
  }

}
