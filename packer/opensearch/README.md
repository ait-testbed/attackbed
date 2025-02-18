# Configuration

This image installs/configures opensearch as a single-node-instance.

# Prebuild

> **Note:** Make sure to take a big enough image flavor, 
> as this role has the following minimum hardware requirements:
> - Memory: 4GB RAM or more 
> - CPU: 2 cores or more

Create a default.json:

```
{
    "base_image" : "ubuntu-2204",
    "image_name" : "atb-opensearch-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208",
    "flavor": "m1.medium"
}
```

# Install requirements

```
ansible-galaxy install -r playbook/requirements.yml
```

# Build

```
packer build -var-file=default.json .
```
