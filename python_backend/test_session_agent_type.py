from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_backend.config import Settings
from python_backend.modules.execution.engine import TDD_RECOMMENDATION, AgentEngine
from python_backend.modules.storage.relational import Storage


def settings():
    return SimpleNamespace(model_api_key='key', model_base_url='http://model.test/v1',
                           model_name='model-x', tavily_api_key='')


class SessionAgentTypeTests(unittest.TestCase):
    """会话当前处在哪个助手类型：取最后一条消息，不是第一条。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='session-agent-type-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        config = replace(Settings(), data_dir=root, storage_backend='sqlite', redis_enabled=False,
                         vector_enabled=False, file_storage_backend='local', model_api_key='')
        self.storage = Storage(config)

    def test_session_list_reports_the_last_agent_type(self):
        first = self.storage.save_question('c1', '我要做一个请假系统', 'chat', None)
        self.storage.update_answer(first, '需求条目')
        last = self.storage.save_question('c1', TDD_RECOMMENDATION, 'skills', None)
        self.storage.update_answer(last, '测试清单')

        rows, _ = self.storage.session_list(0, 10)

        self.assertEqual(rows[0].agentType, 'skills')
        # 侧栏标题仍是会话的第一句话，不能被交接那轮改掉。
        self.assertEqual(rows[0].question, '我要做一个请假系统')


class TddHandoffCommandTests(unittest.TestCase):
    """交接口令由后端认定：前端没切模式时，这轮也要按技能流执行。"""

    def setUp(self):
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.context_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.storage.get_file.return_value = None
        self.storage.get_document.return_value = None
        self.tasks = Mock()
        self.tasks.register.side_effect = lambda _: threading.Event()
        self.skills = Mock()
        self.skills.open_resource_session.return_value = SimpleNamespace(
            read_skill=lambda *args: {}, descriptors=[])
        self.engine = AgentEngine(settings(), self.storage, self.tasks, skills=self.skills,
                                  persona_reader=lambda _: {'instruction': '', 'skills': [], 'style': ''})
        self.engine.model.chat = Mock(return_value='{"intent":"chat","confidence":0.95}')
        self.engine.model.stream = Mock(return_value=iter(['回答']))

    def test_handoff_command_runs_as_skill(self):
        with patch('python_backend.modules.execution.engine.run_agent') as runner:
            runner.return_value = iter([])
            list(self.engine.stream('chat', 'conversation', TDD_RECOMMENDATION))

        self.assertEqual(self.storage.save_question.call_args[0][2], 'skills')
        self.assertTrue(runner.called)

    def test_ordinary_question_stays_in_chat(self):
        list(self.engine.stream('chat', 'conversation', '做个请假系统'))

        self.assertEqual(self.storage.save_question.call_args[0][2], 'chat')


if __name__ == '__main__':
    unittest.main()
