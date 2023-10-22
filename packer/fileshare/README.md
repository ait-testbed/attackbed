# Configuration

This image installs/configures a machine that is vulnerable in many ways.

Foothold:
* Vulnerable Zoneminder

Privilege Escalation:
* Logrotten
* PWNkit
* Writeable Systemd Service
* Insecure SSH keys
* Writeable Cronjob

**Please note that this image uses old debian snapshot archives**

# Prebuild

Create a default.json:

```
{
    "base_image" : "debian-11-amd64-20210814-734",
    "image_name" : "videoserver-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208"
}
```

# Build

```
packer build -var-file=default.json .
```
