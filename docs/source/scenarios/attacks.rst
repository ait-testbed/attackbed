===========
Run Attacks
===========

To run attacks change into **ansible/run/scenario1** and run an attack using ansible playbook:

::

    cd ansible/run/scenario1
    ansible-playbook --tags playbooks,scenario_1_c_c main.yml

This prepares the attacks using the tag **playbooks** and executes the variation **scenario_1_c_c**

.. warning::

   Some scenarios do have multiple variations. Do not run the playbook without any tags and always run one screnario at once. There is no cleanup after an attack!
