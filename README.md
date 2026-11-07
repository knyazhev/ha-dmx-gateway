# BELARD DMX Gateway for Home Assistant

Local integration for the existing native ESP-IDF 5.5.5 gateway. Home Assistant is an optional client; the gateway works independently.

## Configure / РќР°СЃС‚СЂРѕР№РєР°

1. Configure Wi-Fi and channels in the gateway Web UI. On its personalized WPA2 AP, open `https://192.168.4.1/` using the owner-verified certificate/CA. Sign in with the administrator password.
2. Under **Integrations в†’ Home Assistant**, create a scoped integration token. The administrator password is not the HA token.
3. In HA, add or reconfigure **DMX Gateway**. For native firmware use `https://<LAN-IP>#sha256=<owner-verified-certificate-fingerprint>`, port `443`, and the integration token. The fingerprint is public; never put the token in a URL.
4. Existing legacy HTTP addresses remain supported when explicitly configured with their old scheme and port.

РљР°РЅР°Р»С‹ РґРѕР±Р°РІР»СЏСЋС‚СЃСЏ РІ РІРµР±-РёРЅС‚РµСЂС„РµР№СЃРµ С€Р»СЋР·Р°: **РљР°РЅР°Р»С‹ в†’ РёРјСЏ, DMX-Р°РґСЂРµСЃ, С‚РёРї в†’ Р”РѕР±Р°РІРёС‚СЊ РєР°РЅР°Р»**. Р’ РјРµРЅСЋ РЅР°СЃС‚СЂРѕР№РєРё РёРЅС‚РµРіСЂР°С†РёРё РµСЃС‚СЊ РїРµСЂРµС…РѕРґ Рє СЌС‚РѕРјСѓ СЂР°Р·РґРµР»Сѓ. Р’ РєРѕР»РѕРЅРєРµ **Home Assistant** РЅР° С€Р»СЋР·Рµ РјРѕР¶РЅРѕ РІРєР»СЋС‡РёС‚СЊ РёР»Рё РѕС‚РєР»СЋС‡РёС‚СЊ РїСѓР±Р»РёРєР°С†РёСЋ РѕС‚РґРµР»СЊРЅРѕРіРѕ РєР°РЅР°Р»Р°, СЃРѕС…СЂР°РЅРёРІ DMX-РєР°РЅР°Р» Рё РµРіРѕ СѓСЂРѕРІРµРЅСЊ. РўРµРєСѓС‰РµРµ СЃРѕСЃС‚РѕСЏРЅРёРµ Рё СѓСЂРѕРІРЅРё РѕРїСЂР°С€РёРІР°СЋС‚СЃСЏ РєР°Р¶РґС‹Рµ 5 СЃРµРєСѓРЅРґ; С‚РѕРїРѕР»РѕРіРёСЏ Рё РґРёР°РіРЅРѕСЃС‚РёРєР° вЂ” РєР°Р¶РґС‹Рµ 60 СЃРµРєСѓРЅРґ.

