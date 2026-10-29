# DMX Gateway for Home Assistant

Local Home Assistant integration for the ESP32 DMX Gateway Product API.

## Features

- Discovers a gateway by host, port and development credential.
- Uses the stable gateway ID, rather than its DHCP address, as the HA identity.
- Provides dimmable light entities for every configured DMX channel and a
  blackout switch.
- Exposes gateway diagnostic sensors.
- Includes a standard Options Flow: add, edit and delete DMX devices; set the
  first DMX address, channel count and channel names.
- Includes per-gateway default fade settings: enable/disable automatic fades
  and choose the rate in percentage points per second. An explicit HA
  `transition` value overrides this default.
- Preserves device and channel IDs during edits, so existing entity IDs stay
  stable.

## HACS installation

Add this GitHub repository in HACS as a custom **Integration** repository,
install it, restart Home Assistant, and add **DMX Gateway** in
**Settings → Devices & services**.

The integration needs the gateway HTTP Product API (normally port `8080`) and
its bearer development credential.

## Development

The package source is under `custom_components/dmx_gateway`. This repository
contains no Wi-Fi credentials, bearer tokens, SSH keys or firmware binaries.
