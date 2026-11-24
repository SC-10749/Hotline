"""批量嵌入与向量库批量写入的行为测试。

要点：一次 HTTP 请求算一批，而不是一块一次；批次失败要退回逐条，
保证与改造前的结果一致。
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from .retrieval import VectorConfig, embed_texts


class _Response:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class EmbedTextsTests(unittest.TestCase):
    def setUp(self):
        self.config = VectorConfig(api_key="k", base_url="http://x", model="m", dimension=2)

    def test_unconfigured_client_returns_none(self):
        self.assertIsNone(embed_texts(["a", "b"], VectorConfig()))

    def test_blank_texts_are_dropped(self):
        self.assertIsNone(embed_texts(["  ", ""], self.config))

    def test_batch_returns_one_vector_per_text(self):
        payload = {"data": [{"index": 1, "embedding": [0.0, 1.0]},
                            {"index": 0, "embedding": [1.0, 0.0]}]}

        with patch("urllib.request.urlopen",
                   return_value=_Response(json.dumps(payload).encode())):
            vectors = embed_texts(["甲", "乙"], self.config)
        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])

    def test_dimension_mismatch_returns_none(self):
        payload = {"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]}
        with patch("urllib.request.urlopen",
                   return_value=_Response(json.dumps(payload).encode())):
            self.assertIsNone(embed_texts(["甲"], self.config))

    def test_network_failure_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertIsNone(embed_texts(["甲"], self.config))

    def test_missing_index_returns_none(self):
        payload = {"data": [{"embedding": [1.0, 0.0]}]}
        with patch("urllib.request.urlopen",
                   return_value=_Response(json.dumps(payload).encode())):
            self.assertIsNone(embed_texts(["甲"], self.config))


if __name__ == "__main__":
    unittest.main()
