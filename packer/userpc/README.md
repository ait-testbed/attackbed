# Configuration

This packer-config generates userpc image

# Prebuild

Create a default.json:

```
{
    "base_image" : "ubuntu2204",
    "image_name" : "userpc-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208"
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
