"""配置默认值必须自洽：不设任何环境变量时，不应隐式依赖外部服务。

背景：`config.py` 的 `DODO_STORAGE_BACKEND` 默认值是 `mysql`，而
`bootstrap.py` 的兜底是 `sqlite`。直接 import config（不走 bootstrap）的进程
——比如单元测试——会拿到 mysql 默认值，于是 `redis_enabled` 跟着变 true，
指向空的 `127.0.0.1:6379`，连接失败直接把测试进程炸掉。

注意：`Settings` 的字段默认值在类定义（导入）时求值，所以这里直接检查模块级
`settings` 实例与显式传参的构造，不在测试里改环境变量重求值。
"""

from __future__ import annotations

import unittest

from python_backend.config import Settings, settings


class SettingsDefaultTests(unittest.TestCase):
    """不设环境变量时，配置不应要求连外部服务。"""

    def test_redis_is_off_by_default(self):
        self.assertFalse(settings.redis_enabled)

    def test_vector_is_off_by_default(self):
        self.assertFalse(settings.vector_enabled)

    def test_storage_defaults_to_sqlite(self):
        self.assertEqual(settings.storage_backend, 'sqlite')

    def test_redis_can_be_enabled_explicitly(self):
        self.assertTrue(Settings(redis_enabled=True).redis_enabled)


if __name__ == '__main__':
    unittest.main()
