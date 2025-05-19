# Configuration

This image installs/configures a docker-host

# Prebuild

Create a default.json:

```
{
    "base_image" : "Ubuntu 22.04",
    "image_name" : "docker-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "AECID-provider-network"
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
