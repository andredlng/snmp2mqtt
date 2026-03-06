#!/usr/bin/env python

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import iot_daemonize
import iot_daemonize.configuration as configuration
from pysnmp.hlapi.v3arch.asyncio import *


config = None


def _auth_protocol(name: Optional[str]):
    if not name:
        return usmNoAuthProtocol
    m = {
        'MD5': 'usmHMACMD5AuthProtocol',
        'SHA': 'usmHMACSHAAuthProtocol',
        'SHA224': 'usmHMAC128SHA224AuthProtocol',
        'SHA256': 'usmHMAC192SHA256AuthProtocol',
        'SHA384': 'usmHMAC256SHA384AuthProtocol',
        'SHA512': 'usmHMAC384SHA512AuthProtocol',
    }
    attr = m.get(name.upper(), 'usmHMACSHAAuthProtocol')
    return getattr(globals(), attr, usmHMACSHAAuthProtocol)


def _priv_protocol(name: Optional[str]):
    if not name:
        return usmNoPrivProtocol
    m = {
        'DES': 'usmDESPrivProtocol',
        '3DES': 'usm3DESEDEPrivProtocol',
        'AES': 'usmAesCfb128Protocol',
        'AES128': 'usmAesCfb128Protocol',
        'AES192': 'usmAesCfb192Protocol',
        'AES256': 'usmAesCfb256Protocol',
    }
    attr = m.get(name.upper(), 'usmAesCfb128Protocol')
    return getattr(globals(), attr, usmAesCfb128Protocol)


def build_auth(target: Dict[str, Any]):
    version = (target.get('version') or 'v2c').lower()
    if version in ('v1', 'v2c'):
        mp_model = 0 if version == 'v1' else 1
        return CommunityData(target.get('community', 'public'), mpModel=mp_model)
    # v3
    level = (target.get('level') or 'noAuthNoPriv')
    user = target.get('user')
    auth_key = target.get('auth_key')
    priv_key = target.get('priv_key')
    if level == 'noAuthNoPriv':
        return UsmUserData(user)
    elif level == 'authNoPriv':
        return UsmUserData(user, authKey=auth_key, authProtocol=_auth_protocol(target.get('auth_protocol')))
    elif level == 'authPriv':
        return UsmUserData(
            user,
            authKey=auth_key,
            authProtocol=_auth_protocol(target.get('auth_protocol')),
            privKey=priv_key,
            privProtocol=_priv_protocol(target.get('priv_protocol')),
        )
    else:
        return UsmUserData(user)


def _transform(value_str: str, transform: Optional[str]) -> str:
    if not transform:
        return value_str
    try:
        if transform == 'int':
            return str(int(float(value_str)))
        if transform == 'float':
            return str(float(value_str))
        if transform == 'str':
            return str(value_str)
    except Exception:
        pass
    return value_str


async def poll_scalar_once(engine, auth, transport, oid: str) -> List[Tuple[str, str]]:
    errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
        engine,
        auth,
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    results: List[Tuple[str, str]] = []
    if errorIndication:
        raise RuntimeError(str(errorIndication))
    if errorStatus:
        raise RuntimeError(f"{errorStatus.prettyPrint()} at {errorIndex}")
    for name, val in varBinds:
        results.append((name.prettyPrint(), val.prettyPrint()))
    return results


async def poll_scalar(target_name: str, engine, auth, transport, oid_cfg: Dict[str, Any], stop):
    base_topic = f"{config.mqtt_topic}/{target_name}"
    oid = oid_cfg['oid']
    name = oid_cfg.get('name') or oid
    while not stop():
        try:
            varBinds = await poll_scalar_once(engine, auth, transport, oid)
            for _name, val in varBinds:
                payload = _transform(val, oid_cfg.get('transform'))
                iot_daemonize.mqtt_client.publish(f"{base_topic}/{name}", payload)
        except Exception as e:
            logging.warning(f"SNMP GET error for {target_name} {oid}: {e}")
        await asyncio.sleep(int(target_interval(transport)))


