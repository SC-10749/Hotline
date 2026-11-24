from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from python_backend.config import Settings
from python_backend.infrastructure.bot_store import BotStore
from python_backend.infrastructure.persona import load_persona
from python_backend.modules.execution.engine import (CLARIFY_FLAG, TDD_RECOMMENDATION,
                                                    TDD_SKILL, AgentEngine)
from python_backend.modules.intent.requirement import build_requirement_prompt
from python_backend.modules.skills.registry import Skill, SkillRegistry

UNCLEAR_REPLY = ('{"clear":false,"options":['
                 '{"label":"客服内部工单流转","hint":"面向客服建单、跟进与归档"},'
                 '{"label":"客户自助报修","hint":"面向客户提交与查询进度"},'
                 '{"label":"工单数据分析","hint":"已有工单数据的统计与看板"}]}')
CLEAR_REPLY = '{"clear":true}'


def settings():
    return SimpleNamespace(model_api_key='key', model_base_url='http://model.test/v1',
                           model_name='model-x', tavily_api_key='')


class RequirementGateTests(unittest.TestCase):
    """需求分析机器人：需求说不清时先给三个理解方向，说得清就直接产出。"""

    def setUp(self):
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
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
        self.engine = AgentEngine(settings(), self.storage, self.tasks, skills=self.skills,
                                  persona_reader=lambda _: {'instruction': '', 'skills': ['req-1'],
                                                           'style': ''})
        self.reply = UNCLEAR_REPLY
        self.engine.model.chat = Mock(side_effect=self.chat)
        self.engine.model.stream = Mock(return_value=iter(['需求文档']))

    def chat(self, messages):
        if any('准入检查员' in item.get('content', '') for item in messages):
            return self.reply
        return '{"intent":"chat","confidence":0.95}'

    def test_unclear_requirement_asks_for_clarification(self):
        events = list(self.engine.stream('chat', 'conversation', '做个工单系统'))
        types = [event['type'] for event in events]
        self.assertIn('clarify', types)
        self.assertNotIn('text', types)
        payload = next(event['content'] for event in events if event['type'] == 'clarify')
        self.assertEqual(payload['question'], '做个工单系统')
        self.assertEqual(len(payload['options']), 3)
        self.assertEqual(payload['options'][0]['label'], '客服内部工单流转')
        self.assertEqual(payload['options'][0]['hint'], '面向客服建单、跟进与归档')

    def test_gated_turn_is_recorded_as_pending_clarification(self):
        list(self.engine.stream('chat', 'conversation', '做个工单系统'))
        args = self.storage.update_answer.call_args[0]
        self.assertEqual(args[1], '')
        self.assertEqual(args[2], CLARIFY_FLAG)

    def test_clear_requirement_answers_without_clarification(self):
        self.reply = CLEAR_REPLY
        events = list(self.engine.stream('chat', 'conversation', '给客服做工单查询，按工单号精确查'))
        types = [event['type'] for event in events]
        self.assertNotIn('clarify', types)
        self.assertIn('text', types)

    def test_requirement_mode_skips_the_intent_gate(self):
        self.reply = CLEAR_REPLY
        list(self.engine.stream('chat', 'conversation', '给客服做工单查询'))
        self.assertEqual(self.engine.model.chat.call_count, 1)

    def test_clarification_answer_is_not_gated_again(self):
        previous = SimpleNamespace(id=1, answer='', thinking=CLARIFY_FLAG, question='做个工单系统')
        self.storage.session_messages.return_value = [previous]
        events = list(self.engine.stream('chat', 'conversation',
                                         '原问题：做个工单系统\n我想要的是：客服内部工单流转'))
        self.assertNotIn('clarify', [event['type'] for event in events])

    def test_gate_prompt_tells_the_model_not_to_reclarify_answers(self):
        prompt = build_requirement_prompt('第 1 轮回答：漏单主要指没人认领', '助手：上一轮问了三个问题')
        self.assertIn('回答那些问题', prompt[-1]['content'])
        self.assertIn('不要重复澄清', prompt[-1]['content'])

    def test_tdd_recommendation_appears_as_soon_as_requirement_mode_starts(self):
        self.reply = CLEAR_REPLY
        events = list(self.engine.stream('chat', 'conversation', '给客服做工单查询'))
        recommend = next(event['content'] for event in events if event['type'] == 'recommend')
        handoff = next(item for item in recommend if isinstance(item, dict))
        self.assertEqual(handoff['skill'], TDD_SKILL)
        self.assertEqual(handoff['label'], TDD_RECOMMENDATION)

    def test_no_tdd_recommendation_for_other_bots(self):
        self.skills.get.return_value = Skill(id='other-1', name='hotline-tdd', description='开发流程',
                                              entry='SKILL.md', sourceFile='仓库')
        self.reply = CLEAR_REPLY
        events = list(self.engine.stream('chat', 'conversation', '给客服做工单查询'))
        recommend = next(event['content'] for event in events if event['type'] == 'recommend')
        self.assertFalse([item for item in recommend if isinstance(item, dict)])

    def test_model_failure_does_not_block_the_answer(self):
        self.reply = '不是 JSON'
        events = list(self.engine.stream('chat', 'conversation', '做个工单系统'))
        self.assertNotIn('clarify', [event['type'] for event in events])

    def test_missing_directions_fall_back_to_three_dimensions(self):
        self.reply = '{"clear":false}'
        events = list(self.engine.stream('chat', 'conversation', '做个工单系统'))
        payload = next(event['content'] for event in events if event['type'] == 'clarify')
        self.assertEqual(len(payload['options']), 3)
        self.assertEqual(payload['options'][0]['label'], '谁在用这个功能')

    def test_other_bots_keep_the_intent_gate(self):
        self.skills.get.return_value = Skill(id='other-1', name='hotline-tdd', description='开发流程',
                                              entry='SKILL.md', sourceFile='仓库')
        self.engine.model.chat = Mock(return_value='{"intent":"chat","confidence":0.2}')
        events = list(self.engine.stream('chat', 'conversation', '随便聊聊'))
        self.assertIn('clarify', [event['type'] for event in events])




