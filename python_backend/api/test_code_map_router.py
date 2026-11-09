from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .routers.code_map import create_code_map_router


class CodeMapRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'code-map'
        self.root.mkdir()
        app = FastAPI()
        app.include_router(create_code_map_router(self.root))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def write_map(self):
        (self.root / 'hotline.html').write_text('<html>Hotline 代码地图</html>', encoding='utf-8')
        (self.root / 'vendor').mkdir()
        (self.root / 'vendor/mermaid.min.js').write_text('window.mermaid = {};', encoding='utf-8')

    def test_missing_or_incomplete_map_is_unavailable(self):
        self.assertEqual(self.client.get('/code-map').json(), {'available': False})
        self.assertEqual(self.client.get('/code-map/hotline.html').status_code, 404)
        (self.root / 'hotline.html').write_text('map', encoding='utf-8')
        self.assertEqual(self.client.get('/code-map').json(), {'available': False})

    def test_map_and_renderer_are_served_with_correct_types(self):
        self.write_map()
        self.assertEqual(self.client.get('/code-map').json(), {'available': True})
        response = self.client.get('/code-map/hotline.html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('代码地图', response.text)
        self.assertIn('text/html', response.headers['content-type'])
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        script = self.client.get('/code-map/vendor/mermaid.min.js')
        self.assertEqual(script.status_code, 200)
        self.assertIn('application/javascript', script.headers['content-type'])

    def test_other_files_and_traversal_are_rejected(self):
        self.write_map()
        (self.root / 'private.local.txt').write_text('private fixture', encoding='utf-8')
        for path in ['private.local.txt', 'build_map.py', 'vendor/../private.local.txt',
                     '%2e%2e/private.local.txt', 'vendor/%2e%2e/%2e%2e/private.local.txt']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/code-map/' + path).status_code, 404)

    def test_symlink_cannot_serve_a_file_outside_map_directory(self):
        outside = Path(self.temp.name) / 'outside.html'
        outside.write_text('private fixture', encoding='utf-8')
        try:
            (self.root / 'hotline.html').symlink_to(outside)
        except OSError:
            self.skipTest('当前系统没有创建符号链接的权限')
        self.assertEqual(self.client.get('/code-map/hotline.html').status_code, 404)
        self.assertFalse(self.client.get('/code-map').json()['available'])


if __name__ == '__main__':
    unittest.main()
