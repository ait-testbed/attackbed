# Configuration

This image installs/configures a simulated webcam

It is reachable via RTSP:

```
rtsp://cam:cam@IP:8554/mystream
```


# Prebuild

Create a default.json:

```
{
    "base_image" : "debian-11-amd64-20210814-734",
    "image_name" : "webcam-image",
    "security_group": "default",
    "network": "9c480f42-62f2-4f08-a961-38c28fa19346",
    "floating_ip_pool": "provider-aecid-208"
}
```

# Build

```
packer build -var-file=default.json .
```
