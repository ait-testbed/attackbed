.. _deploy_images:

====================
Deploy server images
====================

Prepared server images can be downloaded or created manually with packer. 


Download and install base images
================================

TODO: write documentation about downloading ubuntu2204 and debian-11-amd64-20210814-734


Download and install server images
==================================

TODO: write documentation about "how to download serverimages"

Build server images manually
============================

In the directory *packer* there is a separate directory for each server image. It is neccessary to manually create the file *"default.json"* in each directory.
You need to copy **default.json.example** to **default.json** and change at least the values for **network** and **floating_ip_pool**. Then you can build an image by running packer:

::

    cd packer/adminpc/playbook
    ansible-galaxy install -r requirements.yml
    packer build -var-file=default.json .

.. note::

   You need to repeat this for every image!
