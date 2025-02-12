===========
Gather Logs
===========

Once the attacks have finished, we can specify in the ``gather.yml`` playbook all the logs we
want to collect from the machines.

Install requirements:

::

  cd ansible/
  ansible-galaxy install -r requirements.yml

Start the gathering playbook:

::

    ansible-playbook run/<your_scenario>/gather.yml

The collected logs are saved in the ``ansible/gather/`` folder.
