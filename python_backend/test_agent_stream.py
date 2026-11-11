from __future__ import annotations

import threading
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_backend.modules.execution.engine import AgentEngine, ModelClient


class FakeResponse:
    """模拟 urllib 的 HTTPResponse：既能整体读，也能按行迭代。"""

    def __init__(self, body: bytes, content_type: str):
        self.body = body
        self.headers = {'Content-Type': content_type}

    def read(self):
        return self.body

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def settings():
    return SimpleNamespace(model_api_key='key', model_base_url='http://model.test/v1',
                           model_name='model-x', tavily_api_key='')


SSE_BODY = (b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n'
            b'data: [DONE]\n\n')


class ModelStreamTests(unittest.TestCase):
    def test_read_stream_yields_each_delta(self):
        response = FakeResponse(SSE_BODY, 'text/event-stream; charset=utf-8')
        self.assertEqual(list(ModelClient(settings())._read_stream(response)), ['你', '好'])

    def test_stream_joins_pieces_and_records_usage(self):
        with patch('urllib.request.urlopen', return_value=FakeResponse(SSE_BODY, 'text/event-stream')) as opened:
            client = ModelClient(settings())
            pieces = list(client.stream([{'role': 'user', 'content': 'hi'}]))
        self.assertEqual(''.join(pieces), '你好')
        self.assertEqual(client.last_usage, {'inputTokens': 7, 'outputTokens': 3, 'totalTokens': 10})
        self.assertEqual(opened.call_count, 1)

    def test_stream_falls_back_when_upstream_ignores_stream_flag(self):
        body = b'{"choices":[{"message":{"content":"\xe4\xb8\x80\xe6\xac\xa1\xe6\x80\xa7"}}],"usage":{"total_tokens":4}}'
        with patch('urllib.request.urlopen', return_value=FakeResponse(body, 'application/json')):
            client = ModelClient(settings())
            pieces = list(client.stream([{'role': 'user', 'content': 'hi'}]))
        self.assertEqual(''.join(pieces), '一次性')
        self.assertEqual(client.last_usage['totalTokens'], 4)

    def test_stream_retries_without_stream_options_after_400(self):
        error = urllib.error.HTTPError('http://model.test/v1/chat/completions', 400, 'bad request', {}, None)
        with patch('urllib.request.urlopen', side_effect=[error, FakeResponse(SSE_BODY, 'text/event-stream')]) as opened:
            client = ModelClient(settings())
            pieces = list(client.stream([{'role': 'user', 'content': 'hi'}]))
        self.assertEqual(''.join(pieces), '你好')
        self.assertEqual(opened.call_count, 2)
        retry_payload = opened.call_args_list[1].args[0].data
        self.assertNotIn(b'stream_options', retry_payload)


class EngineStreamTests(unittest.TestCase):
    def setUp(self):
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.storage.get_file.return_value = None
        self.storage.get_document.return_value = None
        self.tasks = Mock()
        self.tasks.register.side_effect = lambda _: threading.Event()
        self.engine = AgentEngine(SimpleNamespace(model_api_key='', model_name='offline-model',
                                                  tavily_api_key=''), self.storage, self.tasks)
        self.engine.model.chat = Mock(return_value='answer')

    def test_engine_emits_text_incrementally(self):
        self.engine.model.stream = Mock(return_value=iter(['片段', 'A', 'B']))
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        self.assertEqual([event['content'] for event in events if event['type'] == 'text'],
                         ['片段', 'A', 'B'])

    def test_engine_falls_back_to_single_call_when_stream_is_empty(self):
        self.engine.model.stream = Mock(return_value=iter([]))
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        self.assertEqual([event['content'] for event in events if event['type'] == 'text'], ['answer'])
        self.engine.model.chat.assert_called_once()


if __name__ == '__main__':
    unittest.main()