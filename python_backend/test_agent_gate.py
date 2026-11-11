from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from python_backend.modules.execution.engine import CLARIFY_FLAG, AgentEngine


def settings():
    return SimpleNamespace(model_api_key='key', model_base_url='http://model.test/v1',
                           model_name='model-x', tavily_api_key='')


CLARIFY_REPLY = ('{"options":[{"intent":"deep","hint":"做一次深入调研"},'
                 '{"intent":"ppt","hint":"整理成演示文稿"},'
                 '{"intent":"chat","hint":"直接给个解释"}]}')


class IntentGateTests(unittest.TestCase):
    """门闸在澄清作答后重新判定当前诉求。"""

    def setUp(self):
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.storage.get_file.return_value = None
        self.storage.get_document.return_value = None
        self.tasks = Mock()
        self.tasks.register.side_effect = lambda _: threading.Event()
        self.engine = AgentEngine(settings(), self.storage, self.tasks)
        self.engine.model.chat = Mock(side_effect=self.chat)
        self.engine.model.stream = Mock(return_value=iter(['答案']))

    def chat(self, messages):
        prompt = messages[-1]['content']
        if '理解方向' in prompt:
            return CLARIFY_REPLY
        return '{"intent":"chat","confidence":0.2}'

    def test_low_confidence_asks_for_clarification(self):
        events = list(self.engine.stream('chat', 'conversation', '随便聊聊'))
        types = [event['type'] for event in events]
        self.assertIn('clarify', types)
        self.assertNotIn('recommend', types)
        self.assertNotIn('text', types)
        self.assertIn('complete', types)
        payload = next(event['content'] for event in events if event['type'] == 'clarify')
        self.assertEqual(payload['question'], '随便聊聊')
        self.assertEqual(len(payload['options']), 3)
        self.assertEqual(payload['options'][0]['label'], '深度研究')

    def test_gated_turn_is_recorded_as_pending_clarification(self):
        list(self.engine.stream('chat', 'conversation', '随便聊聊'))
        args = self.storage.update_answer.call_args[0]
        self.assertEqual(args[1], '')
        self.assertEqual(args[2], CLARIFY_FLAG)

    def test_clarification_answer_is_classified_again(self):
        previous = SimpleNamespace(id=1, answer='', thinking=CLARIFY_FLAG, question='随便聊聊')
        self.storage.session_messages.return_value = [previous]
        self.engine.model.chat = Mock(return_value='{"intent":"deep","confidence":0.95}')
        events = list(self.engine.stream('chat', 'conversation',
                                         '原问题：随便聊聊\n我想要的是：深度调研'))
        types = [event['type'] for event in events]
        self.assertNotIn('clarify', types)
        self.assertIn('text', types)
        self.assertTrue(self.engine.model.chat.called)

    def test_ambiguous_clarification_answer_can_request_more_detail(self):
        previous = SimpleNamespace(id=1, answer='', thinking=CLARIFY_FLAG, question='随便聊聊')
        self.storage.session_messages.return_value = [previous]
        events = list(self.engine.stream('chat', 'conversation', '还是随便'))
        self.assertIn('clarify', [event['type'] for event in events])

    def test_clear_question_answers_directly(self):
        self.engine.model.chat = Mock(return_value='{"intent":"chat","confidence":0.95}')
        events = list(self.engine.stream('chat', 'conversation', '解释一下这个'))
        types = [event['type'] for event in events]
        self.assertNotIn('clarify', types)
        self.assertIn('text', types)

    def test_file_question_is_never_clarified(self):
        self.storage.conversation_file_id.return_value = 'file-1'
        events = list(self.engine.stream('file', 'conversation', '随便聊聊'))
        types = [event['type'] for event in events]
        self.assertNotIn('clarify', types)


if __name__ == '__main__':
    unittest.main()
