"""Integration lifecycle tests on real HA Core; gateway HTTP is a test fixture.
Run inside the official Home Assistant 2026.10.4 image, mount this repo at /work.
Never connects to the physical gateway or the working Home Assistant.
"""
import asyncio, copy, importlib, json, shutil, tempfile, logging
from dataclasses import replace
logging.basicConfig(level=logging.WARNING)
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
from homeassistant import bootstrap, loader
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

async def main():
    checks = []
    def check(name, result):
        assert result, name
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix="belard-ha-") as tmp:
        shutil.copytree("/work/custom_components", Path(tmp)/"custom_components")
        hass = HomeAssistant(tmp)
        loader.async_setup(hass)
        assert await bootstrap.async_from_config_dict({"homeassistant": {"name": "BELARD isolated test", "country": "RU", "time_zone": "Europe/Moscow"}, "logger": {"default": "error"}}, hass)
        await hass.async_start()
        module = importlib.import_module("custom_components.dmx_gateway")
        model = importlib.import_module("custom_components.dmx_gateway.models")
        light = importlib.import_module("custom_components.dmx_gateway.light")
        api = importlib.import_module("custom_components.dmx_gateway.api")
        info = model.GatewayInfo("test-gateway", "BELARD DMX Gateway", "test-native", "v1")
        channels = tuple(model.LogicalChannel("ch"+str(i), "Channel "+str(i), "Light", i, 0, True) for i in range(1,5))
        config = model.GatewayConfig(2, 1, info.gateway_id, info.model, channels, (), ())
        state = model.GatewayState(1, False, {c.channel_id: model.LogicalChannelState(0, False) for c in channels}, {})
        diagnostics = model.Diagnostics(1,30,0,1,0,4,0,False,110000,True,True,4,0)
        class Client:
            def __init__(self,*args): self.calls=[]
            async def async_get_info(self): return info
            async def async_get_config(self): return config
            async def async_get_state(self): return state
            async def async_get_diagnostics(self): return diagnostics
            async def async_set_group_state(self,gid,values,transition,use_default_fade=False):
                nonlocal state
                self.calls.append((gid,values,transition,use_default_fade));groups=dict(state.groups);groups[gid]=tuple(values);members=next(g.members for g in config.groups if g.group_id==gid);levels=dict(state.channels)
                for key,value in zip(members,values):levels[key]=model.LogicalChannelState(value/255,False)
                state=model.GatewayState(state.config_revision+1,state.blackout,levels,groups)
            async def async_set_channel_state(self,cid,value,transition,use_default_fade=False): self.calls.append((cid,value,transition,use_default_fade))
            async def async_set_blackout(self,value):
                nonlocal state
                state=model.GatewayState(state.config_revision+1,value,state.channels,state.groups)
                return value
        entry = ConfigEntry(domain="dmx_gateway", title="Existing gateway", data={"host":"test", "port":443, "token":"test-only"}, options={}, source="user", unique_id=info.gateway_id, version=1, minor_version=2, discovery_keys=MappingProxyType({}), subentries_data=[])
        hass.config_entries._entries[entry.entry_id] = entry
        devices = dr.async_get(hass); registry = er.async_get(hass)
        old = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("dmx_gateway", "old-fixture")}, name="Old dimmer")
        original = registry.async_get_or_create("light", "dmx_gateway", "test-gateway_ch1", config_entry=entry, device_id=old.id, suggested_object_id="kitchen_existing")
        registry.async_update_entity(original.entity_id, name="Owner custom name")
        sensor = registry.async_get_or_create("sensor", "dmx_gateway", "test-gateway_uptime_s", config_entry=entry, device_id=old.id)
        removed = registry.async_get_or_create("light", "dmx_gateway", "test-gateway_deleted", config_entry=entry, device_id=old.id)
        user_disabled = registry.async_get_or_create("light", "dmx_gateway", "test-gateway_ch4", config_entry=entry, disabled_by=er.RegistryEntryDisabler.USER)
        # The gateway client is an in-process fixture. A network-disabled test
        # container has no multicast interface for HA's unused DNS resolver.
        with patch.object(module, "DmxGatewayApiClient", Client), patch.object(module, "async_get_clientsession", return_value=None):
            setup_ok = await hass.config_entries.async_setup(entry.entry_id)
            if not setup_ok:
                print({"entry_state": str(entry.state), "reason": str(getattr(entry,"reason",None))},flush=True)
            check("existing entry setup", setup_ok)
            await hass.async_block_till_done()
            gateway_device=devices.async_get_device_by_identifier(("dmx_gateway",info.gateway_id),entry.entry_id)
            legacy_s1=devices.async_get_or_create(config_entry_id=entry.entry_id,identifiers={("dmx_gateway",info.gateway_id+":device:s1")},via_device_id=gateway_device.id,name="SkyDance S1-DR",model="DMX runtime device")
            legacy_second=devices.async_get_or_create(config_entry_id=entry.entry_id,identifiers={("dmx_gateway",info.gateway_id+":device:sss1")},via_device_id=gateway_device.id,name="sss1",model="DMX runtime device")
            legacy_select=registry.async_get_or_create("select","dmx_gateway",info.gateway_id+"_legacy_startup",config_entry=entry,device_id=legacy_s1.id)
            legacy_number=registry.async_get_or_create("number","dmx_gateway",info.gateway_id+"_legacy_fade",config_entry=entry,device_id=legacy_second.id)
            module._remove_legacy_child_devices(hass,entry,info.gateway_id)
            check("legacy SkyDance and sss1 child devices removed without removing gateway",devices.async_get_device_by_identifier(("dmx_gateway",info.gateway_id),entry.entry_id) is not None and devices.async_get_device_by_identifier(("dmx_gateway",info.gateway_id+":device:s1"),entry.entry_id) is None and devices.async_get_device_by_identifier(("dmx_gateway",info.gateway_id+":device:sss1"),entry.entry_id) is None)
            check("obsolete child configuration entities removed",registry.async_get(legacy_select.entity_id) is None and registry.async_get(legacy_number.entity_id) is None)
            coordinator=entry.runtime_data.coordinator
            check("four logical channels", len(coordinator.data.config.channels)==4)
            check("existing entity_id preserved", registry.async_get_entity_id("light","dmx_gateway","test-gateway_ch1")==original.entity_id)
            check("custom name preserved", registry.async_get(original.entity_id).name=="Owner custom name")
            check("gateway diagnostics removed from HA registry", registry.async_get(sensor.entity_id) is None)
            check("deleted channel retained disabled", registry.async_get(removed.entity_id).disabled_by==er.RegistryEntryDisabler.INTEGRATION)
            check("user disable retained", registry.async_get(user_disabled.entity_id).disabled_by==er.RegistryEntryDisabler.USER)
            gateway=devices.async_get_device_by_identifier(("dmx_gateway",info.gateway_id),entry.entry_id)
            check("all entities belong to gateway", all(e.device_id==gateway.id for e in er.async_entries_for_config_entry(registry,entry.entry_id)))
            original_state=state
            # Delay an actual state read across a newly requested HA command.
            entered=asyncio.Event();release=asyncio.Event()
            async def delayed_state():
                captured=state
                entered.set()
                await release.wait()
                return captured
            before_calls=len(coordinator.client.calls)
            with patch.object(coordinator.client,"async_get_state",side_effect=delayed_state):
                poll=asyncio.create_task(coordinator.async_refresh_state())
                await entered.wait()
                command=asyncio.create_task(coordinator.async_set_channel("ch1",.75,0))
                await asyncio.sleep(0)
                check("late poll and new command use serialized IO",not command.done() and len(coordinator.client.calls)==before_calls)
                release.set()
                await poll;await command
            check("late state cannot overwrite newer HA command",coordinator.data.commanded_brightness["ch1"]==.75)
            # An external Alice command replaces the cache through GET only.
            state=model.GatewayState(2,False,{c.channel_id:model.LogicalChannelState(.25 if c.channel_id=="ch1" else 0,False) for c in channels},{})
            writes=len(coordinator.client.calls)
            await coordinator.async_refresh_state()
            check("external gateway state replaces HA cache",coordinator.data.commanded_brightness["ch1"]==.25)
            check("state synchronization never replays cached commands",len(coordinator.client.calls)==writes)
            # If the gateway is temporarily unreachable, keep the displayed
            # snapshot but never replay it as a command. The next successful
            # read after reconnection must replace it with the gateway's state.
            error_type=importlib.import_module("custom_components.dmx_gateway.api").GatewayApiError
            actual_before_failure=state
            writes=len(coordinator.client.calls)
            with patch.object(coordinator.client,"async_get_state",side_effect=error_type("temporary transport loss")):
                await coordinator.async_refresh_state()
            check("temporary read failure sends no cached command",len(coordinator.client.calls)==writes)
            check("temporary read failure does not fabricate a new level",coordinator.data.commanded_brightness["ch1"]==.25)
            state=model.GatewayState(3,False,{c.channel_id:model.LogicalChannelState(.6 if c.channel_id=="ch1" else 0,False) for c in channels},{})
            await coordinator.async_refresh_state()
            check("authoritative state recovers after gateway reconnect",coordinator.data.commanded_brightness["ch1"]==.6)
            check("reconnect recovery remains read-only",len(coordinator.client.calls)==writes)
            async def applied_but_response_lost(cid,value,transition,use_default_fade=False):
                nonlocal state
                coordinator.client.calls.append((cid,value,transition,use_default_fade))
                state=model.GatewayState(4,False,{c.channel_id:model.LogicalChannelState(.45 if c.channel_id=="ch1" else 0,False) for c in channels},{})
                raise error_type("response lost after gateway applied command")
            with patch.object(coordinator.client,"async_set_channel_state",side_effect=applied_but_response_lost):
                try: await coordinator.async_set_channel("ch1",.9,0)
                except error_type: pass
                else: raise AssertionError("simulated lost response must reach caller")
            check("ambiguous command response does not make target the cache",coordinator.data.commanded_brightness["ch1"]==.6)
            writes_after_ambiguous=len(coordinator.client.calls)
            await coordinator.async_refresh_state()
            check("ambiguous command recovers actual applied value by read",coordinator.data.commanded_brightness["ch1"]==.45)
            check("ambiguous response recovery issues no second command",len(coordinator.client.calls)==writes_after_ambiguous)
            state=actual_before_failure
            state=original_state
            await coordinator.async_refresh_state()
            group=model.LogicalGroup("group-stable", "RGBW test", "RGBW", tuple(c.channel_id for c in channels))
            config=model.GatewayConfig(2,2,info.gateway_id,info.model,tuple(model.LogicalChannel(c.channel_id,c.name,c.type,c.dmx_address,0,False) for c in channels),(group,),())
            state=model.GatewayState(2,False,state.channels,{group.group_id:(64,32,0,0)})
            await coordinator.async_refresh(); await hass.async_block_till_done()
            coordinator=entry.runtime_data.coordinator
            check("group appears on topology refresh", hass.states.get(registry.async_get_entity_id("light","dmx_gateway","test-gateway_group-stable")) is not None)
            check("grouping preserves original entity_id", registry.async_get(original.entity_id).disabled_by==er.RegistryEntryDisabler.INTEGRATION)
            entity=light.DmxLogicalGroupLight(coordinator,group.group_id)
            check("RGBW normalized color", entity.rgbw_color==(255,128,0,0) and entity.brightness==64)
            await entity.async_turn_on(brightness=128,transition=0.3)
            check("brightness rescaled from current peak", coordinator.client.calls[-1]==(group.group_id,[128,64,0,0],300,False))
            await entity.async_turn_on(brightness=128)
            check("repeated brightness does not compound", coordinator.client.calls[-1][1]==[128,64,0,0])
            check("group updates member states atomically in cache", coordinator.data.commanded_brightness["ch1"]==128/255 and coordinator.data.commanded_brightness["ch2"]==64/255)
            await entity.async_turn_off(); await entity.async_turn_on()
            check("off-on restores color and level", coordinator.client.calls[-1][1]==[128,64,0,0] and coordinator.client.calls[-1][3])
            await entity.async_turn_on(rgbw_color=(0,255,0,128),brightness=100)
            check("RGBW roles and brightness", coordinator.client.calls[-1][1]==[0,100,0,50])
            # Alice changes RGBW before the five-second HA poll. A HA brightness
            # command must scale the fresh blue/white values, never cached green.
            state=model.GatewayState(state.config_revision+1,False,state.channels,{group.group_id:(0,0,80,40)})
            await entity.async_turn_on(brightness=160,transition=0)
            check("HA brightness preserves latest external RGBW color",coordinator.client.calls[-1]==(group.group_id,[0,0,160,80],0,False))
            rgb=model.LogicalGroup(group.group_id,"RGB test","RGB",group.members[:3])
            config=model.GatewayConfig(2,3,info.gateway_id,info.model,config.channels,(rgb,),())
            state=model.GatewayState(3,False,state.channels,{group.group_id:(255,0,0)})
            await coordinator.async_refresh();await hass.async_block_till_done();coordinator=entry.runtime_data.coordinator
            entity=light.DmxLogicalGroupLight(coordinator,group.group_id)
            await entity.async_turn_on(rgb_color=(0,0,255),brightness=80)
            check("RGB command", coordinator.client.calls[-1][1]==[0,0,80] and coordinator.client.calls[-1][3])
            config=model.GatewayConfig(2,4,info.gateway_id,info.model,channels,(),())
            state=model.GatewayState(4,False,state.channels,{})
            await coordinator.async_refresh();await hass.async_block_till_done();coordinator=entry.runtime_data.coordinator
            check("ungroup restores same entity_id", registry.async_get_entity_id("light","dmx_gateway","test-gateway_ch1")==original.entity_id and registry.async_get(original.entity_id).disabled_by is None)
            check("removed group retained without deleting automations", registry.async_get(registry.async_get_entity_id("light","dmx_gateway","test-gateway_group-stable")).disabled_by==er.RegistryEntryDisabler.INTEGRATION)
            # Publication changes must preserve registry identity and automations.
            unpublished=tuple(model.LogicalChannel(c.channel_id,c.name,c.type,c.dmx_address,0,False if c.channel_id=="ch1" else c.published) for c in channels)
            config=model.GatewayConfig(2,5,info.gateway_id,info.model,unpublished,(),())
            await coordinator.async_refresh();await hass.async_block_till_done();coordinator=entry.runtime_data.coordinator
            check("unpublish retains entity registry and custom name", registry.async_get(original.entity_id).disabled_by==er.RegistryEntryDisabler.INTEGRATION and registry.async_get(original.entity_id).name=="Owner custom name")
            config=model.GatewayConfig(2,6,info.gateway_id,info.model,channels,(),())
            await coordinator.async_refresh();await hass.async_block_till_done();coordinator=entry.runtime_data.coordinator
            check("republish restores same entity_id and unique_id", registry.async_get_entity_id("light","dmx_gateway","test-gateway_ch1")==original.entity_id and registry.async_get(original.entity_id).disabled_by is None)
            await coordinator.async_set_blackout(True)
            check("blackout updates state", coordinator.data.state.blackout and coordinator.data.diagnostics.blackout)
            check("blackout reports effective light state as off",not light.DmxLogicalLight(coordinator,"ch1").is_on)
            flow_module=importlib.import_module("custom_components.dmx_gateway.config_flow")
            async def validate(hass, data):
                if data.get("token") != "test-only":
                    raise api.GatewayAuthenticationError("test invalid credential")
                return info
            with patch.object(flow_module,"async_validate_gateway",validate):
                flow=await hass.config_entries.flow.async_init("dmx_gateway",context={"source":"reconfigure","entry_id":entry.entry_id})
                check("reconfigure form", flow["type"]=="form")
                bad=await hass.config_entries.flow.async_configure(flow["flow_id"],{"host":"test","port":443,"token":"wrong"})
                check("flow rejects incorrect token", bad["errors"]=={"base":"invalid_auth"})
                done=await hass.config_entries.flow.async_configure(flow["flow_id"],{"host":"https://test#sha256="+"ab"*32,"port":443,"token":"test-only"})
                check("reconfigure preserves entry identity", done["type"]=="abort" and done["reason"]=="reconfigure_successful" and entry.unique_id==info.gateway_id)
                await hass.async_block_till_done()
                check("reconfigure saved HTTPS endpoint", entry.data["port"]==443 and entry.data["host"].startswith("https://"))
                duplicate=await hass.config_entries.flow.async_init("dmx_gateway",context={"source":"user"},data={"host":"test","port":443,"token":"test-only"})
                check("same gateway cannot create duplicate entry", duplicate["type"]=="abort" and duplicate["reason"]=="already_configured")
            diag=importlib.import_module("custom_components.dmx_gateway.diagnostics")
            sensor_module=importlib.import_module("custom_components.dmx_gateway.sensor")
            from custom_components.dmx_gateway.const import DEFAULT_PORT
            coordinator.data=replace(coordinator.data,diagnostics=replace(coordinator.data.diagnostics,uptime_s=90061,free_heap=1048576))
            uptime_sensor=sensor_module.DmxDiagnosticSensor(coordinator,"uptime_s","Время работы",None,None)
            heap_sensor=sensor_module.DmxDiagnosticSensor(coordinator,"free_heap","Свободная память","MB",sensor_module.SensorDeviceClass.DATA_SIZE)
            check("uptime is human-readable instead of seconds",uptime_sensor.native_value=="1 д 1 ч")
            check("free heap is displayed in MB",heap_sensor.native_value==1.0 and heap_sensor.native_unit_of_measurement=="MB")
            check("native HTTPS port defaults to 443",DEFAULT_PORT==443)
            result=await diag.async_get_config_entry_diagnostics(hass,entry)
            check("diagnostics redact HA token", result["entry"]["token"]!="test-only")
            options=await hass.config_entries.options.async_init(entry.entry_id)
            check("options offer channel configuration", "gateway_settings" in options["menu_options"])
            link=await hass.config_entries.options.async_configure(options["flow_id"],{"next_step_id":"gateway_settings"})
            check("channel help links to trusted gateway URL", link["description_placeholders"]["gateway_url"]=="https://192.168.4.1/#channels")
            coordinator=entry.runtime_data.coordinator
            single=light.DmxLogicalLight(coordinator,"ch1")
            hass.config_entries.async_update_entry(entry,options={"default_fade_enabled":False,"retained_setting":"keep"})
            check("HA does not keep a duplicate fade policy", single._transition_ms({},1.0)==0)
            check("gateway decides fade when HA omits transition", single._transition_ms({},0.3)==0)
            check("explicit HA transition is forwarded unchanged", single._transition_ms({"transition":2.5},1.0)==2500)
            check("explicit zero transition stays immediate", single._transition_ms({"transition":0},1.0)==0)
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_stop()
        print(json.dumps({"success":True,"environment":"official Home Assistant Core 2026.10.4", "gateway":"in-process fixture; no physical DMX commands", "checks":checks},indent=2))
asyncio.run(main())
