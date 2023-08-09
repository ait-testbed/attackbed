.. _deploy_bootstrap:

================
Deploy bootstrap
================

.. image:: ../../images/AECID-Testbed-Bootstrap.png

The bootstrap is a basic network infrastructure with all the network components that are required for all the scenarios. This bootstrap can be deployed with terragrunt.
It is necessary to change the configuration in terragrunt/bootstrap/terragrunt.hcl:

::

    inputs = {
      host_userdata = "firewallinit.yml"
      ext_router = "aecid-testbed-router"
      sshkey = "testbed-key"
      inetdns_image = "ubuntu-2204"
      inetfw_image = "atb-fw-inet-lan-dmz-image-2023-06-09T14-03-06Z"
      mgmt_image = "ubuntu-2204"
      floating_pool = "provider-aecid-208"
    }

If you built the server images manually you have to change the image-names. It is also necessary to set the **external router** and the **floating_pool**. After editing
the terragrunt.hcl the bootstrap can be deployed:

::

    cd terragrunt/bootstrap
    terragrunt apply

Most of the scenarios require a virtual machine for the **Attacker**. It is also necessary to modify the configuration for the attacker in *terragrunt/attacker/terragrunt.hcl* and
deploy the attacker:

::

    cd terragrunt/attacker
    terragrunt apply
