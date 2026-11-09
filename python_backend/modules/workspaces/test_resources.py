from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.resources import create_resource_router
from ...infrastructure.resource_store import ResourceStore
from ...skill_center import Catalog


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(['git', *args], cwd=str(cwd), check=True, capture_output=True,
                   env={**os.environ, 'GIT_AUTHOR_NAME': 'test', 'GIT_AUTHOR_EMAIL': 'test@example.com',
                        'GIT_COMMITTER_NAME': 'test', 'GIT_COMMITTER_EMAIL': 'test@example.com'})


def make_git_repo(root: Path, branch: str = 'main') -> Path:
    """建一个本地 git 仓库，作为检出的来源；只在本机跑，不连远端。"""
    repo = root / 'source-repo'
    repo.mkdir(parents=True, exist_ok=True)
    _git(['init', '-q', '-b', branch], repo)
    (repo / 'README.md').write_text('hello', encoding='utf-8')
    _git(['add', '.'], repo)
    _git(['commit', '-q', '-m', 'init'], repo)
    _git(['branch', 'feature'], repo)
    return repo


def build_execution_db(path: Path, rows: list[tuple]) -> Path:
    db = sqlite3.connect(path)
    db.execute(
        '''CREATE TABLE execution_run (
            run_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            query TEXT NOT NULL,
            file_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT ''
        )'''
    )
    db.executemany(
        'INSERT INTO execution_run(run_id,conversation_id,agent,query,status,created_at,agent_id,workspace_id)'
        ' VALUES(?,?,?,?,?,?,?,?)', rows)
    db.commit()
    db.close()
    return path


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ResourceStore(self.root / 'resources.db')
        self.client = TestClient(self._app())

    def tearDown(self):
        self.temp.cleanup()

    def _app(self):
        app = FastAPI()
        app.include_router(create_resource_router(self.store))
        return app

    def create_agent(self, **overrides):
        payload = {'name': '客服助手', 'description': '处理工单', 'version': 'v1', 'model': 'auto',
                   'policy': {'timeout': 30}}
        payload.update(overrides)
        response = self.client.post('/harness/agents', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['agent']

    def create_workspace(self, **overrides):
        payload = {'name': '主工作区', 'repository': '', 'branch': 'main'}
        payload.update(overrides)
        response = self.client.post('/harness/workspaces', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['workspace']

    def test_legacy_agent_table_gains_enabled_tools_and_skills(self):
        legacy = self.root / 'legacy.db'
        db = sqlite3.connect(legacy)
        db.execute(
            '''CREATE TABLE harness_agent (
                agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT 'v1', model TEXT NOT NULL DEFAULT 'auto',
                policy TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''
        )
        db.execute("INSERT INTO harness_agent(agent_id,name) VALUES('agent-old','旧 Agent')")
        db.commit()
        db.close()
        reopened = ResourceStore(legacy)
        items = reopened.list_agents()
        self.assertEqual(items[0]['enabled'], False)
        self.assertEqual(items[0]['tools'], [])
        self.assertEqual(items[0]['skills'], [])
        self.assertEqual(reopened.get_agent('agent-old')['revision'], 1)

    def test_agent_list_and_detail_carry_enabled_tools_and_skills(self):
        agent = self.create_agent(tools=['search'])
        self.assertEqual(agent['enabled'], False)
        self.assertEqual(agent['tools'], ['search'])
        self.assertEqual(agent['skills'], [])
        listed = self.client.get('/harness/agents').json()['items']
        self.assertEqual(listed[0]['tools'], ['search'])
        self.assertIn('enabled', listed[0])
        detail = self.client.get(f"/harness/agents/{agent['agent_id']}").json()['agent']
        self.assertIn('enabled', detail)
        self.assertIn('skills', detail)

    def test_status_toggle_switches_agent_and_rejects_unknown(self):
        agent = self.create_agent()
        response = self.client.put(f"/harness/agents/{agent['agent_id']}/status", json={'enabled': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['agent']['enabled'])
        again = self.client.put(f"/harness/agents/{agent['agent_id']}/status", json={'enabled': False})
        self.assertFalse(again.json()['agent']['enabled'])
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.assertEqual(len(versions), 3)
        self.client.put(f"/harness/agents/{agent['agent_id']}/status", json={'enabled': False})
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.assertEqual(len(versions), 3)
        missing = self.client.put('/harness/agents/agent-missing/status', json={'enabled': True})
        self.assertEqual(missing.status_code, 404)

    def test_skill_binding_overwrites_and_unbinds_single_skill(self):
        agent = self.create_agent()
        bound = self.client.post(f"/harness/agents/{agent['agent_id']}/skills",
                                 json={'skillIds': ['skill-a', 'skill-b']})
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(bound.json()['agent']['skills'], ['skill-a', 'skill-b'])
        replaced = self.client.post(f"/harness/agents/{agent['agent_id']}/skills", json={'skillIds': ['skill-c']})
        self.assertEqual(replaced.json()['agent']['skills'], ['skill-c'])
        removed = self.client.delete(f"/harness/agents/{agent['agent_id']}/skills/skill-c")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()['agent']['skills'], [])
        self.client.post(f"/harness/agents/{agent['agent_id']}/skills", json={'skillIds': ['skill-c']})
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.client.post(f"/harness/agents/{agent['agent_id']}/skills", json={'skillIds': ['skill-c']})
        repeated = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.assertEqual(len(repeated), len(versions))
        self.assertEqual(self.client.delete(f"/harness/agents/agent-missing/skills/x").status_code, 404)

    def test_update_keeps_tools_when_payload_omits_them(self):
        agent = self.create_agent(tools=['search'])
        response = self.client.put(f"/harness/agents/{agent['agent_id']}",
                                   json={'name': '新名字', 'description': '', 'version': 'v2',
                                         'model': 'auto', 'policy': {}, 'revision': agent['revision']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['agent']['tools'], ['search'])

    def test_stale_revision_is_rejected(self):
        agent = self.create_agent()
        stale = self.client.put(f"/harness/agents/{agent['agent_id']}",
                                json={'name': '改名', 'description': '', 'version': 'v2',
                                      'model': 'auto', 'policy': {}, 'revision': agent['revision'] + 1})
        self.assertEqual(stale.status_code, 409)

    def test_version_history_records_create_and_update(self):
        agent = self.create_agent()
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]['name'], '客服助手')
        update = self.client.put(f"/harness/agents/{agent['agent_id']}",
                                 json={'name': '改名后', 'description': '', 'version': 'v2',
                                       'model': 'auto', 'policy': {}, 'revision': agent['revision']})
        self.assertEqual(update.status_code, 200, update.text)
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]['name'], '改名后')
        self.assertEqual(versions[1]['name'], '客服助手')
        self.assertEqual(self.client.get('/harness/agents/agent-missing/versions').status_code, 404)

    def test_diff_reports_changed_fields_and_skill_additions(self):
        agent = self.create_agent()
        self.client.put(f"/harness/agents/{agent['agent_id']}",
                        json={'name': '改名后', 'description': '', 'version': 'v2',
                              'model': 'auto', 'policy': {}, 'revision': agent['revision']})
        self.client.post(f"/harness/agents/{agent['agent_id']}/skills", json={'skillIds': ['skill-a']})
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        target, base = versions[0], versions[-1]
        diff = self.client.get(f"/harness/agents/{agent['agent_id']}/diff",
                                params={'base': base['version_id'], 'target': target['version_id']}).json()
        fields = {item['field'] for item in diff['changed']}
        self.assertIn('name', fields)
        self.assertIn('skills', fields)
        self.assertEqual(diff['added'], [{'field': 'skills', 'value': 'skill-a'}])
        self.assertEqual(diff['removed'], [])
        missing = self.client.get(f"/harness/agents/{agent['agent_id']}/diff",
                                  params={'base': 'nope', 'target': target['version_id']})
        self.assertEqual(missing.status_code, 404)

    def test_diff_ignores_policy_key_order(self):
        agent = self.create_agent(policy={'a': 1, 'b': 2})
        self.client.put(f"/harness/agents/{agent['agent_id']}",
                        json={'name': '客服助手', 'description': '处理工单', 'version': 'v1',
                              'model': 'auto', 'policy': {'b': 2, 'a': 1}, 'revision': agent['revision']})
        versions = self.client.get(f"/harness/agents/{agent['agent_id']}/versions").json()['items']
        diff = self.client.get(f"/harness/agents/{agent['agent_id']}/diff",
                                params={'base': versions[-1]['version_id'],
                                        'target': versions[0]['version_id']}).json()
        self.assertEqual(diff['changed'], [])
        self.assertNotEqual(versions[0]['policy'], versions[-1]['policy'])

    def test_workspace_snapshot_counts_real_files_and_skips_git(self):
        repo = self.root / 'repo'
        (repo / '.git').mkdir(parents=True)
        (repo / '.git' / 'config').write_text('ignored', encoding='utf-8')
        (repo / 'a.txt').write_text('hello', encoding='utf-8')
        (repo / 'big.bin').write_bytes(b'0' * (3 * 1024 * 1024))
        workspace = self.create_workspace(repository=str(repo), branch='dev')
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/snapshots")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()['snapshot']
        self.assertEqual(snapshot['file_count'], 2)
        self.assertEqual(snapshot['size_bytes'], 5)
        self.assertEqual(snapshot['branch'], 'dev')
        self.assertEqual(snapshot['commit'], 'local')
        changes = self.client.get(
            f"/harness/workspaces/{workspace['workspace_id']}/snapshots/{snapshot['snapshot_id']}/changes").json()
        self.assertEqual({item['path'] for item in changes['items']}, {'a.txt', 'big.bin'})
        self.assertEqual({item['change_type'] for item in changes['items']}, {'tracked'})
        listed = self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/snapshots").json()['items']
        self.assertEqual(len(listed), 1)

    def test_snapshot_of_unreachable_repository_is_rejected(self):
        workspace = self.create_workspace(repository='https://example.invalid/repo.git')
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/snapshots")
        self.assertEqual(response.status_code, 400)
        self.assertIn('仓库路径不可访问', response.json()['detail'])
        self.assertEqual(
            self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/snapshots").json()['items'], [])

    def test_workspace_change_registration_validates_type(self):
        workspace = self.create_workspace()
        ok = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/changes",
                              json={'path': 'src/app.py', 'changeType': 'modified'})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()['change']['change_type'], 'modified')
        bad = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/changes",
                               json={'path': 'src/app.py', 'changeType': 'renamed'})
        self.assertEqual(bad.status_code, 400)
        empty = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/changes",
                                 json={'path': '  ', 'changeType': 'tracked'})
        self.assertEqual(empty.status_code, 422)

    def test_runs_are_read_only_links_to_execution_records(self):
        agent = self.create_agent()
        workspace = self.create_workspace()
        execution_db = build_execution_db(self.root / 'execution.db', [
            ('run-1', 'conv-1', 'chat', 'q1', 'completed', '2026-01-01T00:00:00Z', agent['agent_id'], workspace['workspace_id']),
            ('run-2', 'conv-2', 'chat', 'q2', 'failed', '2026-01-02T00:00:00Z', 'agent-other', workspace['workspace_id']),
        ])
        with patch('python_backend.api.routers.resources.settings',
                   SimpleNamespace(execution_db_path=execution_db)):
            agent_runs = self.client.get(f"/harness/agents/{agent['agent_id']}/runs").json()
            self.assertEqual([item['run_id'] for item in agent_runs['items']], ['run-1'])
            self.assertEqual(agent_runs['items'][0]['status'], 'completed')
            workspace_runs = self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/runs").json()
            self.assertEqual({item['run_id'] for item in workspace_runs['items']}, {'run-1', 'run-2'})
            limited = self.client.get(f"/harness/agents/{agent['agent_id']}/runs?limit=1").json()
            self.assertEqual(len(limited['items']), 1)

    def test_missing_execution_database_returns_empty_runs(self):
        agent = self.create_agent()
        missing = self.root / 'no-such' / 'execution.db'
        with patch('python_backend.api.routers.resources.settings',
                   SimpleNamespace(execution_db_path=missing)):
            response = self.client.get(f"/harness/agents/{agent['agent_id']}/runs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])


class WorkspaceCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ResourceStore(self.root / 'resources.db')
        self.client = TestClient(self._app())
        self.repo = make_git_repo(self.root)
        self.remote = 'file:///' + self.repo.as_posix().replace(':', ':').lstrip('/')

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def _app(self):
        app = FastAPI()
        app.include_router(create_resource_router(self.store))
        return app

    def create_workspace(self, **overrides):
        payload = {'name': '主工作区', 'repository': self.remote, 'branch': 'main'}
        payload.update(overrides)
        response = self.client.post('/harness/workspaces', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['workspace']

    def test_local_directory_is_not_checked_out(self):
        workspace = self.create_workspace(repository=str(self.repo))
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertEqual(body['detail'], '本地目录无需检出')
        self.assertIn('directory', body)
        self.assertEqual(
            self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/checkout").json()['checkedOut'],
            False)

    def test_checkout_clones_branch_and_records_snapshot(self):
        workspace = self.create_workspace(branch='feature')
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['checkout']['branch'], 'feature')
        self.assertNotEqual(body['checkout']['commit'], 'local')
        snapshot = body['snapshot']
        self.assertEqual(snapshot['branch'], 'feature')
        self.assertEqual(snapshot['commit'], body['checkout']['commit'])
        self.assertEqual(snapshot['file_count'], 1)
        changes = self.client.get(
            f"/harness/workspaces/{workspace['workspace_id']}/snapshots/{snapshot['snapshot_id']}/changes").json()
        self.assertEqual({item['path'] for item in changes['items']}, {'README.md'})
        self.assertEqual({item['change_type'] for item in changes['items']}, {'tracked'})

    def test_checkout_lands_inside_managed_directory(self):
        workspace = self.create_workspace()
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        self.assertEqual(response.status_code, 200, response.text)
        checkout_dir = Path(response.json()['checkout']['checkout_dir'])
        self.assertTrue(checkout_dir.is_dir())
        self.assertEqual(checkout_dir.parent.parent, (self.root / 'workspaces').resolve())

    def test_missing_branch_reports_remote_branches(self):
        workspace = self.create_workspace(branch='nope')
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertEqual(body['detail'], '分支不存在')
        self.assertEqual(body['reason'], 'branch_not_found')
        self.assertIn('main', body['branches'])
        self.assertLessEqual(len(body['branches']), 10)

    def test_unreachable_repository_is_not_reported_as_success(self):
        workspace = self.create_workspace(repository='file:///' + (self.root / 'missing').as_posix().lstrip('/'))
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()['reason'], 'unreachable')
        self.assertEqual(
            self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/checkout").json()['checkedOut'],
            False)

    def test_checkout_status_is_readable(self):
        workspace = self.create_workspace()
        empty = self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/checkout").json()
        self.assertEqual(empty['checkedOut'], False)
        self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        state = self.client.get(f"/harness/workspaces/{workspace['workspace_id']}/checkout").json()
        self.assertEqual(state['checkedOut'], True)
        self.assertEqual(state['branch'], 'main')
        self.assertTrue(state['checkedAt'])
        self.assertEqual(
            self.client.get('/harness/workspaces/workspace-missing/checkout').status_code, 404)

    def test_snapshot_of_checked_out_workspace_uses_real_commit(self):
        workspace = self.create_workspace()
        self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/checkout")
        response = self.client.post(f"/harness/workspaces/{workspace['workspace_id']}/snapshots")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()['snapshot']['commit'], 'local')


class CatalogBindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ResourceStore(self.root / 'resources.db')
        self.catalog_db = self.root / 'catalog.db'
        self.catalog = Catalog(self.catalog_db)
        self.content = '---\nname: demo-skill\ndescription: 演示技能\n---\n\n正文\n'
        self.catalog.call('save', {'content': self.content, 'resources': {'a.md': '第一版'}})
        self.catalog.call('save', {'content': self.content, 'resources': {'a.md': '第二版'}})
        self.client = TestClient(self._app())
        self.settings = SimpleNamespace(skill_catalog_db=self.catalog_db, skill_project='hotline-agent',
                                        execution_db_path=self.root / 'execution.db')

    def tearDown(self):
        self.client.close()
        self.catalog.db.close()
        self.temp.cleanup()

    def _app(self):
        app = FastAPI()
        app.include_router(create_resource_router(self.store))
        return app

    def test_bind_writes_binding_and_audit(self):
        with patch('python_backend.api.routers.resources.settings', self.settings):
            response = self.client.post('/harness/skills/catalog/bind',
                                        json={'name': 'demo-skill', 'version': 'v1'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['binding']['version'], 'v1')
        self.assertEqual([item['version'] for item in body['bindings']], ['v1'])
        audit = body['binding']['audit']
        self.assertEqual(audit['action'], 'bind')
        self.assertIsNotNone(audit['auditId'])

    def test_bind_rejects_unknown_version(self):
        with patch('python_backend.api.routers.resources.settings', self.settings):
            response = self.client.post('/harness/skills/catalog/bind',
                                        json={'name': 'demo-skill', 'version': 'v99'})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertIn('技能版本不存在', response.json()['detail'])

    def test_bind_requires_name_and_version(self):
        with patch('python_backend.api.routers.resources.settings', self.settings):
            empty_name = self.client.post('/harness/skills/catalog/bind', json={'name': ' ', 'version': 'v1'})
            empty_version = self.client.post('/harness/skills/catalog/bind',
                                             json={'name': 'demo-skill', 'version': ' '})
        self.assertEqual(empty_name.status_code, 400)
        self.assertEqual(empty_version.status_code, 400)

    def test_unbind_removes_binding(self):
        with patch('python_backend.api.routers.resources.settings', self.settings):
            self.client.post('/harness/skills/catalog/bind', json={'name': 'demo-skill', 'version': 'v1'})
            response = self.client.request('DELETE', '/harness/skills/catalog/bind',
                                           json={'name': 'demo-skill'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['bindings'], [])
        self.assertEqual(response.json()['binding']['audit']['action'], 'unbind')

    def test_version_compare_returns_resource_diffs(self):
        with patch('python_backend.api.routers.resources.settings', self.settings):
            result = self.catalog.call('version_compare',
                                        {'name': 'demo-skill', 'baseVersion': 'v1', 'version': 'v2'})
        diffs = result['resourceDiffs']
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]['path'], 'a.md')
        self.assertIn('-第一版', diffs[0]['diff'])
        self.assertIn('+第二版', diffs[0]['diff'])
        self.assertFalse(diffs[0]['truncated'])
        self.assertFalse(diffs[0]['unavailable'])

    def test_version_compare_marks_missing_resource_body_unavailable(self):
        self.catalog.call('save', {'content': self.content, 'resources': {}})
        result = self.catalog.call('version_compare',
                                   {'name': 'demo-skill', 'baseVersion': 'v1', 'version': 'v3'})
        diffs = result['resourceDiffs']
        self.assertEqual(len(diffs), 1)
        self.assertTrue(diffs[0]['unavailable'])
        self.assertIsNone(diffs[0]['diff'])


if __name__ == '__main__':
    unittest.main()
