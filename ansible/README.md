# Dependency:

```
pip3 install openstacksdk==0.36
```

# configure

set mgmt-ip in hosts

set ansible-remote-user using an environment var:

```
export ANSIBLE_REMOTE_USER=ait
```

create a `hosts` file in the `ansible` folder following this template (or see the `hosts.example` file):
```
[<RegionName>:vars]
ansible_ssh_common_args='-o ProxyCommand="ssh -A -p 22 -W %h:%p -q <ProxyUser>@<ProxyHostIP>"'
```
