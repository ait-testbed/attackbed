# Scenario 5 - LAN Turtle

Hosts file (remember to put in the correct region and management host ip!):
```
[DE1:vars]
ansible_ssh_common_args='-o ProxyCommand="ssh -A -p 22 -W %h:%p -q aecid@51.75.95.133"'
```


Start the attack scenario:
```
cd ansible
ansible-playbook run/scenario5/main.yml
```
Use the `-vvvv` for debugging.

After the attack has finished, start gather:
```
ansible-playbook gather.yml
```

### Debugging

Find attackmate process on the attacker machine:
```
pgrep -fl attackmate
```

Find ghostagent process on the adminpc:
```
pgrep -fl ghosts.client.linux
```

Kill processes with:
```
sudo kill <process_id>
```
