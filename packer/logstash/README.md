# Configuration

This image installs/configures logstash and connects it with opensearch.

> **Note:** Logstash need the `ca.pem` certificate file from opensearch to make the connection.
> Therefore, it is **important to build the opensearch image first!** The file is then located in the 
> `packer/opensearch` directory, which logstash automatically takes.

# Prebuild

Create a default.json:

```
{
    "base_image" : "ubuntu-2204",
    "image_name" : "atb-logstash-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208",
    "flavor": "m1.small"
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
