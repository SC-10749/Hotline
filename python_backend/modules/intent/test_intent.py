from __future__ import annotations

import unittest

from .catalog import ACTION_CATALOG, RETRIEVAL_CATALOG
from .clarify import (build_clarify_prompt, build_clarify_request, parse_clarify_reply)
from .classifier import parse_intent_sample
from .classifier import (AMBIGUOUS, CONFIDENT, build_prompt, classify, keyword_candidates,
                         merge_candidates, parse_intent_reply, score_keywords)
from .decision import (AMBIGUITY_GATE, DecisionClient, DecisionConfig, DecisionResult,
                       build_questions, parse_decision)
from . import (parse_retrieval_route, retrieval_candidates, retrieval_fallback,
               retrieval_messages, route_label)


class IntentCatalogTests(unittest.TestCase):
    def test_catalog_names_and_default_are_consistent(self):
        for catalog in (RETRIEVAL_CATALOG, ACTION_CATALOG):
            self.assertIn(catalog.default, catalog.names())
            self.assertEqual(len(set(catalog.names())), len(catalog.names()))

    def test_resolve_accepts_alias_case_and_separator_differences(self):
        self.assertEqual(RETRIEVAL_CATALOG.resolve('Semantic'), 'semantic')
        self.assertEqual(RETRIEVAL_CATALOG.resolve('text2sql'), 'text2sql')
        self.assertIsNone(RETRIEVAL_CATALOG.resolve('unknown-intent'))
        self.assertIsNone(RETRIEVAL_CATALOG.resolve(''))


class KeywordStageTests(unittest.TestCase):
    def test_score_keywords_ranks_hits_by_count(self):
        scored = score_keywords('这份文档有多少条记录，统计一下', RETRIEVAL_CATALOG)
        self.assertTrue(scored)
        self.assertEqual(scored[0][0], 'text2sql')
        self.assertGreaterEqual(scored[0][1], 2)

    def test_candidates_fall_back_to_default_when_nothing_matches(self):
        self.assertEqual(keyword_candidates('随便聊聊天气', RETRIEVAL_CATALOG), ('hybrid',))

    def test_candidates_are_capped(self):
        candidates = keyword_candidates('错误码 api 接口 字段 关系 依赖', RETRIEVAL_CATALOG)
        self.assertLessEqual(len(candidates), 3)


class ParseTests(unittest.TestCase):
    def test_parses_plain_json(self):
        parsed = parse_intent_reply('{"intent": "semantic", "confidence": 0.9}', RETRIEVAL_CATALOG)
        self.assertEqual(parsed, ('semantic', 0.9))

    def test_parses_fenced_json(self):
        parsed = parse_intent_reply('```json\n{"intent": "graph", "confidence": 0.8}\n```',
                                    RETRIEVAL_CATALOG)
        self.assertEqual(parsed, ('graph', 0.8))

    def test_rejects_unknown_intent_and_broken_json(self):
        self.assertIsNone(parse_intent_reply('{"intent": "nope"}', RETRIEVAL_CATALOG))
        self.assertIsNone(parse_intent_reply('not json', RETRIEVAL_CATALOG))
        self.assertIsNone(parse_intent_reply('', RETRIEVAL_CATALOG))

    def test_confidence_is_clamped(self):
        parsed = parse_intent_reply('{"intent": "semantic", "confidence": 7}', RETRIEVAL_CATALOG)
        self.assertEqual(parsed[1], 1.0)
        parsed = parse_intent_reply('{"intent": "semantic", "confidence": -3}', RETRIEVAL_CATALOG)
        self.assertEqual(parsed[1], 0.0)


