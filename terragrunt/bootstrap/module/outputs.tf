output "network_ids" {
  description = "Network UUIDs belonging to this deployment"
  value = {
    internet = openstack_networking_network_v2.internet.id
    lan      = openstack_networking_network_v2.lan.id
    dmz      = openstack_networking_network_v2.dmz.id
    admin    = openstack_networking_network_v2.admin.id
    user     = openstack_networking_network_v2.user.id
  }
}

output "management_floating_ip" {
  description = "Floating IP of this deployment's management host"
  value       = openstack_networking_floatingip_v2.mgmt.address
}