class RequirementBotTests(unittest.TestCase):
    """机器人绑定需求分析技能后，会话进入需求澄清而不是通用意图门闸。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='requirement-bot-'))
        self.addCleanup(shutil.rmtree, self.root, True)
        config = replace(Settings(), data_dir=self.root, skills_dir=self.root / 'skills',
                         repo_skills_dir=Path(__file__).resolve().parents[1] / 'skills',
                         skill_catalog_db=self.root / 'catalog.db')
        config.ensure_dirs()
        self.registry = SkillRegistry(config)
        skill = self.registry.install_from_dir(config.repo_skills_dir / 'requirement-analysis')
        store = BotStore(self.root / 'harness-bots.db')
        bot = store.create({'name': '需求分析助手', 'instruction': '只做需求分析',
                            'skills': [skill.id], 'enabled': True})
        store.bind_session('conversation', bot['bot_id'])
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.tasks = Mock()
        self.tasks.register.side_effect = lambda _: threading.Event()
        self.engine = AgentEngine(settings(), self.storage, self.tasks, skills=self.registry,
                                  persona_reader=lambda cid: load_persona(self.root, cid))
        self.engine.model.chat = Mock(return_value=UNCLEAR_REPLY)
        self.engine.model.stream = Mock(return_value=iter(['需求文档']))

    def test_bound_skill_switches_engine_into_requirement_mode(self):
        persona = load_persona(self.root, 'conversation')
        self.assertEqual(len(persona['skills']), 1)
        self.assertTrue(self.engine._requirement_mode(persona))

    def test_unclear_requirement_produces_clarify_event(self):
        events = list(self.engine.stream('chat', 'conversation', '做个工单系统'))
        payload = next(event['content'] for event in events if event['type'] == 'clarify')
        self.assertEqual(len(payload['options']), 3)

    def test_disabled_bot_falls_back_to_the_intent_gate(self):
        store = BotStore(self.root / 'harness-bots.db')
        bot = store.list()[0]
        store.update(bot['bot_id'], {'enabled': False})
        self.engine.model.chat = Mock(return_value='{"intent":"chat","confidence":0.2}')
        events = list(self.engine.stream('chat', 'conversation', '随便聊聊'))
        self.assertIn('clarify', [event['type'] for event in events])


if __name__ == '__main__':
    unittest.main()