class ClassifyTests(unittest.TestCase):
    def test_keyword_hit_skips_the_model(self):
        calls = []

        def chat(messages):
            calls.append(messages)
            return '{"intent": "semantic", "confidence": 0.9}'

        result = classify('这份文档有多少条记录，统计一下', RETRIEVAL_CATALOG, chat)
        self.assertEqual(result.source, 'keyword')
        self.assertEqual(result.intent, 'text2sql')
        self.assertEqual(calls, [])

    def test_ambiguous_input_falls_through_to_the_model(self):
        def chat(messages):
            return '{"intent": "semantic", "confidence": 0.92}'

        result = classify('解释一下这个', RETRIEVAL_CATALOG, chat)
        self.assertEqual(result.source, 'model')
        self.assertEqual(result.intent, 'semantic')
        self.assertEqual(result.tier, 'high')

    def test_model_failure_keeps_the_keyword_conclusion(self):
        def chat(messages):
            raise RuntimeError('model down')

        result = classify('这份文档有多少条记录，统计一下', RETRIEVAL_CATALOG, chat)
        self.assertEqual(result.source, 'keyword')
        self.assertEqual(result.intent, 'text2sql')

    def test_invalid_model_output_keeps_the_keyword_conclusion(self):
        result = classify('这份文档有多少条记录，统计一下', RETRIEVAL_CATALOG,
                          lambda messages: 'garbage')
        self.assertEqual(result.source, 'keyword')
        self.assertEqual(result.intent, 'text2sql')

    def test_model_failure_without_candidates_returns_default(self):
        def chat(messages):
            raise RuntimeError('model down')

        result = classify('这个项目', RETRIEVAL_CATALOG, chat)
        self.assertEqual(result.source, 'default')
        self.assertEqual(result.intent, RETRIEVAL_CATALOG.default)

    def test_no_model_available_uses_keyword_only(self):
        result = classify('这份文档有多少条记录', RETRIEVAL_CATALOG)
        self.assertEqual(result.source, 'keyword')
        self.assertEqual(result.intent, 'text2sql')

    def test_medium_confidence_asks_for_clarification(self):
        result = classify('这个项目', RETRIEVAL_CATALOG,
                          lambda messages: '{"intent": "semantic", "confidence": 0.5}')
        self.assertEqual(result.tier, 'medium')
        self.assertTrue(result.needs_clarification)

    def test_prompt_constrains_the_choice_to_candidates(self):
        messages = build_prompt('问题', RETRIEVAL_CATALOG, ('semantic', 'graph'))
        prompt = messages[-1]['content']
        self.assertIn('intent 必须取自这组候选：semantic、graph', prompt)

    def test_prompt_lists_the_whole_catalog_for_probabilities(self):
        prompt = build_prompt('问题', RETRIEVAL_CATALOG, ('semantic', 'graph'))[-1]['content']
        self.assertIn('text2sql', prompt)
        self.assertIn('probabilities', prompt)
        self.assertIn('confidence', prompt)


