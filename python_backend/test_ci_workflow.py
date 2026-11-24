from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from python_backend.api.routers.ci_workflow import create_ci_workflow_router
from python_backend.infrastructure.github_workflow import GitHubWorkflowClient, WorkflowError


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def settings(token='token', repository='owner/repo', workflow='ci.yml'):
    return SimpleNamespace(github_token=token, github_repository=repository,
                           github_ci_workflow=workflow)


class WorkflowClientTests(unittest.TestCase):
    def test_reads_state_and_maps_active_to_enabled(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append((request.get_method(), request.full_url, request.headers))
            return FakeResponse(json.dumps({'state': 'active', 'name': 'CI'}).encode())

        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            state = GitHubWorkflowClient('token', 'owner/repo').workflow_state()

        self.assertEqual(state['enabled'], True)
        self.assertEqual(state['state'], 'active')
        method, url, headers = calls[0]
        self.assertEqual(method, 'GET')
        self.assertEqual(url, 'https://api.github.com/repos/owner/repo/actions/workflows/ci.yml')
        self.assertEqual(headers['Authorization'], 'Bearer token')

    def test_disabled_workflow_is_reported_as_off(self):
        def fake_urlopen(request, timeout=None):
            return FakeResponse(json.dumps({'state': 'disabled_manually'}).encode())

        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            state = GitHubWorkflowClient('token', 'owner/repo').workflow_state()

        self.assertEqual(state['enabled'], False)

    def test_toggles_use_enable_and_disable_endpoints(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append((request.get_method(), request.full_url))
            payload = json.dumps({'state': 'active'}).encode() if request.get_method() == 'GET' else b''
            return FakeResponse(payload)

        client = GitHubWorkflowClient('token', 'owner/repo')
        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            client.set_enabled(False)
            client.set_enabled(True)

        self.assertEqual(calls[0][:2], ('PUT', 'https://api.github.com/repos/owner/repo/actions/workflows/ci.yml/disable'))
        self.assertEqual(calls[2][:2], ('PUT', 'https://api.github.com/repos/owner/repo/actions/workflows/ci.yml/enable'))

    def test_http_error_becomes_workflow_error_without_credential(self):
        import urllib.error

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 403, 'forbidden', None, None)

        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            with self.assertRaises(WorkflowError) as caught:
                GitHubWorkflowClient('secret-token', 'owner/repo').workflow_state()

        self.assertNotIn('secret-token', str(caught.exception))


class CiWorkflowRouterTests(unittest.TestCase):
    def client(self, **kwargs):
        app = FastAPI()
        app.include_router(create_ci_workflow_router(settings(**kwargs)))
        return TestClient(app)

    def test_unconfigured_backend_says_so_instead_of_guessing(self):
        response = self.client(token='', repository='').get('/harness/ci-workflow')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['configured'], False)
        self.assertIn('未配置', response.json()['message'])

    def test_toggle_without_credentials_is_rejected(self):
        response = self.client(token='', repository='').post('/harness/ci-workflow', json={'enabled': False})

        self.assertEqual(response.status_code, 409)

    def test_toggle_calls_github_and_returns_state(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append((request.get_method(), request.full_url))
            payload = json.dumps({'state': 'disabled_manually'}).encode() if request.get_method() == 'GET' else b''
            return FakeResponse(payload)

        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            response = self.client().post('/harness/ci-workflow', json={'enabled': False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['enabled'], False)
        self.assertEqual(calls[0][:2], ('PUT', 'https://api.github.com/repos/owner/repo/actions/workflows/ci.yml/disable'))

    def test_github_failure_is_reported_as_bad_gateway(self):
        import urllib.error

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 404, 'not found', None, None)

        with patch('python_backend.infrastructure.github_workflow.urllib.request.urlopen', fake_urlopen):
            response = self.client().get('/harness/ci-workflow')

        self.assertEqual(response.status_code, 502)


if __name__ == '__main__':
    unittest.main()
