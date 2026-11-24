from __future__ import annotations

import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_backend.models import SessionMessage
from python_backend.modules.execution.engine import (REQUIREMENT_FLAG, TDD_RECOMMENDATION,
                                                    TDD_SKILL, AgentEngine)
from python_backend.modules.skills.registry import Skill

CLEAR_REPLY = '{"clear":true}'
REQUIREMENT_BODY = 'FR-1 员工能提交一条请假申请，提交后能在「我的申请」里看到这条记录。'


def settings():
    return SimpleNamespace(model_api_key='key', model_base_url='http://model.test/v1',
                           model_name='model-x', tavily_api_key='')


def message(recommend: str) -> SessionMessage:
    return SessionMessage(id=1, conversationId='c', question='q', answer='a', thinking='',
                           tools='', reference=None, agentType='chat', fileid=None,
                           recommend=recommend, createTime='')


class TddHandoffTests(unittest.TestCase):
    """需求分析 → TDD 技能：推荐项带目标技能，需求正文随会话交接过去。"""

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
        self.skills.get.return_value = Skill(id='req-1', name='requirement-analysis',
                                             description='需求分析', entry='SKILL.md',
                                             sourceFile='仓库')
        self.skills.prompt_block.return_value = '技能正文'
        self.skills.open_resource_session.return_value = SimpleNamespace(
            read_skill=lambda *args: {}, descriptors=[])
        self.engine = AgentEngine(settings(), self.storage, self.tasks, skills=self.skills,
                                  persona_reader=lambda _: {'instruction': '', 'skills': ['req-1'],
                                                           'style': ''})
        self.engine.model.chat = Mock(return_value=CLEAR_REPLY)
        self.engine.model.stream = Mock(return_value=iter(['需求文档']))

    def test_recommendation_carries_the_target_skill(self):
        events = list(self.engine.stream('chat', 'conversation', '给客服做工单查询'))
        recommend = next(event['content'] for event in events if event['type'] == 'recommend')
        handoff = next(item for item in recommend if isinstance(item, dict))
        self.assertEqual(handoff['skill'], TDD_SKILL)
        self.assertIn('TDD', handoff['label'])

    def test_requirement_answer_is_marked_for_handoff(self):
        list(self.engine.stream('chat', 'conversation', '给客服做工单查询'))
        args = self.storage.update_answer.call_args[0]
        self.assertIn(REQUIREMENT_FLAG, args[2])

    def test_skill_run_receives_the_requirement_body(self):
        self.storage.session_messages.return_value = [
            SimpleNamespace(id=1, answer=REQUIREMENT_BODY, thinking=REQUIREMENT_FLAG,
                            question='做个请假系统')]
        with patch('python_backend.modules.execution.skill_flow.run_agent') as runner:
            runner.return_value = iter([])
            list(self.engine.stream('skills', 'conversation', '按 TDD 把这些需求写成测试'))
        prompt = runner.call_args[0][1]
        self.assertIn(REQUIREMENT_BODY, prompt)

    def test_skill_run_without_requirement_body_still_runs(self):
        with patch('python_backend.modules.execution.skill_flow.run_agent') as runner:
            runner.return_value = iter([])
            list(self.engine.stream('skills', 'conversation', '按 TDD 把这些需求写成测试'))
        prompt = runner.call_args[0][1]
        self.assertNotIn(REQUIREMENT_BODY, prompt)

    def test_draft_requirement_tells_the_skill_to_use_it(self):
        """交接的是未定稿草稿时，技能助手要基于草稿列未决点，而不是说没拿到需求。"""
        self.storage.session_messages.return_value = [
            SimpleNamespace(id=1, answer=REQUIREMENT_BODY, thinking=REQUIREMENT_FLAG,
                            question='做个请假系统')]
        with patch('python_backend.modules.execution.skill_flow.run_agent') as runner:
            runner.return_value = iter([])
            list(self.engine.stream('skills', 'conversation', '按 TDD 把这些需求写成测试'))
        prompt = runner.call_args[0][1]
        self.assertIn('未定稿', prompt)
        self.assertIn('不要说没有拿到需求', prompt)


class LegacyRecommendationTests(unittest.TestCase):
    """旧会话里的推荐项是字符串：读出来时要升级成结构化，点它才切得到技能助手。"""

    def test_legacy_string_recommendation_is_upgraded(self):
        data = message(json.dumps(['请进一步解释：做个工单系统', TDD_RECOMMENDATION],
                                  ensure_ascii=False)).to_dict()
        items = json.loads(data['recommend'])
        self.assertEqual(items[0], '请进一步解释：做个工单系统')
        self.assertEqual(items[1]['label'], TDD_RECOMMENDATION)
        self.assertEqual(items[1]['skill'], TDD_SKILL)

    def test_structured_recommendation_is_kept(self):
        payload = json.dumps([{'label': TDD_RECOMMENDATION, 'skill': TDD_SKILL}], ensure_ascii=False)
        data = message(payload).to_dict()
        self.assertEqual(json.loads(data['recommend']),
                         [{'label': TDD_RECOMMENDATION, 'skill': TDD_SKILL}])

    def test_unreadable_recommendation_is_kept_as_is(self):
        data = message('not json').to_dict()
        self.assertEqual(data['recommend'], 'not json')

    def test_missing_recommendation_stays_empty(self):
        self.assertEqual(message(None).to_dict()['recommend'], None)


if __name__ == '__main__':
    unittest.main()
