# v0.1.4 — publication candidate

Unpublished candidate; no release tag is created by this preparation.

Native ESP-IDF gateway support with owner-verified HTTPS certificate pin and separate scoped HA token. Channels/groups belong to one gateway; stable IDs and entity registry records are preserved during publication/topology changes. Gateway Web UI owns channel, fade and startup configuration. Obsolete child devices and gateway diagnostic sensors are removed from HA.

Authoritative fade targets prevent off/on/off state replay. Bounded 500 ms local state refresh skips busy ticks and sends no cached commands on read failure. HA works independently of optional Cloud/Alice.

Verified on official HA Core 2026.10.4 and a physical native gateway. Three ten-second cloud fade tests measured HA off at 1.406–1.844 seconds including Cloud request, with no rebound. Gateway firmware 0.1.0-net.20261107.3 completed a separate one-hour run with no MQTT reconnect, HTTP/TLS timeout, reboot or software DMX error.

Limitations: polling is not instantaneous push; automatic Alice UI delivery was not measured by these API tests; older HA versions permitted by manifest were not all tested. Firmware power-loss rollback and electrical DMX timing need separate hardware acceptance.
