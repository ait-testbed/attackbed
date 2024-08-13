.. _setup_virtualenv:

Setting up a python virtual environment
=============================================================

For building certain images, it is necessary to have some python libraries installed locally.


Create a virtual environment:

::

    python3 -m venv venv

Activate virtual environment:

::

    source venv/bin/activate

Install dependencies:

::

    pip install -r requirements.txt


(Optional) Installing Ansible in the virtual environment
--------------------------------------------------------

If Ansible has not been installed yet, you can add it to your virtual environment:

::

   pip install ansible

Verify installation:

::

   ansible --version
