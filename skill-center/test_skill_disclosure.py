import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_backend.skill_center import Catalog
from python_backend.skills import SkillRegistry

CONTENT = '---\nname: demo\ndescription: 用于演示\n---\nBODY_SENTINEL\n参考 references/guide.md\n'


class DisclosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'skills'
        self.package = self.repo / 'demo'
        self.package.mkdir(parents=True)
        (self.package / 'SKILL.md').write_text(CONTENT, encoding='utf-8')
        self.settings = SimpleNamespace(
            repo_skills_dir=self.repo, skills_dir=self.root / 'installed',
            skill_catalog_db=self.root / 'catalog.db', skill_project='test-project',
        )
        self.registry = SkillRegistry(self.settings)

    def bind_catalog(self):
        with closing(Catalog(self.settings.skill_catalog_db).db) as database:
            catalog = Catalog.__new__(Catalog)
            catalog.db = database
            saved = catalog.call('save', {'content': CONTENT, 'resources': {'references/guide.md': 'GUIDE_SENTINEL'}})
            catalog.call('bind', {**saved, 'project': self.settings.skill_project})
            return saved

    def test_repository_discovery_only_returns_metadata(self):
        session = self.registry.open_resource_session('request-1')
        self.assertEqual(len(session.descriptors), 1)
        descriptor = session.descriptors[0]
        self.assertEqual(descriptor.name, 'demo')
        self.assertTrue(descriptor.entry_uri.startswith('skill://'))
        self.assertNotIn(str(self.root), repr(descriptor))
        self.assertNotIn('BODY_SENTINEL', repr(descriptor))
        self.assertFalse(self.settings.skill_catalog_db.exists())

    def test_scan_reads_header_not_body_or_reference(self):
        original_open = Path.open
        reads = []

        class HeaderOnly:
            def __init__(self, stream):
                self.stream = stream
                self.lines = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def readline(self, *args):
                self.lines += 1
                if self.lines > 4:
                    raise AssertionError('discovery read the body')
                return self.stream.readline(*args)

        def checked_open(path, *args, **kwargs):
            reads.append(path.name)
            return HeaderOnly(original_open(path, *args, **kwargs))

        with patch.object(Path, 'open', checked_open):
            session = self.registry.open_resource_session('request-1')
        self.assertEqual(len(session.descriptors), 1)
        self.assertEqual(reads, ['SKILL.md'])

    def test_metadata_cache_reads_only_new_or_changed_skill_headers(self):
        first = self.registry.open_resource_session('request-1')
        self.assertEqual([item.name for item in first.descriptors], ['demo'])
        added = self.repo / 'another'
        added.mkdir()
        added_file = added / 'SKILL.md'
        added_file.write_text(CONTENT.replace('name: demo', 'name: another').replace('用于演示', '新增技能'), encoding='utf-8')

        original_header_reader = __import__('python_backend.skills', fromlist=['_read_skill_header'])._read_skill_header
        read_names = []

        def track_header(path):
            read_names.append(path.parent.name)
            return original_header_reader(path)

        with patch('python_backend.skills._read_skill_header', side_effect=track_header):
            second = self.registry.open_resource_session('request-2')
            third = self.registry.open_resource_session('request-3')

        self.assertEqual({item.name for item in second.descriptors}, {'demo', 'another'})
        self.assertEqual({item.name for item in third.descriptors}, {'demo', 'another'})
        self.assertEqual(read_names, ['another'])

    def test_metadata_cache_reloads_only_skill_with_changed_header(self):
        original = self.registry.open_resource_session('request-1')
        (self.package / 'SKILL.md').write_text(CONTENT.replace('用于演示', '更新后的说明'), encoding='utf-8')
        another = self.repo / 'another'
        another.mkdir()
        (another / 'SKILL.md').write_text(
            CONTENT.replace('name: demo', 'name: another').replace('用于演示', '另一个技能'), encoding='utf-8')

        original_header_reader = __import__('python_backend.skills', fromlist=['_read_skill_header'])._read_skill_header
        read_names = []

        def track_header(path):
            read_names.append(path.parent.name)
            return original_header_reader(path)

        with patch('python_backend.skills._read_skill_header', side_effect=track_header):
            refreshed = self.registry.open_resource_session('request-3')
        self.assertCountEqual(read_names, ['demo', 'another'])
        descriptions = {item.name: item.description for item in refreshed.descriptors}
        self.assertEqual(descriptions['demo'], '更新后的说明')
        self.assertEqual(descriptions['another'], '另一个技能')
        self.assertNotEqual(original.descriptors[0].description, descriptions['demo'])

    def test_installed_skill_manifest_is_cached_until_changed(self):
        import io
        import zipfile
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('installed-demo/SKILL.md', CONTENT)
        installed = self.registry.install(archive.getvalue(), 'demo.zip')
        self.registry.open_resource_session('request-1')
        manifest = self.registry._skill_dir(installed.dirName) / '.skill-meta.json'
        original_reader = Path.read_text
        reads = []

        def track_manifest(path, *args, **kwargs):
            if path.name == '.skill-meta.json':
                reads.append(path)
            return original_reader(path, *args, **kwargs)

        with patch.object(Path, 'read_text', track_manifest):
            self.registry.open_resource_session('request-2')
            self.assertEqual(reads, [])
            metadata = json.loads(original_reader(manifest, encoding='utf-8'))
            metadata['description'] = '变更后的摘要'
            manifest.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
            self.registry.open_resource_session('request-3')
        self.assertEqual(reads, [manifest])

    def test_metadata_cache_drops_deleted_skill_without_reading_other_headers(self):
        first = self.registry.open_resource_session('request-1')
        self.assertEqual(len(first.descriptors), 1)
        (self.package / 'SKILL.md').unlink()
        with patch('python_backend.skills._read_skill_header') as read_header:
            second = self.registry.open_resource_session('request-2')
        self.assertEqual(second.descriptors, ())
        read_header.assert_not_called()

    def test_catalog_metadata_does_not_select_content(self):
        self.bind_catalog()
        with closing(Catalog(self.settings.skill_catalog_db).db) as database:
            catalog = Catalog.__new__(Catalog)
            catalog.db = database
            queries = []
            database.set_trace_callback(queries.append)
            rows = catalog.call('runtime_metadata', {'project': self.settings.skill_project, 'requestId': 'request-1'})['skills']
        self.assertEqual(set(rows[0]), {'name', 'version', 'description'})
        projections = [query.lower().split(' from ')[0] for query in queries if query.lstrip().lower().startswith('select')]
        self.assertTrue(projections)
        self.assertFalse(any('content' in query or 'resources' in query or '*' in query for query in projections))

    def test_sources_with_same_name_have_distinct_uris(self):
        self.bind_catalog()
        session = self.registry.open_resource_session('request-1')
        self.assertEqual([item.name for item in session.descriptors], ['demo', 'demo'])
        self.assertEqual(len({item.id for item in session.descriptors}), 2)
        self.assertEqual(len({item.entry_uri for item in session.descriptors}), 2)

    def test_only_configured_skill_roots_are_discovered(self):
        samples = self.root / 'skill-center' / 'samples' / 'extra'
        samples.mkdir(parents=True)
        (samples / 'SKILL.md').write_text(CONTENT, encoding='utf-8')
        session = self.registry.open_resource_session('request-1')
        self.assertEqual(len(session.descriptors), 1)

    def test_reads_body_and_reference_only_when_requested_with_pagination(self):
        reference = self.package / 'references' / 'guide.md'
        reference.parent.mkdir()
        reference.write_text('中文参考 RESOURCE_SENTINEL', encoding='utf-8')
        session = self.registry.open_resource_session('request-1')
        uri = session.descriptors[0].entry_uri
        first = session.read_file(uri, limit=5)
        second = session.read_file(uri, offset=first['next_offset'])
        self.assertEqual(first['text'] + second['text'], CONTENT)
        self.assertTrue(second['eof'])
        self.assertNotIn('RESOURCE_SENTINEL', first['text'] + second['text'])
        resource = session.read_file(uri.replace('SKILL.md', 'references/guide.md'))
        self.assertEqual(resource['text'], '中文参考 RESOURCE_SENTINEL')

    def test_read_skill_resolves_only_registered_id_and_relative_paths(self):
        reference = self.package / 'references' / 'guide.md'
        reference.parent.mkdir()
        reference.write_text('中文参考 RESOURCE_SENTINEL', encoding='utf-8')
        session = self.registry.open_resource_session('request-1')
        skill_id = session.descriptors[0].id
        entry = session.read_skill(skill_id, limit=5)
        remainder = session.read_skill(skill_id, offset=entry['next_offset'])
        self.assertEqual(entry['text'] + remainder['text'], CONTENT)
        self.assertEqual(session.read_skill(skill_id, 'references/guide.md')['text'], '中文参考 RESOURCE_SENTINEL')
        self.assertIn('error', session.read_skill('unknown', 'SKILL.md'))
        self.assertIn('error', session.read_skill(skill_id, '../outside.txt'))

    def test_rejects_unsafe_and_secret_paths_without_leaking_disk_path(self):
        session = self.registry.open_resource_session('request-1')
        base = session.descriptors[0].entry_uri.rsplit('/', 1)[0]
        outside = self.root / 'outside.txt'
        outside.write_text('OUTSIDE_SENTINEL', encoding='utf-8')
        (self.package / 'escape.txt').symlink_to(outside)
        for relative in ('../outside.txt', '%2e%2e/outside.txt', '%252e%252e/outside.txt',
                         '\\outside.txt', '/etc/passwd', '.env', '.env.bak', 'config.env',
                         '.env.example', 'private/file.md', 'secrets/file.md', 'escape.txt',
                         '.skill-meta.json', 'key.pem', 'key.key', 'nested/.env', '.git/config'):
            with self.subTest(relative=relative):
                result = session.read_file(base + '/' + relative)
                self.assertIn('error', result)
                self.assertNotIn(str(self.root), json.dumps(result))
                self.assertNotIn('OUTSIDE_SENTINEL', json.dumps(result))
        self.assertIn('error', session.read_file('file:///etc/passwd'))
        self.assertIn('error', session.read_file('skill://unknown/SKILL.md'))

    def test_local_file_changes_are_detected_and_pages_are_stable(self):
        session = self.registry.open_resource_session('request-1')
        uri = session.descriptors[0].entry_uri
        entry = self.package / 'SKILL.md'
        entry.write_text(CONTENT + 'changed', encoding='utf-8')
        self.assertIn('error', session.read_file(uri))
        session = self.registry.open_resource_session('request-2')
        first = session.read_file(uri, limit=10)
        entry.write_text('changed again', encoding='utf-8')
        remainder = session.read_file(uri, offset=first['next_offset'])
        self.assertEqual(first['text'] + remainder['text'], CONTENT + 'changed')

    def test_rejects_binary_oversize_and_bad_offsets(self):
        (self.package / 'binary.dat').write_bytes(b'\x00\xff\x00')
        (self.package / 'huge.md').write_bytes(b'x' * (1024 * 1024 + 1))
        session = self.registry.open_resource_session('request-1')
        uri = session.descriptors[0].entry_uri
        for filename in ('binary.dat', 'huge.md', 'missing.md'):
            self.assertIn('error', session.read_file(uri.replace('SKILL.md', filename)))
        for offset, limit in ((-1, 10), (0, 0), (0, 12001), (True, 5), (0, False)):
            self.assertIn('error', session.read_file(uri, offset=offset, limit=limit))

    def test_catalog_reads_pinned_version_and_revokes_on_unbind(self):
        saved = self.bind_catalog()
        session = self.registry.open_resource_session('request-1')
        descriptor = next(item for item in session.descriptors if item.version)
        with closing(Catalog(self.settings.skill_catalog_db).db) as database:
            catalog = Catalog.__new__(Catalog)
            catalog.db = database
            newer = catalog.call('save', {'content': CONTENT + 'NEW_VERSION'})
            catalog.call('bind', {**newer, 'project': self.settings.skill_project})
            self.assertEqual(session.read_file(descriptor.entry_uri)['text'], CONTENT)
            reference = descriptor.entry_uri.replace('SKILL.md', 'references/guide.md')
            self.assertEqual(session.read_file(reference)['text'], 'GUIDE_SENTINEL')
            catalog.call('bind', {'name': saved['name'], 'project': self.settings.skill_project})
            self.assertIn('error', session.read_file(descriptor.entry_uri))

    def test_installed_skill_is_revoked_when_disabled(self):
        import io
        import zipfile
        original_ids = {item.id for item in self.registry.open_resource_session('before-install').descriptors}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('demo/SKILL.md', CONTENT)
        installed = self.registry.install(archive.getvalue(), 'demo.zip')
        session = self.registry.open_resource_session('request-1')
        descriptor = next(item for item in session.descriptors if item.id not in original_ids)
        self.assertEqual(session.read_file(descriptor.entry_uri)['text'], CONTENT)
        self.registry.set_enabled(installed.id, False)
        self.assertIn('error', session.read_file(descriptor.entry_uri))

    def test_catalog_resource_path_validation_cannot_be_bypassed(self):
        saved = self.bind_catalog()
        with closing(Catalog(self.settings.skill_catalog_db).db) as database:
            catalog = Catalog.__new__(Catalog)
            catalog.db = database
            for path in ('../SKILL.md', '.env', 'private/file', '/SKILL.md'):
                with self.assertRaises(ValueError):
                    catalog.call('read_runtime_file', {**saved, 'project': self.settings.skill_project,
                                 'requestId': 'request-1', 'path': path})

    def test_missing_catalog_is_not_recreated_during_read(self):
        self.bind_catalog()
        session = self.registry.open_resource_session('request-1')
        descriptor = next(item for item in session.descriptors if item.version)
        self.settings.skill_catalog_db.unlink()
        self.assertIn('error', session.read_file(descriptor.entry_uri))
        self.assertFalse(self.settings.skill_catalog_db.exists())

    def test_deleted_catalog_version_revokes_cached_text(self):
        saved = self.bind_catalog()
        session = self.registry.open_resource_session('request-1')
        descriptor = next(item for item in session.descriptors if item.version)
        self.assertEqual(session.read_file(descriptor.entry_uri)['text'], CONTENT)
        with sqlite3.connect(self.settings.skill_catalog_db) as database:
            database.execute('DELETE FROM versions WHERE name=? AND version=?', (saved['name'], saved['version']))
        self.assertIn('error', session.read_file(descriptor.entry_uri))

    def test_special_files_are_rejected_without_opening(self):
        import os
        target = self.package / 'pipe.txt'
        os.mkfifo(target)
        session = self.registry.open_resource_session('request-1')
        uri = session.descriptors[0].entry_uri.replace('SKILL.md', 'pipe.txt')
        original_open = Path.open

        def reject_fifo_open(path, *args, **kwargs):
            if path.resolve() == target.resolve():
                raise AssertionError('must reject special file before opening')
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', reject_fifo_open):
            self.assertIn('error', session.read_file(uri))

    def test_private_skill_directories_are_not_scanned(self):
        for name in ('private', 'secrets', '.hidden', 'demo.private.copy', 'demo.local.copy'):
            directory = self.repo / name
            directory.mkdir()
            (directory / 'SKILL.md').write_text(CONTENT, encoding='utf-8')
        self.assertEqual(len(self.registry.open_resource_session('request-1').descriptors), 1)


if __name__ == '__main__':
    unittest.main()
