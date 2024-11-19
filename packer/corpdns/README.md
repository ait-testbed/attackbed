# Configuration

This image installs/configures a maradns-server for a corporate external dns-server.

# Install requirements

```
ansible-galaxy install -r playbook/requirements.yml
```

# Build

```
packer build -var-file=default.json .
```