class CascadeTests(unittest.TestCase):
    """三级级联：关键词 → 向量召回 → 模型判定。"""

    class _FakeVectors:
        def __init__(self, names, score=0.5):
            self.names = names
            self.score = score
            self.calls = []

        def candidates(self, query, limit=3):
            self.calls.append(query)
            return tuple(self.names)

        def recall(self, query, limit=3):
            self.calls.append(query)
            return tuple((name, self.score) for name in self.names)

    def test_vector_candidates_are_merged_after_keyword_ones(self):
        vectors = self._FakeVectors(('semantic',))
        result = classify('这份文档有多少条记录', RETRIEVAL_CATALOG, vectors=vectors)
        self.assertEqual(result.candidates[0], 'text2sql')
        self.assertIn('semantic', result.candidates)

    def test_vector_layer_is_consulted_before_the_model(self):
        vectors = self._FakeVectors(('graph',))
        seen = {}

        def chat(messages):
            seen['prompt'] = messages[-1]['content']
            return '{"intent": "graph", "confidence": 0.88}'

        result = classify('这个项目', RETRIEVAL_CATALOG, chat, vectors=vectors)
        self.assertEqual(vectors.calls, ['这个项目'])
        self.assertIn('graph', seen['prompt'])
        self.assertEqual(result.intent, 'graph')
        self.assertEqual(result.source, 'model')

    def test_missing_vector_layer_leaves_the_chain_intact(self):
        result = classify('这份文档有多少条记录', RETRIEVAL_CATALOG)
        self.assertEqual(result.intent, 'text2sql')
        self.assertEqual(result.source, 'keyword')

    def test_merge_candidates_dedupes_and_keeps_order(self):
        merged = merge_candidates(('a', 'b'), ('b', 'c'), ())
        self.assertEqual(merged, ('a', 'b', 'c'))

    def test_merge_candidates_respects_the_limit(self):
        merged = merge_candidates(('a', 'b'), ('c', 'd'), limit=3)
        self.assertEqual(merged, ('a', 'b', 'c'))

    def test_longer_keyword_wins_a_tie(self):
        scored = score_keywords('把这份内容做成 PPT', ACTION_CATALOG)
        self.assertEqual(scored[0][0], 'ppt')
        self.assertEqual(scored[0][1], 1)

    def test_single_keyword_hit_is_not_decisive(self):
        result = classify('解释一下索引', ACTION_CATALOG,
                          lambda messages: '{"intent":"chat","confidence":0.9}')
        self.assertEqual(result.source, 'model')

    def test_vector_layer_decides_when_similarity_is_high(self):
        vectors = self._FakeVectors(('ppt',), score=0.97)
        result = classify('把这份内容做成 PPT', ACTION_CATALOG, vectors=vectors)
        self.assertEqual(result.source, 'vector')
        self.assertEqual(result.intent, 'ppt')
        self.assertAlmostEqual(result.confidence, 0.97)

    def test_sample_parses_confidence_and_distribution(self):
        parsed = parse_intent_sample(
            '{"intent":"chat","confidence":0.8,"probabilities":{"chat":3,"file":1}}',
            ACTION_CATALOG)
        self.assertEqual(parsed[0], 'chat')
        self.assertEqual(parsed[1], 0.8)
        self.assertEqual(parsed[2], {'chat': 0.75, 'file': 0.25})

    def test_sample_accepts_the_legacy_format(self):
        parsed = parse_intent_sample('{"intent":"chat","confidence":0.8}', ACTION_CATALOG)
        self.assertEqual(parsed[0], 'chat')
        self.assertEqual(parsed[1], 0.8)
        self.assertEqual(parsed[2], {'chat': 0.8})

    def test_sampling_averages_the_reported_confidence(self):
        replies = iter(['{"intent":"chat","confidence":0.9}',
                         '{"intent":"chat","confidence":0.6}',
                         '{"intent":"chat","confidence":0.3}'])
        result = classify('这个问题有点含糊', ACTION_CATALOG, lambda messages: next(replies))
        self.assertEqual(result.source, 'model')
        self.assertEqual(result.intent, 'chat')
        self.assertAlmostEqual(result.confidence, 0.6, places=3)

    def test_majority_vote_decides_the_intent(self):
        replies = iter(['{"intent":"chat","confidence":0.9}',
                         '{"intent":"deep","confidence":0.9}',
                         '{"intent":"chat","confidence":0.9}'])
        result = classify('这个问题有点含糊', ACTION_CATALOG, lambda messages: next(replies))
        self.assertEqual(result.intent, 'chat')

    def test_weak_vector_similarity_leaves_the_decision_to_the_model(self):
        vectors = self._FakeVectors(('deep',), score=0.5)
        result = classify('这个项目', ACTION_CATALOG,
                          lambda messages: '{"intent":"deep","confidence":0.88}',
                          vectors=vectors)
        self.assertEqual(result.source, 'model')
        self.assertEqual(result.intent, 'deep')


class RetrievalRouteTests(unittest.TestCase):
    def test_keyword_fallback_matches_historical_rules(self):
        self.assertEqual(retrieval_fallback('统计文档数量'), 'text2sql')
        self.assertEqual(retrieval_fallback('模块之间的依赖关系'), 'graph')
        self.assertEqual(retrieval_fallback('how many rows'), 'text2sql')
        self.assertEqual(retrieval_fallback('介绍一下这个项目'), 'hybrid')

    def test_route_labels_cover_every_route(self):
        for route in ('semantic', 'keyword', 'text2sql', 'graph', 'hybrid'):
            self.assertNotEqual(route_label(route), route)

    def test_parses_model_route_and_rejects_invalid(self):
        self.assertEqual(parse_retrieval_route('{"route": "text2sql"}'), 'text2sql')
        self.assertEqual(parse_retrieval_route('```json\n{"route": "graph"}\n```'), 'graph')
        self.assertIsNone(parse_retrieval_route('{"route": "unknown"}'))
        self.assertIsNone(parse_retrieval_route('garbage'))
        self.assertIsNone(parse_retrieval_route(''))

    def test_messages_ask_for_json_route(self):
        messages = retrieval_messages('问题')
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('"route"', messages[-1]['content'])

    def test_messages_restrict_the_choice_to_candidates(self):
        prompt = retrieval_messages('问题', ('text2sql', 'graph'))[-1]['content']
        self.assertIn('text2sql', prompt)
        self.assertIn('graph', prompt)
        self.assertNotIn('语义检索', prompt)

    def test_candidates_merge_keyword_and_vector_layers(self):
        class _FakeVectors:
            def candidates(self, query, limit=3):
                return ('semantic',)

        candidates = retrieval_candidates('统计文档数量', _FakeVectors())
        self.assertEqual(candidates[0], 'text2sql')
        self.assertIn('semantic', candidates)

    def test_candidates_without_a_vector_layer_are_keyword_only(self):
        self.assertEqual(retrieval_candidates('统计文档数量', None), ('text2sql',))


