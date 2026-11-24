from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from python_backend.config import Settings
from python_backend.infrastructure.bot_store import BotStore
from python_backend.infrastructure.persona import BOT_DB_NAME
from python_backend.infrastructure.registry_store import RegistryStore
from python_backend.modules.execution.agent_tool import (AGENT_SOURCE, agent_tools_from_dir,
                                                         build_agent_tools)
from python_backend.modules.execution.engine import AgentEngine, TaskManager
from python_backend.modules.execution.tools import REGISTRY_DB_NAME, set_tool_policy

CLARIFY_PAYLOAD = {'question': '做个工单系统',
                    'options': [{'label': '客服工单', 'hint': '面向客户咨询投诉'},
                                {'label': '运维工单', 'hint': '面向内部报修'},
                                {'label': '任务工单', 'hint': '面向团队协作'}]}


def tool_schema(bot_id):
    return {'type': 'object',
            'properties': {'query': {'type': 'string'},
                           'clarification': {'type': 'string'}},
            'required': ['query'],
            'agent': {'bot_id': bot_id}}


class AgentToolTests(unittest.TestCase):
    """登记为 agent 的机器人能被装配成工具并按契约调用。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(set_tool_policy, None, False)
        self.registry = RegistryStore(self.root / REGISTRY_DB_NAME)
        self.bots = BotStore(self.root / BOT_DB_NAME)
        self.bot = self.bots.create({'name': '需求分析助手', 'instruction': '只做需求分析',
                                      'skills': ['skill-1'], 'enabled': True})
        self.registry.create_tool({
            'name': 'requirement_analysis', 'source': AGENT_SOURCE, 'scope': 'workspace',
            'risk': 'low', 'status': 'configured', 'description': '把需求变成可验收条目',
            'input_schema': tool_schema(self.bot['bot_id']), 'approval_policy': 'risk-based'})

    def tool(self, runner):
        tools = build_agent_tools(self.registry, self.bots, runner)
        return tools[0] if tools else None

    def test_registered_bot_becomes_a_tool(self):
        tool = self.tool(lambda persona, query, clarification: {'status': 'ok', 'summary': ''})
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, 'requirement_analysis')
        self.assertEqual(tool.description, '把需求变成可验收条目')
        self.assertIn('query', tool.args_schema.model_fields)

    def test_disabled_bot_is_not_mounted(self):
        self.bots.update(self.bot['bot_id'], {'enabled': False})
        self.assertIsNone(self.tool(lambda persona, query, clarification: {'status': 'ok'}))

    def test_tool_call_runs_the_agent_and_returns_json(self):
        seen = {}

        def runner(persona, query, clarification):
            seen.update({'persona': persona, 'query': query, 'clarification': clarification})
            return {'status': 'ok', 'summary': '需求文档'}

        tool = self.tool(runner)
        result = json.loads(tool.invoke({'query': '做个工单系统'}))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['summary'], '需求文档')
        self.assertEqual(seen['persona']['instruction'], '只做需求分析')
        self.assertEqual(seen['persona']['skills'], ['skill-1'])
        self.assertEqual(seen['query'], '做个工单系统')

    def test_clarification_answer_is_passed_through(self):
        seen = {}

        def runner(persona, query, clarification):
            seen['clarification'] = clarification
            return {'status': 'needs_clarification', 'summary': '', 'clarification': CLARIFY_PAYLOAD}

        tool = self.tool(runner)
        result = json.loads(tool.invoke({'query': '做个工单系统', 'clarification': '客服工单'}))
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertEqual(result['clarification']['options'][0]['label'], '客服工单')
        self.assertEqual(seen['clarification'], '客服工单')

    def test_tool_call_is_blocked_by_the_allow_list(self):
        set_tool_policy(['read_skill'])
        tool = self.tool(lambda persona, query, clarification: {'status': 'ok'})
        with self.assertRaises(ValueError):
            tool.invoke({'query': '做个工单系统'})

    def test_agent_tools_are_read_from_the_data_directory(self):
        tools = agent_tools_from_dir(self.root, lambda persona, query, clarification: {'status': 'ok'})
        self.assertEqual([tool.name for tool in tools], ['requirement_analysis'])


class AgentRunnerTests(unittest.TestCase):
    """引擎侧的 Agent 工具执行器：澄清不阻塞，产出按上限截断。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        settings = replace(Settings(), data_dir=self.root, skills_dir=self.root / 'skills',
                            context_enabled=False)
        settings.ensure_dirs()
        self.engine = AgentEngine(settings, None, TaskManager(settings))

    def test_clarification_is_returned_instead_of_blocking(self):
        def fake_fallback(*args, **kwargs):
            yield {'type': 'clarify', 'content': CLARIFY_PAYLOAD}

        self.engine._fallback = fake_fallback
        result = self.engine._run_agent_tool({'instruction': '', 'skills': [], 'style': ''},
                                              '做个工单系统', '')
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertEqual(result['clarification']['options'][1]['label'], '运维工单')

    def test_answer_is_returned_as_summary(self):
        def fake_fallback(*args, **kwargs):
            yield {'type': 'step', 'content': '正在回答'}
            return ('需求文档', [], False)

        self.engine._fallback = fake_fallback
        result = self.engine._run_agent_tool({'instruction': '', 'skills': [], 'style': ''},
                                              '做个工单系统', '')
        self.assertEqual(result, {'status': 'ok', 'summary': '需求文档'})

    def test_long_answer_is_truncated(self):
        def fake_fallback(*args, **kwargs):
            yield {'type': 'step', 'content': '正在回答'}
            return ('长' * 5000, [], False)

        self.engine._fallback = fake_fallback
        result = self.engine._run_agent_tool({'instruction': '', 'skills': [], 'style': ''},
                                              '做个工单系统', '')
        self.assertTrue(result['summary'].endswith('…（已截断）'))
        self.assertLess(len(result['summary']), 5000)

    def test_clarification_answer_is_composed_into_the_question(self):
        seen = {}

        def fake_fallback(agent, query, file_id=None, history=None, **kwargs):
            seen.update({'query': query, 'clarified': kwargs.get('clarified')})
            yield {'type': 'step', 'content': '正在回答'}
            return ('需求文档', [], False)

        self.engine._fallback = fake_fallback
        self.engine._run_agent_tool({'instruction': '', 'skills': [], 'style': ''},
                                    '做个工单系统', '客服工单')
        self.assertIn('原问题：做个工单系统', seen['query'])
        self.assertIn('我想要的是：客服工单', seen['query'])
        self.assertTrue(seen['clarified'])


if __name__ == '__main__':
    unittest.main()
