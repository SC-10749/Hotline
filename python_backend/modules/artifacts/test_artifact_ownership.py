"""产物归属：登记必须带归属，下载默认拒绝而不是默认放行。

对应规格 S-013。
"""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.artifacts import create_artifact_router
from python_backend.modules.storage.objects import ObjectStorage
from .store import ArtifactStore, artifact_metadata


class ArtifactOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.generated = self.root / 'generated'
        self.generated.mkdir()
        self.artifacts = ArtifactStore(self.root / 'artifacts.db')
        self.storage = ObjectStorage(
            SimpleNamespace(file_storage_backend='local', generated_dir=self.generated))

    def tearDown(self):
        self.temp.cleanup()

    def client(self, settings=None):
        app = FastAPI()
        app.include_router(create_artifact_router(self.artifacts, self.storage, settings))
        return TestClient(app)

    def register(self, owner='alice', key='run-A/result.txt'):
        target = self.generated / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'result')
        return self.artifacts.register(
            run_id='run-A', name=Path(key).name, size=6,
            sha256=hashlib.sha256(b'result').hexdigest(), content_type='text/plain',
            storage_backend='local', storage_key=key, owner=owner)

    def test_registration_without_owner_is_rejected(self):
        with self.assertRaises(ValueError):
            self.register(owner='')

    def test_matching_owner_can_download(self):
        record = self.register(owner='alice')
        response = self.client().get(f"/harness/artifacts/{record['artifact_id']}/download",
                                      headers={'X-Harness-Owner': 'alice'})
        self.assertEqual(response.status_code, 200)

    def test_wrong_owner_is_rejected(self):
        record = self.register(owner='alice')
        response = self.client().get(f"/harness/artifacts/{record['artifact_id']}/download",
                                      headers={'X-Harness-Owner': 'bob'})
        self.assertEqual(response.status_code, 403)

    def test_missing_owner_header_is_rejected(self):
        record = self.register(owner='alice')
        response = self.client().get(f"/harness/artifacts/{record['artifact_id']}/download")
        self.assertEqual(response.status_code, 403)

    def test_legacy_record_without_owner_is_rejected(self):
        record = self.register(owner='alice')
        db = sqlite3.connect(self.root / 'artifacts.db')
        try:
            db.execute("UPDATE run_artifact SET owner='' WHERE artifact_id=?", (record['artifact_id'],))
            db.commit()
        finally:
            db.close()
        response = self.client().get(f"/harness/artifacts/{record['artifact_id']}/download",
                                      headers={'X-Harness-Owner': 'alice'})
        self.assertEqual(response.status_code, 403)
        self.assertIn('未登记归属', response.json()['detail'])

    def test_download_link_carries_the_owner(self):
        record = self.register(owner='alice')
        link = artifact_metadata(record)['download']
        self.assertIn('owner=alice', link)
        response = self.client().get(link)
        self.assertEqual(response.status_code, 200)

    def test_configured_header_name_is_accepted(self):
        record = self.register(owner='alice')
        client = self.client(lambda: {'artifactOwnerHeader': 'X-Owner'})
        ok = client.get(f"/harness/artifacts/{record['artifact_id']}/download",
                        headers={'X-Owner': 'alice'})
        self.assertEqual(ok.status_code, 200)
        # 默认名仍然兼容，前端还没拿到设置时也能下载。
        fallback = client.get(f"/harness/artifacts/{record['artifact_id']}/download",
                              headers={'X-Harness-Owner': 'alice'})
        self.assertEqual(fallback.status_code, 200)
        wrong = client.get(f"/harness/artifacts/{record['artifact_id']}/download",
                           headers={'X-Owner': 'bob'})
        self.assertEqual(wrong.status_code, 403)
