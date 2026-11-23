"""MCP 工具调用必须过人工审批。

对应规格 S-013。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.mcp import create_mcp_router
from ...infrastructure.governance_store import GovernanceStore
from ...infrastructure.registry_store import RegistryStore

FAKE_TOOL_SERVER = """
import json
import sys

TOOLS = [{'name': 'echo', 'description': '回显文本',
          'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                          'required': ['text']}}]

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        request = json.loads(line)
    except Exception:
        continue
    method = request.get('method')
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake-mcp', 'version': '1.0'}}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        arguments = (request.get('params') or {}).get('arguments') or {}
        result = {'content': [{'type': 'text', 'text': 'echo:' + str(arguments.get('text', ''))}],
                  'isError': False}
    else:
        result = {}
    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}) + chr(10))
    sys.stdout.flush()
"""


class McpApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        script = self.root / 'server.py'
        script.write_text(FAKE_TOOL_SERVER, encoding='utf-8')
        self.registry = RegistryStore(self.root / 'registry.db')
        self.governance = GovernanceStore(self.root / 'governance.db')
        app = FastAPI()
        app.include_router(create_mcp_router(self.registry, self.governance))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def register_server(self, approval_policy='risk-based', risk='high'):
        return self.registry.create_tool({
            'name': 'mcp-echo', 'source': 'mcp', 'scope': 'workspace', 'risk': risk,
            'status': 'configured', 'description': '回显',
            'input_schema': {'type': 'object', 'properties': {},
                             'mcp': {'command': sys.executable, 'args': [str(self.root / 'server.py')]}},
            'approval_policy': approval_policy,
        })

    def call(self, tool_id):
        return self.client.post(f'/harness/mcp/servers/{tool_id}/tools/echo/call',
                                json={'arguments': {'text': 'hi'}})

    def test_high_risk_call_is_rejected_and_creates_an_approval_request(self):
        tool = self.register_server()
        response = self.call(tool['tool_id'])
        self.assertEqual(response.status_code, 409)
        pending = self.governance.list('pending')
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['tool'], f"mcp:{tool['tool_id']}:echo")
        self.assertIn(pending[0]['request_id'], response.json()['detail'])

    def test_approved_call_goes_through(self):
        tool = self.register_server()
        self.assertEqual(self.call(tool['tool_id']).status_code, 409)
        request = self.governance.list('pending')[0]
        self.governance.decide(request['request_id'], 'approved', operator='tester')
        response = self.call(tool['tool_id'])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    def test_always_policy_also_requires_approval(self):
        tool = self.register_server(approval_policy='always')
        self.assertEqual(self.call(tool['tool_id']).status_code, 409)

    def test_low_risk_call_runs_without_approval(self):
        tool = self.register_server(risk='low')
        response = self.call(tool['tool_id'])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(self.governance.list('pending'), [])
