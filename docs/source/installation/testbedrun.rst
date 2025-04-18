.. _testbedrun:

=========================
Helper Tools - Testbedrun
=========================

Using the `testbedrun` Script
-----

The ``testbedrun`` script provides a convenient way to selectively redeploy specific OpenStack instances within your testbed environment without needing to perform a full ``terragrunt destroy`` and ``apply`` on the entire infrastructure. 
This is useful for resetting individual virtual machines to their base state.
The script is executed using Python 3 and requires a single argument specifying the path to a YAML mapping file:

.. code-block:: bash

   python3 testbedrun <path_to_yaml_file>

Arguments
---------

*   ``<path_to_yaml_file>`` (Required):
    The path to a YAML file that maps the logical instance names (used for selection) to their corresponding Terragrunt subdirectory names where they are defined.

Input YAML File Format
----------------------

The YAML file provided as an argument must contain a simple key-value mapping. Each key represents the logical name of an OpenStack instance as you want it displayed in the selection prompt. The corresponding value must be the name of the Terragrunt subdirectory (within the main ``terragrunt/`` directory of the project) where that specific instance is defined in the ``terragrunt.hcl`` configuration.

**Example YAML File (`instance_names.yml`):**

.. code-block:: yaml
   :caption: Example instance_names.yml

   reposerver: repository
   linuxshare: repository
   videoserver: videoserver
   adminpc: videoserver
   webcam: videoserver
   corpdns: videoserver
   attacker: attacker
   inet-dns: bootstrap
   inet-fw: bootstrap
   mgmt: bootstrap

Workflow
--------

When executed, the ``testbedrun`` script performs the following actions:

1.  **Loads VM Map:** Parses the provided YAML file to understand the instance-to-directory mapping.
2.  **Finds Root Path:** Automatically locates the project's root directory by searching upwards for the presence of the ``terragrunt`` directory.
3.  **Prompts for Selection:** Presents an interactive checklist to the user, listing all instance names found as keys in the YAML file. The user selects which instance(s) they wish to redeploy.
4.  **Executes Redeployment:** For *each* instance selected by the user:
    a.  Changes directory to the corresponding Terragrunt subdirectory (e.g., ``<rootpath>/terragrunt/repository/`` for ``reposerver`` based on the example YAML).
    b.  Runs ``terragrunt destroy --target openstack_compute_instance_v2.<instance_name>`` to specifically destroy only that OpenStack compute instance resource. (Example: ``terragrunt destroy --target openstack_compute_instance_v2.reposerver``).
    c.  If the destroy command succeeds, it immediately runs ``terragrunt apply`` within the *same subdirectory* to recreate the instance based on the current configuration.

Example Command
---------------

Assuming your mapping file is located at ``config/instance_map.yml`` relative to where you run the command:

.. code-block:: bash

   python3 path/to/testbedrun config/instance_map.yml

The script will then present the checklist based on the contents of ``config/instance_map.yml`` for you to select the instances to redeploy.