class ClarifyTests(unittest.TestCase):
    """需求澄清：三个方向 + 自由输入的口子。"""

    def test_parses_model_options(self):
        raw = '{"options":[{"intent":"deep","hint":"做一次深入调研"},{"intent":"chat","hint":"直接给个解释"}]}'
        parsed = parse_clarify_reply(raw, ACTION_CATALOG)
        self.assertEqual([item['intent'] for item in parsed], ['deep', 'chat'])
        self.assertEqual(parsed[0]['hint'], '做一次深入调研')

    def test_parses_fenced_json_and_drops_unknown_intents(self):
        raw = '```json\n{"options":[{"intent":"nope","hint":"x"},{"intent":"ppt","hint":"y"}]}\n```'
        parsed = parse_clarify_reply(raw, ACTION_CATALOG)
        self.assertEqual([item['intent'] for item in parsed], ['ppt'])

    def test_rejects_broken_payloads(self):
        self.assertEqual(parse_clarify_reply('garbage', ACTION_CATALOG), ())
        self.assertEqual(parse_clarify_reply('{"options":"x"}', ACTION_CATALOG), ())
        self.assertEqual(parse_clarify_reply('', ACTION_CATALOG), ())

    def test_request_always_offers_three_options(self):
        request = build_clarify_request('这个能聊聊吗', ACTION_CATALOG, ('chat',))
        self.assertEqual(len(request.options), 3)
        self.assertEqual(request.options[0].intent, 'chat')

    def test_model_options_are_used_when_valid(self):
        raw = ('{"options":[{"intent":"deep","hint":"深度调研"},{"intent":"ppt","hint":"做幻灯片"},'
               '{"intent":"chat","hint":"直接解释"}]}')
        request = build_clarify_request('这个能聊聊吗', ACTION_CATALOG, ('chat',), lambda messages: raw)
        self.assertEqual([item.intent for item in request.options], ['deep', 'ppt', 'chat'])
        self.assertEqual(request.options[0].hint, '深度调研')

    def test_model_failure_falls_back_to_catalog(self):
        def chat(messages):
            raise RuntimeError('model down')

        request = build_clarify_request('这个能聊聊吗', ACTION_CATALOG, ('chat',), chat)
        self.assertEqual(len(request.options), 3)
        self.assertEqual(request.options[0].label, ACTION_CATALOG.get('chat').label)

    def test_invalid_model_output_falls_back_to_catalog(self):
        request = build_clarify_request('这个能聊聊吗', ACTION_CATALOG, ('chat',),
                                        lambda messages: 'garbage')
        self.assertEqual(len(request.options), 3)

    def test_prompt_lists_candidates_and_catalog(self):
        prompt = build_clarify_prompt('问题', ACTION_CATALOG, ('chat',))[-1]['content']
        self.assertIn('chat', prompt)
        self.assertIn('deep', prompt)


