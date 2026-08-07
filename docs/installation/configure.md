# Configure access to openstack

In order to install and work with the testbed you will need gitlab access to store the OpenTofu state and openstack access to deploy the testbed.
To do this, [download the openstack rc file](https://docs.openstack.org/mitaka/cli-reference/common/cli_set_environment_variables_using_openstack_rc.html#download-and-source-the-openstack-rc-file) and save it as an .env file in the top level of the testbed repository:

    cp <path-to-openstackrc> .env

We also need the Gitlab-user and Gitlab-token to store the OpenTofu state. We store them in the same .env file:

    echo "" >> .env
    echo "export CR_GITLAB_ACCESS_TOKEN=YOURTOKEN" >> .env
    echo "export GITLAB_USERNAME=YOURUSERNAME" >> .env
    echo "export GITLAB_STATE_REPOSITORY=YOURSTATEREPO" >> .env

Finally we also need a remote username for ansible:

    echo "export ANSIBLE_REMOTE_USER=aecid" >> .env

## Activate the configuration

In order to activate **ALL** configuration at once change into the ansible directory and source the activate file:

    cd ansible
    source activate

!!! note
    You need to activate the configuration everytime you want to deploy a testbed or run any scenario!

## Ansible hosts file

Create a `hosts` file in the `ansible` folder using the `hosts.example` file and change the public IP to the public IP of the deployed mgmt server accordingly at the following line:

    [all:vars]
    ansible_ssh_common_args='-o ProxyCommand="ssh -o IdentitiesOnly=yes -A -p 22 -W %h:%p -q aecid@203.0.113.10"'
