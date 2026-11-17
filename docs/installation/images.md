# Server images

Use [AttackBed CLI](../tools/attackbed.md) to build the Packer recipes for a scenario:

```sh
uv run attackbed build demo
```

Configure common image-build settings in `packer/defaults.json`. Each Packer recipe may override them with `packer/RECIPE/default.json`.

Prebuilt images are available from <https://aecidimages.ait.ac.at>; the [testbedimage-tool](https://github.com/ait-aecid/testbedimage-tool.git) can import them into OpenStack. Base images must already be available to Packer.

