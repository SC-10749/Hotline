"""Nacos lifecycle for the capability API; the SDK owns gRPC keepalive/reconnect."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from ipaddress import ip_address
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryConfig:
    enabled: bool = False
    server: str = ''
    ip: str = ''
    port: int = 8888
    service: str = 'hotline-python-api'
    namespace: str = ''
    group: str = 'DEFAULT_GROUP'
    username: str = ''
    password: str = ''

    @classmethod
    def from_environment(cls):
        enabled = os.getenv('HOTLINE_PYTHON_NACOS_ENABLED', 'false').lower() == 'true'
        if not enabled:
            return cls()
        config = cls(True, os.getenv('HOTLINE_NACOS_SERVER_ADDR', ''),
                     os.getenv('HOTLINE_PYTHON_ADVERTISED_IP', ''),
                     int(os.getenv('HOTLINE_PYTHON_ADVERTISED_PORT', os.getenv('DODO_PORT', '8888'))),
                     os.getenv('HOTLINE_PYTHON_SERVICE_NAME', 'hotline-python-api'),
                     os.getenv('HOTLINE_NACOS_NAMESPACE', ''), os.getenv('HOTLINE_NACOS_GROUP', 'DEFAULT_GROUP'),
                     os.getenv('HOTLINE_NACOS_USERNAME', ''), os.getenv('HOTLINE_NACOS_PASSWORD', ''))
        try:
            valid_ip = bool(config.ip) and not ip_address(config.ip).is_unspecified
        except ValueError:
            valid_ip = False
        if not config.server or not valid_ip:
            raise ValueError('Nacos requires a server and explicit reachable Python advertised IP')
        if not 0 < config.port < 65536 or not config.service or not config.group:
            raise ValueError('Invalid Python service registration configuration')
        return config


class NacosRegistry:
    def __init__(self, config: RegistryConfig, data_dir: Path, ready=lambda: True):
        self.config = config
        self.data_dir = data_dir
        self.ready = ready
        self.registered = False
        self.client = None
        self.task = None

    @property
    def available(self):
        return not self.config.enabled or self.registered

    async def start(self):
        if self.config.enabled:
            self.task = asyncio.create_task(self._maintain())

    async def _connect(self):
        from v2.nacos import ClientConfigBuilder, NacosNamingService
        c = self.config
        directory = self.data_dir / 'nacos'
        directory.mkdir(parents=True, exist_ok=True)
        config = (ClientConfigBuilder().server_address(c.server).namespace_id(c.namespace)
                  .username(c.username).password(c.password).timeout_ms(5000)
                  .log_dir(str(directory / 'logs')).cache_dir(str(directory / 'cache')).build())
        self.client = await NacosNamingService.create_naming_service(config)

    async def _publish(self, draining=False):
        from v2.nacos import RegisterInstanceParam
        c = self.config
        return await self.client.register_instance(RegisterInstanceParam(
            service_name=c.service, group_name=c.group, ip=c.ip, port=c.port,
            ephemeral=True, enabled=not draining, healthy=True,
            metadata={'apiVersion': '1', 'draining': str(draining).lower()}))

    async def _maintain(self):
        while True:
            try:
                if self.client is None:
                    await self._connect()
                # Refresh readiness metadata; SDK reconnects and re-registers ephemeral instances.
                result = await asyncio.wait_for(self._publish(draining=not self.ready()), timeout=10)
                self.registered = bool(result)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.registered = False
                # SDK exceptions can contain addresses or credentials.
                logger.warning('Python service registration unavailable; retrying')
            await asyncio.sleep(5)

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.client:
            from v2.nacos import DeregisterInstanceParam
            c = self.config
            try:
                await asyncio.wait_for(self.client.deregister_instance(DeregisterInstanceParam(
                    service_name=c.service, group_name=c.group, ip=c.ip, port=c.port, ephemeral=True)), timeout=5)
            except Exception:
                logger.warning('Python service deregistration unavailable; ephemeral lease will expire')
            finally:
                try:
                    await asyncio.wait_for(self.client.shutdown(), timeout=5)
                except Exception:
                    logger.warning('Python service registry client shutdown timed out or failed')
        self.registered = False