class DecisionTests(unittest.TestCase):
    """决策层：System One 响应解析、提问构造与门闸衔接。"""

    def test_parses_choice_and_ambiguity(self):
        payload = {'answers': {'intent': {'type': 'choice', 'choice': 'ppt', 'confidence': 0.96},
                               'ambiguous': {'type': 'noul', 'noul': 0.42}}}
        result = parse_decision(payload, ACTION_CATALOG)
        self.assertEqual(result.intent, 'ppt')
        self.assertEqual(result.confidence, 0.96)
        self.assertEqual(result.ambiguity, 0.42)

    def test_rejects_unknown_intent_and_broken_payload(self):
        self.assertIsNone(parse_decision({'answers': {'intent': {'choice': 'nope'}}}, ACTION_CATALOG))
        self.assertIsNone(parse_decision({'answers': {}}, ACTION_CATALOG))
        self.assertIsNone(parse_decision({}, ACTION_CATALOG))
        self.assertIsNone(parse_decision('garbage', ACTION_CATALOG))

    def test_questions_cover_catalog_with_examples(self):
        questions = build_questions(ACTION_CATALOG)
        self.assertEqual(questions['intent']['type'], 'choice')
        self.assertEqual(questions['ambiguous']['type'], 'noul')
        self.assertEqual(set(questions['intent']['criteria']), set(ACTION_CATALOG.names()))
        self.assertIn('例如', questions['intent']['criteria']['ppt'])

    def test_client_without_config_returns_none(self):
        client = DecisionClient(DecisionConfig(base_url='', api_key=''))
        self.assertIsNone(client.judge('随便聊聊', ACTION_CATALOG))

    def test_client_rejects_blank_query(self):
        client = DecisionClient(DecisionConfig(base_url='https://example.invalid/v1', api_key='k'))
        self.assertIsNone(client.judge('   ', ACTION_CATALOG))


class DecisionGateTests(unittest.TestCase):
    """决策层结果驱动门闸：按歧义度而不是意图把握程度判断。"""

    def _decision(self, intent, confidence, ambiguity):
        def judge(query, catalog):
            return DecisionResult(intent, confidence, ambiguity)
        return judge

    def test_high_ambiguity_gates_even_with_high_intent_confidence(self):
        result = classify('你看着办', ACTION_CATALOG,
                          decision=self._decision('chat', 0.94, 0.91), gate=0.6)
        self.assertTrue(result.gated)
        self.assertEqual(result.source, 'decision')
        self.assertEqual(result.ambiguity, 0.91)

    def test_low_ambiguity_passes_even_with_low_intent_confidence(self):
        result = classify('解释一下索引的作用', ACTION_CATALOG,
                          decision=self._decision('chat', 0.3, 0.09), gate=0.6)
        self.assertFalse(result.gated)

    def test_decision_layer_takes_precedence_over_chat(self):
        calls = []

        def chat(messages):
            calls.append(messages)
            return '{"intent": "deep", "confidence": 0.9}'

        result = classify('你看着办', ACTION_CATALOG, chat,
                          decision=self._decision('chat', 0.9, 0.95), gate=0.6)
        self.assertEqual(result.intent, 'chat')
        self.assertEqual(calls, [])

    def test_unavailable_decision_falls_back_to_chat(self):
        result = classify('随便聊聊', ACTION_CATALOG,
                          lambda messages: '{"intent": "chat", "confidence": 0.9}',
                          decision=lambda query, catalog: None, gate=0.6)
        self.assertEqual(result.source, 'model')
        self.assertFalse(result.gated)


class GateTests(unittest.TestCase):
    """门闸：置信度不足时标记 gated，交由调用方转成澄清。"""

    def test_gate_marks_low_confidence(self):
        result = classify('随便聊聊', ACTION_CATALOG,
                          lambda messages: '{"intent":"chat","confidence":0.3}', gate=0.6)
        self.assertTrue(result.gated)
        self.assertTrue(result.needs_clarification)

    def test_gate_passes_high_confidence(self):
        result = classify('随便聊聊', ACTION_CATALOG,
                          lambda messages: '{"intent":"chat","confidence":0.9}', gate=0.6)
        self.assertFalse(result.gated)

    def test_without_gate_behaviour_is_unchanged(self):
        result = classify('随便聊聊', ACTION_CATALOG,
                          lambda messages: '{"intent":"chat","confidence":0.4}')
        self.assertFalse(result.gated)
        self.assertEqual(result.tier, 'medium')


if __name__ == '__main__':
    unittest.main()