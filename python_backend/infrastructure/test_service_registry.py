import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from .service_registry import NacosRegistry, RegistryConfig


class RegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_does_not_create_client(self):
        registry = NacosRegistry(RegistryConfig(), Path('.'))
        await registry.start()
        self.assertTrue(registry.available)
        self.assertIsNone(registry.task)
        await registry.stop()

    async def test_register_metadata_and_deregister_on_shutdown(self):
        registry = NacosRegistry(RegistryConfig(True, '127.0.0.1:8848', '127.0.0.1'), Path('.'), lambda: False)
        registry.client = AsyncMock()
        registry.client.register_instance.return_value = True
        await registry.start()
        for _ in range(20):
            await asyncio.sleep(0.01)
            if registry.registered:
                break
        self.assertTrue(registry.available)
        request = registry.client.register_instance.call_args.args[0]
        self.assertEqual(request.metadata, {'apiVersion': '1', 'draining': 'true'})
        self.assertFalse(request.enabled)
        self.assertEqual(request.service_name, 'hotline-python-api')
        await registry.stop()
        registry.client.deregister_instance.assert_awaited_once()
        registry.client.shutdown.assert_awaited_once()
        self.assertFalse(registry.registered)

    async def test_failure_is_not_ready_and_shutdown_still_closes_client(self):
        registry = NacosRegistry(RegistryConfig(True, '127.0.0.1:8848', '127.0.0.1'), Path('.'))
        registry.client = AsyncMock()
        registry.client.register_instance.side_effect = RuntimeError('private diagnostics')
        registry.client.deregister_instance.side_effect = RuntimeError('private diagnostics')
        with self.assertLogs('python_backend.infrastructure.service_registry', level='WARNING') as logs:
            await registry.start()
            await asyncio.sleep(0.02)
            self.assertFalse(registry.available)
            await registry.stop()
        self.assertNotIn('private diagnostics', ''.join(logs.output))
        registry.client.shutdown.assert_awaited_once()

    def test_registration_requires_explicit_reachable_address(self):
        with patch.dict('os.environ', {'HOTLINE_PYTHON_NACOS_ENABLED': 'true',
                                      'HOTLINE_NACOS_SERVER_ADDR': '127.0.0.1:8848',
                                      'HOTLINE_PYTHON_ADVERTISED_IP': '0.0.0.0'}, clear=True):
            with self.assertRaises(ValueError):
                RegistryConfig.from_environment()


if __name__ == '__main__':
    unittest.main()
