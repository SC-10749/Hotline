from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .routers.intent import create_intent_router


class IntentRouterTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(create_intent_router())
        self.client = TestClient(self.app)

    def test_catalogs_expose_both_scopes(self):
        payload = self.client.get('/intent/catalogs').json()
        scopes = {item['scope'] for item in payload['items']}
        self.assertEqual(scopes, {'action', 'retrieval'})
        for item in payload['items']:
            self.assertTrue(item['intents'])
            self.assertIn(item['default'], [intent['name'] for intent in item['intents']])

    def test_classify_reports_keyword_hit_without_a_model(self):
        response = self.client.post('/intent/classify',
                                    json={'query': '这份文档有多少条记录', 'scope': 'retrieval'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['intent'], 'text2sql')
        self.assertEqual(payload['source'], 'keyword')
        self.assertGreater(payload['confidence'], 0)

    def test_classify_falls_back_to_the_default_intent(self):
        payload = self.client.post('/intent/classify',
                                   json={'query': '随便聊聊', 'scope': 'action'}).json()
        self.assertEqual(payload['intent'], 'chat')
        self.assertEqual(payload['source'], 'default')

    def test_classify_uses_the_model_when_one_is_supplied(self):
        app = FastAPI()
        app.include_router(create_intent_router(
            lambda messages: '{"intent": "deep", "confidence": 0.93}'))
        client = TestClient(app)
        # 这句话不命中任何关键词，必须交给模型判定。
        payload = client.post('/intent/classify',
                              json={'query': '这个项目', 'scope': 'action'}).json()
        self.assertEqual(payload['intent'], 'deep')
        self.assertEqual(payload['source'], 'model')
        self.assertEqual(payload['tier'], 'high')
        self.assertFalse(payload['needsClarification'])

    def test_malformed_model_output_keeps_the_keyword_conclusion(self):
        app = FastAPI()
        app.include_router(create_intent_router(lambda messages: 'not json'))
        client = TestClient(app)
        payload = client.post('/intent/classify',
                              json={'query': '这份文档有多少条记录', 'scope': 'retrieval'}).json()
        self.assertEqual(payload['intent'], 'text2sql')
        self.assertEqual(payload['source'], 'keyword')

    def test_unknown_scope_uses_the_action_catalog(self):
        payload = self.client.post('/intent/classify',
                                   json={'query': '解释一下', 'scope': 'unknown'}).json()
        self.assertEqual(payload['scope'], 'action')


if __name__ == '__main__':
    unittest.main()