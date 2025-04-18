.. _development_overview:

========
Overview
========

This document provides a high-level overview for developers interested in understanding the project structure and contribution process.

Purpose
-------
This project facilitates the creation, execution, and log collection of automated attack simulations within a defined virtual environment. 


Project Structure
-----------------
The codebase is generally organized as follows:

*   ``ansible/``: Contains Ansible playbooks defining the scenario setup and the attack playbooks.
*   ``docs/``: Contains the Sphinx documentation source files.
*   ``scripts/``: Contains helper scripts 
*   ``packer/``: Contains Packer templates (e.g., ``.pkr.hcl`` or ``.json`` files) and associated scripts used to build the base virtual machine images for the simulation environment components (e.g., attacker, victim, server machines).
*   ``terragrunt/``: Contains Terragrunt configuration files (``terragrunt.hcl``) used to orchestrate the deployment and management of the underlying infrastructure (virtual machines, networks, etc.).

Getting Started with Development
--------------------------------
1.  **Prerequisites:** Ensure you have the necessary base software installed, such as OpenStack, OpenTofu, Ansible, Terragrunt (see :ref:`Requirements <requirements>`)
2.  **Setup:** Clone the repository and follow the instructions in the Installation section to build the base environment

Contributing
------------
Contributions to enhance scenarios, improve tooling, or fix bugs are welcome, following standard Git practices:

1.  Fork the repository.
2.  Create a descriptive feature branch (e.g., ``feat/add-new-scenario`` or ``fix/resolve-ssh-issue``).
3.  Implement your changes, adhering to existing code style.
4.  Test your changes thoroughly.
5.  Update documentation (in ``docs/``) if necessary.
6.  Submit a Pull Request against the main branch for review.
