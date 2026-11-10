from __future__ import annotations

import unittest
from unittest.mock import patch

from .catalog import ACTION_CATALOG, RETRIEVAL_CATALOG
from .retrieval import ExampleVectorStore, VectorConfig, cosine, embed_text


def _vector(index: int, dimension: int = 16) -> list[float]:
    """构造一组两两正交的向量，便于断言相似度顺序。"""
    vector = [0.0] * dimension
    vector[index % dimension] = 1.0
    return vector


class VectorConfigTests(unittest.TestCase):
    def test_config_without_key_is_not_usable(self):
        self.assertFalse(VectorConfig().usable)
        self.assertFalse(VectorConfig(api_key='k', base_url='', model='m').usable)
        self.assertTrue(VectorConfig(api_key='k', base_url='http://x', model='m').usable)


class CosineTests(unittest.TestCase):
    def test_identical_vectors_score_one(self):
        self.assertAlmostEqual(cosine([1.0, 2.0], [1.0, 2.0]), 1.0)

    def test_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_length_mismatch_scores_zero(self):
        self.assertEqual(cosine([1.0], [1.0, 2.0]), 0.0)

    def test_zero_vector_scores_zero(self):
        self.assertEqual(cosine([0.0, 0.0], [1.0, 2.0]), 0.0)


class EmbedTests(unittest.TestCase):
    def test_unconfigured_client_returns_none(self):
        self.assertIsNone(embed_text('任意文本', VectorConfig()))

    def test_blank_text_returns_none(self):
        config = VectorConfig(api_key='k', base_url='http://x', model='m')
        self.assertIsNone(embed_text('   ', config))

    def test_dimension_mismatch_is_rejected(self):
        payload = {'data': [{'embedding': [0.1, 0.2]}]}
        config = VectorConfig(api_key='k', base_url='http://x', model='m', dimension=4)

        class _Response:
            def read(self):
                return b'{}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch('urllib.request.urlopen', return_value=_Response()) as opener:
            import json
            opener.return_value.read = lambda: json.dumps(payload).encode()
            self.assertIsNone(embed_text('文本', config))

    def test_network_failure_returns_none(self):
        config = VectorConfig(api_key='k', base_url='http://127.0.0.1:9', model='m')
        self.assertIsNone(embed_text('文本', config))


class ExampleVectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.config = VectorConfig(api_key='k', base_url='http://x', model='m', dimension=16)

    def test_unavailable_store_recalls_nothing(self):
        store = ExampleVectorStore(RETRIEVAL_CATALOG, VectorConfig())
        self.assertEqual(store.candidates('任意问题'), ())
        self.assertFalse(store.available)

    def test_warmup_fails_without_configuration(self):
        store = ExampleVectorStore(RETRIEVAL_CATALOG, VectorConfig())
        self.assertFalse(store.warmup())
        self.assertFalse(store.ready)

    def test_recall_ranks_by_similarity(self):
        store = ExampleVectorStore(ACTION_CATALOG, self.config)
        # 每条示例句给一个互不相同的方向，查询句与第一条同向。
        examples = [example for item in ACTION_CATALOG.intents for example in item.examples]
        directions = {example: _vector(index) for index, example in enumerate(examples)}
        target = examples[0]

        def fake_embed(text, config):
            if text == target:
                return _vector(0)
            # 查询句与第一条示例同向；其余示例句各用不同方向。
            return directions.get(text, _vector(0))

        with patch('python_backend.modules.intent.retrieval.embed_text', side_effect=fake_embed):
            self.assertTrue(store.warmup())
            self.assertTrue(store.available)
            recalled = store.recall('查询')
        self.assertTrue(recalled)
        self.assertEqual(recalled[0][0], ACTION_CATALOG.intents[0].name)
        self.assertAlmostEqual(recalled[0][1], 1.0)
        self.assertEqual(len(recalled), 1)

    def test_similar_queries_below_the_floor_are_dropped(self):
        store = ExampleVectorStore(ACTION_CATALOG, self.config)
        examples = [example for item in ACTION_CATALOG.intents for example in item.examples]

        def fake_embed(text, config):
            return _vector(1)

        with patch('python_backend.modules.intent.retrieval.embed_text', side_effect=fake_embed):
            self.assertTrue(store.warmup())
            # 查询向量与示例向量正交，低于相似度下限，应被过滤掉。
            with patch('python_backend.modules.intent.retrieval.embed_text',
                       return_value=[0.0] * 15 + [1.0]):
                self.assertEqual(store.candidates('查询'), ())

    def test_embed_failure_marks_the_store_unavailable(self):
        store = ExampleVectorStore(ACTION_CATALOG, self.config)
        with patch('python_backend.modules.intent.retrieval.embed_text', return_value=None):
            self.assertFalse(store.warmup())
            self.assertFalse(store.available)
            self.assertEqual(store.candidates('查询'), ())


if __name__ == '__main__':
    unittest.main()