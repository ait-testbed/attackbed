# Scenario 6 - Client

Execute the following commands from the `/ansible` folder.

Install requirements:
```
ansible-galaxy install -r requirements.yml
```

Hosts file (remember to put in the correct region and management host ip!):
```
[DE1:vars]
ansible_ssh_common_args='-o ProxyCommand="ssh -A -p 22 -W %h:%p -q aecid@<mgmt-ip>>"'

[inetfw-int]
192.168.100.254 ansible_user=aecid ansible_ssh_common_args='-o ProxyCommand="ssh -A -p 22 -W %h:%p -q aecid@51.75.95.133"'
```

Start the attack scenario:
```
cd ansible
ansible-playbook run/scenario5/main.yml
```
Use the `-vvvv` for debugging.

Then start gathering the logs:
```
ansible-playbook run/scenario5/gather.yml