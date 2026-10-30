# DMX Gateway for Home Assistant

Local Home Assistant integration for the ESP32 DMX Gateway Product API.

## Features

- Discovers a gateway by host, port and development credential.
- Uses the stable gateway ID, rather than its DHCP address, as the HA identity.
- Provides dimmable light entities for every configured DMX channel and a
  blackout switch.
- Exposes gateway diagnostic sensors on the gateway device page: uptime,
  free memory, DMX frame rate, transmission errors, runtime topology,
  transition count, and NVS persistence health.
- Includes a standard Options Flow: add, edit and delete DMX devices; set the
  first DMX address, channel count and channel names.
- Includes per-channel default fade settings: enable/disable automatic fades
  and choose the time for a full 0–100% transition (1–10 seconds). An explicit HA
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

After setup, open the **SkyDance S1-DR** device page. Each channel exposes
three controls: **Включать плавно**, **Действие после подачи электропитания**
(`Включен`, `Выключен`, `Состояние при отключении`) and the full-range fade
time from 0 to 100 percent. An explicit `transition` value in a Home Assistant
light action overrides the channel default.

The integration talks to the gateway over its authenticated HTTP Product API
on port 8080. The separate ESPHome native API on port 6053 remains available
for diagnostics and fallback, but it is not used for DMX commands by this
integration. Diagnostic sensors are exposed from the HTTP `/v1/diagnostics`
endpoint in the same style as ESPHome diagnostics.

For another user: install HACS, add `knyazhev/ha-dmx-gateway` as a custom
Integration repository, install **DMX Gateway**, restart Home Assistant, then
choose **Settings → Devices & services → Add integration → DMX Gateway**.
Enter the gateway host, port 8080 and the device-specific bearer token. The
token is provisioned during firmware commissioning and is never part of GitHub
or HACS.

The current public package is therefore self-service for a provisioned
gateway, but it is not a zero-configuration firmware provisioning system. A
future product release can add a one-time pairing flow or QR-based commissioning
to remove the manual token hand-off.

## Development

The package source is under `custom_components/dmx_gateway`. This repository
contains no Wi-Fi credentials, bearer tokens, SSH keys or firmware binaries.
