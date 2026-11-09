"""第二层：向量召回。

用 embedding 模型把意图示例句编码，常驻内存后按余弦相似度为一次提问召回候选意图。
embedding 不可用（没配 key、接口不通、维度不一致）时，本层整体跳过，由关键词层兜底。
"""

from __future__ import annotations

import json
import math
import threading
import urllib.request
from dataclasses import dataclass

from .catalog import IntentCatalog
from ..context_engineering.privacy import sanitize_text

# 召回的相似度下限：低于它认为没有可用候选。
MIN_SIMILARITY = 0.45


@dataclass(frozen=True)
class VectorConfig:
    """embedding 接口配置。key 为空即视为不可用。"""

    api_key: str = ''
    base_url: str = ''
    model: str = ''
    dimension: int = 1024
    timeout: int = 30

    @property
    def usable(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


def embed_text(text: str, config: VectorConfig) -> list[float] | None:
    """调用 embedding 接口；任何失败都返回 None，不抛错。"""
    if not config.usable or not text.strip():
        return None
    endpoint = config.base_url.rstrip('/') + '/embeddings'
    request = urllib.request.Request(
        endpoint,
        data=json.dumps({'model': config.model, 'input': sanitize_text(text)}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {config.api_key}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        vector = payload['data'][0]['embedding']
    except Exception:
        return None
    if not isinstance(vector, list) or not vector:
        return None
    if len(vector) != config.dimension:
        return None
    return [float(value) for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    """余弦相似度。"""
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


class ExampleVectorStore:
    """意图示例句的向量缓存。

    示例句来自意图目录，首次使用时批量向量化并缓存到进程内存，
    之后每次查询只需 embedding 查询句再算余弦相似度。
    """

    def __init__(self, catalog: IntentCatalog, config: VectorConfig):
        self.catalog = catalog
        self.config = config
        self._lock = threading.Lock()
        self._vectors: dict[tuple[str, str], list[float]] = {}
        self._ready = False
        self._failed = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def available(self) -> bool:
        """本层是否可用：配置齐备且示例向量已就绪。"""
        return self.config.usable and self._ready and not self._failed

    def _example_texts(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for item in self.catalog.intents:
            for example in item.examples:
                pairs.append((item.name, example))
        return pairs

    def warmup(self) -> bool:
        """预先算好示例向量。失败则本层标记为不可用。"""
        if not self.config.usable:
            self._failed = True
            return False
        with self._lock:
            if self._ready:
                return True
            if self._failed:
                return False
            pairs = self._example_texts()
            vectors: dict[tuple[str, str], list[float]] = {}
            for name, example in pairs:
                vector = embed_text(example, self.config)
                if vector is None:
                    self._failed = True
                    return False
                vectors[(name, example)] = vector
            self._vectors = vectors
            self._ready = True
            return True

    def recall(self, query: str, limit: int = 3) -> list[tuple[str, float]]:
        """按余弦相似度召回候选意图，返回 [(意图名, 相似度)]。"""
        if not self.available and not self.warmup():
            return []
        query_vector = embed_text(query, self.config)
        if query_vector is None:
            return []
        best: dict[str, float] = {}
        for (name, _example), vector in self._vectors.items():
            score = cosine(query_vector, vector)
            if score >= MIN_SIMILARITY and score > best.get(name, 0.0):
                best[name] = score
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]

    def candidates(self, query: str, limit: int = 3) -> tuple[str, ...]:
        """召回的候选意图名；没有命中时返回空元组。"""
        return tuple(name for name, _ in self.recall(query, limit))
