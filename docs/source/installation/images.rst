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

There are pre-built server images at https://aecidimages.ait.ac.at. The `testbedimage-tool <https://github.com/ait-aecid/testbedimage-tool.git>`_
can import all prebuild images to the openstack-project:

::

  $ pip3 install testbedimage
  $ export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  $ . myproject-openrc.sh
  $ testbedimage import_images

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
