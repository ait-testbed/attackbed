# Configuration

This image installs/configures shorewall, dnsmasq and suricata. 

shorewall needs some informations:

1. dmz-interface
2. lan-interface
3. dmz-ip-range
4. lan-ip-range

for dns we need a functional dns-server. This images has hard-coded settings for the dmz-interface, lan-interface, dmz-ip-range and lan-ip-range. In order
to change these settings I would recommend to do this using cloud-init in terraform. Simply replace the file /etc/shorewall/params with your own.

Please note that shorewall is stopped! You need to enable and restart it manualle. This can also be done with cloud-init

# Install requirements

```
ansible-galaxy install -r playbook/requirements.yml
```

# Build

```
packer build -var-file=default.json .
```
