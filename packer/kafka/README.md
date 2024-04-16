# Configuration

This image installs/configures a kafka broker


# Prebuild

Create a default.json:

```
{
    "base_image" : "ubuntu-2204",
    "image_name" : "kafka-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208"
}
```

# Build

```
packer build -var-file=default.json .
```
