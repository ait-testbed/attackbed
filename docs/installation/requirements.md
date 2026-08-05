# Requirements

To setup the AttackBed it is necessary to have the following requirements prepared:

1.  Access to a working [OpenStack](https://www.openstack.org/) is required

2.  Install [OpenTofu](https://opentofu.org/)

3.  Install [Terragrunt](https://terragrunt.gruntwork.io/)

4.  Install [Ansible](https://www.ansible.com/)

    !!! note
        Optionally, you can install Ansible in a Python virtual environment (venv) after it has been activated in a later step.

5.  Install [Packer](https://developer.hashicorp.com/packer/install) and its following plugins:
    
      - [Ansible plugin](https://developer.hashicorp.com/packer/integrations/hashicorp/ansible)
      - [OpenStack plugin](https://developer.hashicorp.com/packer/integrations/hashicorp/openstack)

6.  Upload a SSH-key to your OpenStack Project and name it *testbed-key*
