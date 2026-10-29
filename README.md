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

## Installation in Home Assistant

Add this GitHub repository in HACS as a custom **Integration** repository,
install it, restart Home Assistant, and add **DMX Gateway** in
**Settings → Devices & services**.

The setup form asks for:

- **Host** — the gateway IP address (for example, `192.168.2.109`), preferably
  reserved in the router DHCP settings;
- **Port** — `8080` for the gateway HTTP Product API;
- **API token** — the bearer token provisioned in that gateway's firmware.

The token is not a GitHub, HACS, Home Assistant or Wi-Fi password. It is
device-specific and is deliberately not included in this repository. A user
who builds the firmware must create a random token, put it in the local
`firmware/secrets.yaml` as `stage72_api_token`, and flash that firmware. The
same token is then entered in the HA setup form. Never publish the token or a
firmware binary that contains it.

For an already provisioned device, the installer must obtain the token from
the device owner or the private commissioning record. HACS installation alone
cannot recover a lost token; the device must be re-provisioned and reflashed.

After setup, open the device's **Configure** action and choose **Fade settings**
to enable/disable default fades and set the rate in percentage points per
second. An explicit `transition` value in a Home Assistant light action
overrides this default.

The current public package is therefore self-service for a provisioned
gateway, but it is not a zero-configuration firmware provisioning system. A
future product release can add a one-time pairing flow or QR-based commissioning
to remove the manual token hand-off.

## Development

The package source is under `custom_components/dmx_gateway`. This repository
contains no Wi-Fi credentials, bearer tokens, SSH keys or firmware binaries.