def target_interval(transport) -> int:
    return getattr(transport, '_interval', 30)


def set_target_interval(transport, interval: int):
    setattr(transport, '_interval', max(1, int(interval)))


def compute_index_suffix(root_oid: str, full_oid: str) -> str:
    if full_oid.startswith(root_oid + '.'):
        return full_oid[len(root_oid) + 1:]
    return ''


async def walk_once(engine, auth, transport, root_oid: str) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    async for (errorIndication, errorStatus, errorIndex, varBinds) in next_cmd(
        engine,
        auth,
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(root_oid)),
        lexicographicMode=False,
    ):
        if errorIndication:
            raise RuntimeError(str(errorIndication))
        if errorStatus:
            raise RuntimeError(f"{errorStatus.prettyPrint()} at {errorIndex}")
        for name, val in varBinds:
            results.append((name.prettyPrint(), val.prettyPrint()))
    return results


async def poll_walk(target_name: str, engine, auth, transport, oid_cfg: Dict[str, Any], stop):
    base_topic = f"{config.mqtt_topic}/{target_name}"
    root_oid = oid_cfg['oid']
    while not stop():
        try:
            varBinds = await walk_once(engine, auth, transport, root_oid)
            for name_str, val_str in varBinds:
                index = compute_index_suffix(root_oid, name_str)
                topic = f"{base_topic}/{oid_cfg.get('name') or root_oid}"
                if index:
                    topic = f"{topic}/{index}"
                payload = _transform(val_str, oid_cfg.get('transform'))
                iot_daemonize.mqtt_client.publish(topic, payload)
        except Exception as e:
            logging.warning(f"SNMP WALK loop error for {target_name} {root_oid}: {e}")
        await asyncio.sleep(int(target_interval(transport)))


async def run_target(target: Dict[str, Any], engine, stop):
    name = target.get('name') or f"{target.get('host')}_{target.get('port', 161)}"
    auth = build_auth(target)
    host = target.get('host', 'localhost')
    port = int(target.get('port', 161))
    timeout = int(target.get('timeout', 1))
    retries = int(target.get('retries', 3))
    interval = int(target.get('interval', 30))
    transport = await UdpTransportTarget.create((host, port), timeout=timeout, retries=retries)
    set_target_interval(transport, interval)

    tasks = []
    for oid_cfg in (target.get('oids') or []):
        if oid_cfg.get('walk'):
            tasks.append(asyncio.create_task(poll_walk(name, engine, auth, transport, oid_cfg, stop)))
        else:
            tasks.append(asyncio.create_task(poll_scalar(name, engine, auth, transport, oid_cfg, stop)))
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        raise


def poll_snmp(stop):
    if config.targets is None:
        return
    loop = asyncio.new_event_loop()
    engine = SnmpEngine()
    for target in config.targets:
        loop.create_task(run_target(target, engine, stop))
    loop.run_forever()


def main():
    global config

    config = configuration.MqttDaemonConfiguration(
        program='snmp2mqtt',
        description='An SNMP to MQTT bridge')
    config.add_config_arg('mqtt_clientid', flags='--mqtt_clientid', default='snmp2mqtt',
                         help='The clientid to send to the MQTT server. Default is snmp2mqtt.')
    config.add_config_arg('mqtt_topic', flags='--mqtt_topic', default='bus/snmp',
                         help='The topic to publish MQTT messages. Default is bus/snmp.')
    config.add_config_arg('config', flags=['-c', '--config'], default='/etc/snmp2mqtt.conf',
                         help='The path to the config file. Default is /etc/snmp2mqtt.conf.')
    config.add_config_arg('targets',
                         help='The SNMP targets to poll.')
    config.parse_args()
    config.parse_config(config.config)

    iot_daemonize.init(config, mqtt=True, daemonize=True)

    iot_daemonize.daemon.add_task(poll_snmp)

    iot_daemonize.run()


if __name__ == '__main__':
    main()
