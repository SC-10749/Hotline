from __future__ import annotations

import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from .agents import AgentEngine


class AgentProgressTests(unittest.TestCase):
    def setUp(self):
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.storage.get_file.return_value = None
        self.storage.get_document.return_value = None
        tasks = Mock()
        tasks.register.side_effect = lambda _: threading.Event()
        settings = SimpleNamespace(model_api_key='', model_name='offline-model', tavily_api_key='')
        self.engine = AgentEngine(settings, self.storage, tasks)
        self.engine.model.stream = Mock(return_value=iter(['回答']))
        self.engine.model.chat = Mock(return_value='回答')

    def test_understanding_is_first_and_answer_progress_precedes_text(self):
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        self.assertEqual(events[0]['stage'], 'understanding')
        self.assertEqual(events[0]['status'], 'running')
        stages = [event for event in events if event['type'] == 'step']
        self.assertEqual([event['stage'] for event in stages], ['llm', 'llm'])
        answer_start = next(i for i, event in enumerate(events) if event.get('stage') == 'llm')
        text_start = next(i for i, event in enumerate(events) if event['type'] == 'text')
        self.assertLess(answer_start, text_start)
        self.assertEqual(stages[-1]['status'], 'completed')

    def test_document_progress_uses_filename_without_local_path(self):
        self.storage.get_file.return_value = SimpleNamespace(
            fileName='local-folder\\操作手册.pdf', embed=False, extractedText='文档内容')
        self.engine._search = Mock()
        events = list(self.engine.stream('file', 'conversation', 'question', 'file-id'))
        event = next(event for event in events if event.get('stage') == 'retrieval_request')
        self.assertEqual(event['content'], '正在检索《操作手册.pdf》')
        self.assertNotIn('local-folder', event['content'])
        self.engine._search.assert_not_called()

    def test_retrieval_progress_is_emitted_before_store_work(self):
        self.engine.vector_store = Mock()
        self.engine.vector_store.search_expanded.return_value = ['片段']
        events = self.engine._retrieve('file-id', 'question', 'semantic')
        first = next(events)
        self.assertEqual(first['status'], 'running')
        self.engine.vector_store.search_expanded.assert_not_called()
        rest = list(events)
        self.assertEqual(rest[-1]['status'], 'completed')
        self.assertEqual(rest[-1]['details']['hits'], 1)

    def test_search_progress_reports_titles_and_redacts_service_addresses(self):
        self.engine.settings.tavily_api_key = 'test-key-placeholder'
        self.engine._search = Mock(return_value=[{
            'title': '参考资料 http://docs.invalid/private', 'url': 'https://example.com', 'content': '资料内容',
        }])
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        steps = [event for event in events if event.get('stage') == 'web_search']
        self.assertEqual([event['status'] for event in steps], ['running', 'completed'])
        self.assertIn('[REDACTED]', steps[-1]['details']['documents'][0])
        self.assertNotIn('docs.invalid', json.dumps(steps))

    def test_optional_phases_are_not_invented(self):
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        stages = {event.get('stage') for event in events}
        self.assertNotIn('query_rewrite', stages)
        self.assertNotIn('web_search', stages)


if __name__ == '__main__':
    unittest.main()
