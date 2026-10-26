import hashlib
import sqlite3
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_backend.skill_center import Catalog
from python_backend.skills import SkillRegistry

CONTENT = '---\nname: incident-summary\ndescription: 运维事件复盘\n---\n输出影响和处理行动。\n'
PROJECT = 'dodo-agent'


class CatalogTests(unittest.TestCase):
    def test_version_binding_and_agent_prompt(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp, closing(Catalog(Path(temp) / 'catalog.db').db) as db:
            catalog = Catalog.__new__(Catalog)
            catalog.db = db
            old = catalog.call('save', {'content': CONTENT})
            self.assertEqual(old, catalog.call('save', {'content': CONTENT}))
            new = catalog.call('save', {'content': CONTENT + '标记缺失信息。'})
            self.assertEqual(old['version'], 'v1')
            self.assertEqual(new['version'], 'v2')
            self.assertEqual(catalog.call('save', {'content': CONTENT + '补充第三版。'})['version'], 'v3')
            self.assertEqual(catalog.call('save', {'content': CONTENT.replace('incident-summary', 'other-skill')})['version'], 'v1')
            catalog.call('bind', {**old, 'project': PROJECT})
            self.assertEqual(catalog.call('runtime', {'project': PROJECT})['skills'][0]['content'], CONTENT)
            self.assertEqual(catalog.call('runtime', {'project': 'other'})['skills'], [])
            registry = SkillRegistry(SimpleNamespace(skills_dir=Path(temp) / 'local',
                skill_catalog_db=Path(temp) / 'catalog.db', skill_project=PROJECT))
            skill = registry.select('$incident-summary 请复盘')
            self.assertIsNotNone(skill)
            self.assertIn('输出影响和处理行动', registry.prompt_block(skill))
            self.assertIn(old['version'], registry.prompt_block(skill))
            catalog.call('bind', {**new, 'project': PROJECT})
            self.assertEqual(catalog.call('runtime', {'project': PROJECT})['skills'][0]['version'], new['version'])
            catalog.call('bind', {'name': old['name'], 'project': PROJECT})
            self.assertEqual(catalog.call('runtime', {'project': PROJECT})['skills'], [])

    def test_reject_invalid_packages(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp, closing(Catalog(Path(temp) / 'catalog.db').db) as db:
            catalog = Catalog.__new__(Catalog)
            catalog.db = db
            for args in [{'content': 'bad'}, {'content': CONTENT, 'resources': {'../escape': 'bad'}}]:
                with self.assertRaises(ValueError):
                    catalog.call('save', args)
            with self.assertRaises(ValueError):
                catalog.call('bind', {'name': 'missing', 'version': 'missing', 'project': PROJECT})

    def test_evolution_gates_stage_promote_and_rollback(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            catalog = Catalog(Path(temp) / 'catalog.db')
            base_content = CONTENT + ('执行步骤：记录事实并核对证据。\n' * 12)
            old = catalog.call('save', {'content': base_content})
            catalog.call('eval_case', {'caseId': 'case-1', 'split': 'selection',
                                       'case': {'required': ['输出影响和处理行动', '禁止泄露'], 'forbidden': []}})
            catalog.call('eval_case', {'caseId': 'case-2', 'split': 'test',
                                       'case': {'required': ['输出影响和处理行动', '禁止泄露'], 'forbidden': []}})
            evolved = catalog.call('evolve', {'name': old['name'], 'baseVersion': old['version'],
                                              'patches': [{'op': 'add', 'text': '禁止泄露敏感信息。'}]})
            self.assertEqual(evolved['status'], 'staged')
            self.assertTrue(all(evolved['gates'].values()))
            catalog.call('bind', {**old, 'project': PROJECT})
            catalog.call('promote', {'project': PROJECT, 'name': old['name'], 'version': evolved['candidateVersion'], 'percentage': 10})
            self.assertEqual(catalog.call('runtime', {'project': PROJECT})['skills'][0]['version'], evolved['candidateVersion'])
            catalog.call('rollback', {'project': PROJECT, 'name': old['name']})
            self.assertEqual(catalog.call('runtime', {'project': PROJECT})['skills'][0]['version'], old['version'])
            catalog.db.close()

    def test_migrate_existing_hash_versions_and_binding(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path = Path(temp) / 'legacy.db'
            contents = [CONTENT, CONTENT + '第二版。']
            hashes = [hashlib.sha256((c + '\0{}').encode()).hexdigest() for c in contents]
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''CREATE TABLE versions (name TEXT, version TEXT, description TEXT,
                    content TEXT, resources TEXT, source TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(name,version));
                    CREATE TABLE bindings (project TEXT, name TEXT, version TEXT, PRIMARY KEY(project,name));''')
                with db:
                    for content, version in zip(contents, hashes):
                        db.execute('INSERT INTO versions(name,version,description,content,resources,source) VALUES(?,?,?,?,?,?)',
                                   ('incident-summary', version, '运维事件复盘', content, '{}', '{}'))
                    db.execute('INSERT INTO bindings VALUES(?,?,?)', ('dodo', 'incident-summary', hashes[0]))
            catalog = Catalog(path)
            try:
                self.assertEqual(catalog.call('runtime', {'project': 'dodo'})['skills'][0]['version'], 'v1')
                self.assertEqual(catalog.call('save', {'content': contents[1]})['version'], 'v2')
                self.assertEqual(catalog.call('save', {'content': CONTENT + '第三版。'})['version'], 'v3')
            finally:
                catalog.db.close()
            reopened = Catalog(path)
            try:
                self.assertEqual(len(reopened.call('list', {})['skills']), 3)
                self.assertEqual(reopened.call('runtime', {'project': 'dodo'})['skills'][0]['content'], CONTENT)
            finally:
                reopened.db.close()

    def test_migrate_hotline_project_id(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path = Path(temp) / 'hotline.db'
            with closing(Catalog(path).db) as db:
                pass
            with closing(sqlite3.connect(path)) as db:
                with db:
                    db.execute("INSERT INTO versions(name,version,description,content,resources,source) VALUES('incident-summary','v1','运维事件复盘',?, '{}', '{}')", (CONTENT,))
                    db.execute("INSERT INTO bindings VALUES('projects/ai/dodo-agent','incident-summary','v1')")
            catalog = Catalog(path)
            try:
                rows = catalog.call('runtime', {'project': PROJECT})['skills']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['version'], 'v1')
                self.assertEqual(catalog.call('runtime', {'project': 'projects/ai/dodo-agent'})['skills'], [])
            finally:
                catalog.db.close()


if __name__ == '__main__':
    unittest.main()
