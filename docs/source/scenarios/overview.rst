========
Overview
========

All attacks are executed by Ansible. The directory **ansible/run** stores all playbooks to
perform the attacks. Every playbook prepares the servers and virtual machines, uploads the
attack-playbooks and executes the attacks.

Prepare Ansible
---------------

Most of the virtual machines are not directly reachable from the ansible-provisioning-server.
Therefore it is necessary to use a jumphost. The bootstrap(see: :ref:`deploy_bootstrap`) 
deployes a virtual machine "mgmt" which is located in each network and should be used as SSH 
jumphost. Change the ip address of the host mgmt in the ansible/hosts file:

::

  [RegionOne:vars]
  ansible_ssh_common_args='-o ProxyCommand="ssh -A -p 22 -W %h:%p -q aecid@<MGMTIP>"'
