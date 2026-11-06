# BELARD DMX Gateway for Home Assistant

Local integration for the existing native ESP-IDF 5.5.5 gateway. Home Assistant is an optional client; the gateway works independently.

## Configure / Настройка

1. Configure Wi-Fi and channels in the gateway Web UI. On its personalized WPA2 AP, open `https://192.168.4.1/` using the owner-verified certificate/CA. Sign in with the administrator password.
2. Under **Integrations → Home Assistant**, create a scoped integration token. The administrator password is not the HA token.
3. In HA, add or reconfigure **DMX Gateway**. For native firmware use `https://<LAN-IP>#sha256=<owner-verified-certificate-fingerprint>`, port `443`, and the integration token. The fingerprint is public; never put the token in a URL.
4. Existing legacy HTTP addresses remain supported when explicitly configured with their old scheme and port.

Каналы добавляются в веб-интерфейсе шлюза: **Каналы → имя, DMX-адрес, тип → Добавить канал**. В меню настройки интеграции есть переход к этому разделу. В колонке **Home Assistant** на шлюзе можно включить или отключить публикацию отдельного канала, сохранив DMX-канал и его уровень. Текущее состояние и уровни опрашиваются каждые 5 секунд; топология и диагностика — каждые 60 секунд.

HA и Алиса управляют одним шлюзом независимыми путями. Команда Алисы меняет шлюз через Cloud/MQTT; HA получает состояние следующим read-only опросом. Команда HA управляет шлюзом локально, а тот публикует новое состояние в Cloud/MQTT. При ошибке чтения HA не отправляет старый кэш обратно; после восстановления соединения интеграция перечитывает состояние с устройства. Перед изменением яркости RGB/RGBW-группы HA сначала читает актуальный цвет, чтобы не восстановить устаревшие цветовые компоненты.

## Entities

There is one active physical gateway device. Published independent channels are Light/Switch entities; RGB/RGBW groups are Light entities. Group members are hidden as separate controls until ungrouped. IDs derive from persistent gateway/channel/group IDs, not names or DMX addresses.

Registry records for hidden or removed logical controls are retained and disabled by the integration. Their existing entity_id, unique_id and customizations are not deleted. Explicit user disabling is preserved. The two known legacy physical child records (`SkyDance S1-DR` and `sss1`) and their obsolete disabled entities are cleaned up; the BELARD gateway and its stable logical channel identities are preserved. Mapping identities from an older incompatible firmware must be reviewed; retained inactive legacy records alone do not prove old automations have been migrated.

## Security / Diagnostics

Scoped HA Bearer tokens can read runtime state and control light/blackout, but cannot change configuration, Wi-Fi, administrator credentials or OTA. HTTPS uses either normal CA validation or an explicit owner-verified SHA-256 leaf pin. A wrong certificate or token is rejected.

Diagnostics use gateway readings. A save that has not yet been attempted is unknown, not a write failure. Software TX counters and measured enqueue rate do not replace electrical BREAK/MAB measurements.

## Tests

`tests/run_core_tests.py` runs against the official Home Assistant Core 2026.10.4 image with isolated configuration and an in-process gateway fixture. It checks entity registry preservation, topology changes, RGB/RGBW control, delayed-poll ordering, read-failure/reconnect recovery, ambiguous command-response recovery, blackout, reconfiguration, token redaction, human-readable uptime, memory units and the HTTPS default port. The fixture is not a physical gateway test. On 2026-11-05 live checks also exercised both physical channels in both HA↔gateway↔Cloud directions, blackout, HA Core restart/reconnect, interruption of a six-second HA fade by a Cloud command, and repeated refreshes without stale replay. Those runs restored the original DMX levels. Separate native-project tests exercise verified TLS and the native C++ runtime/auth code.

No credentials, personalized identity images or firmware binaries belong in this repository.