HA Рё РђР»РёСЃР° СѓРїСЂР°РІР»СЏСЋС‚ РѕРґРЅРёРј С€Р»СЋР·РѕРј РЅРµР·Р°РІРёСЃРёРјС‹РјРё РїСѓС‚СЏРјРё. РљРѕРјР°РЅРґР° РђР»РёСЃС‹ РјРµРЅСЏРµС‚ С€Р»СЋР· С‡РµСЂРµР· Cloud/MQTT; HA РїРѕР»СѓС‡Р°РµС‚ СЃРѕСЃС‚РѕСЏРЅРёРµ СЃР»РµРґСѓСЋС‰РёРј read-only РѕРїСЂРѕСЃРѕРј. РљРѕРјР°РЅРґР° HA СѓРїСЂР°РІР»СЏРµС‚ С€Р»СЋР·РѕРј Р»РѕРєР°Р»СЊРЅРѕ, Р° С‚РѕС‚ РїСѓР±Р»РёРєСѓРµС‚ РЅРѕРІРѕРµ СЃРѕСЃС‚РѕСЏРЅРёРµ РІ Cloud/MQTT. РџСЂРё РѕС€РёР±РєРµ С‡С‚РµРЅРёСЏ HA РЅРµ РѕС‚РїСЂР°РІР»СЏРµС‚ СЃС‚Р°СЂС‹Р№ РєСЌС€ РѕР±СЂР°С‚РЅРѕ; РїРѕСЃР»Рµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ СЃРѕРµРґРёРЅРµРЅРёСЏ РёРЅС‚РµРіСЂР°С†РёСЏ РїРµСЂРµС‡РёС‚С‹РІР°РµС‚ СЃРѕСЃС‚РѕСЏРЅРёРµ СЃ СѓСЃС‚СЂРѕР№СЃС‚РІР°. РџРµСЂРµРґ РёР·РјРµРЅРµРЅРёРµРј СЏСЂРєРѕСЃС‚Рё RGB/RGBW-РіСЂСѓРїРїС‹ HA СЃРЅР°С‡Р°Р»Р° С‡РёС‚Р°РµС‚ Р°РєС‚СѓР°Р»СЊРЅС‹Р№ С†РІРµС‚, С‡С‚РѕР±С‹ РЅРµ РІРѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ СѓСЃС‚Р°СЂРµРІС€РёРµ С†РІРµС‚РѕРІС‹Рµ РєРѕРјРїРѕРЅРµРЅС‚С‹.

## Entities

There is one active physical gateway device. Published independent channels are Light/Switch entities; RGB/RGBW groups are Light entities. Group members are hidden as separate controls until ungrouped. IDs derive from persistent gateway/channel/group IDs, not names or DMX addresses.

Registry records for hidden or removed logical controls are retained and disabled by the integration. Their existing entity_id, unique_id and customizations are not deleted. Explicit user disabling is preserved. The two known legacy physical child records (`SkyDance S1-DR` and `sss1`) and their obsolete disabled entities are cleaned up; the BELARD gateway and its stable logical channel identities are preserved. Mapping identities from an older incompatible firmware must be reviewed; retained inactive legacy records alone do not prove old automations have been migrated.

## Security / Diagnostics

Scoped HA Bearer tokens can read runtime state and control light/blackout, but cannot change configuration, Wi-Fi, administrator credentials or OTA. HTTPS uses either normal CA validation or an explicit owner-verified SHA-256 leaf pin. A wrong certificate or token is rejected.

Diagnostics use gateway readings. A save that has not yet been attempted is unknown, not a write failure. Software TX counters and measured enqueue rate do not replace electrical BREAK/MAB measurements.

## Tests

`tests/run_core_tests.py` runs against the official Home Assistant Core 2026.10.4 image with isolated configuration and an in-process gateway fixture. It checks entity registry preservation, topology changes, RGB/RGBW control, delayed-poll ordering, read-failure/reconnect recovery, ambiguous command-response recovery, blackout, reconfiguration, token redaction, human-readable uptime, memory units and the HTTPS default port. The fixture is not a physical gateway test. On 2026-11-05 live checks also exercised both physical channels in both HAв†”gatewayв†”Cloud directions, blackout, HA Core restart/reconnect, interruption of a six-second HA fade by a Cloud command, and repeated refreshes without stale replay. Those runs restored the original DMX levels. Separate native-project tests exercise verified TLS and the native C++ runtime/auth code.

No credentials, personalized identity images or firmware binaries belong in this repository.

## Verified stability — 2026-11-07

With native firmware `0.1.0-net.20261107.3`, a one-hour physical gateway run recorded 119 samples, no MQTT reconnects, no TLS/HTTP timeouts, no reboot and no DMX transmission error. Free heap recovered after temporary allocations; no sustained leak was observed during this hour. This does not certify electrical BREAK/MAB timing or power-loss OTA rollback. Cloud-origin state propagation was separately measured at 1.41–1.84 seconds including cloud request time. HA remains an independent local client.
