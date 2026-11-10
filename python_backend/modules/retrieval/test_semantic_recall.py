"""Semantic recall on synonym questions that share no wording with the target.

The keyword layers cannot answer a paraphrase that shares no character with the
source, so the workspace keeps its own vector channel. This file measures that
channel on a labelled set.

It needs a real embedding service, so it is skipped unless it is asked for:

    HOTLINE_SEMANTIC_EVAL=1 python -m unittest python_backend.modules.retrieval.test_semantic_recall -v

Every query below shares no fragment with the file it must reach, so a hit can
only come from the semantic channel.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from .workspace_index import WorkspaceIndex
from ..workspaces.context import recall_workspace

FILES: dict[str, str] = {
    'docs/hr.md': '员工每年享有 5 天带薪年假，申请需提前 3 个工作日。\n入职当月不享受年假，按自然折算。',
    'docs/ops.md': '华东区超时阈值为 30 秒，超过后进入降级模式，华东区不再单独告警。\n华东区值班表按周轮换，夜间由值班工程师兜底。',
    'docs/billing.md': '订单编号 ORD-2024-118 的结算金额是 1280 元。\n对账任务每日凌晨执行，失败会重试三次。',
    'docs/api.md': '接口 /v1/orders 的分页参数是 page 与 size，默认值为 20，最大 100。\n接口 /v1/users 按创建时间倒序返回。',
    'docs/office.md': '华东区办公室位于上海，班车每天两班。',
    'docs/metrics.md': '超时阈值的单位是毫秒，与运维文档口径不同。',
}

# query -> file that must be reached. No query shares a fragment with its target.
SYNONYMS: list[tuple[str, str]] = [
    ('休假能休几天', 'docs/hr.md'),
    ('新同事第一年能休多少天假', 'docs/hr.md'),
    ('钱什么时候算清楚', 'docs/billing.md'),
    ('结算出来的价格是多少钱', 'docs/billing.md'),
    ('一次能取多少条记录', 'docs/api.md'),
    ('响应时间上限是多少', 'docs/ops.md'),
    ('上班地点在哪儿', 'docs/office.md'),
]

SEMANTIC_TOP = 3


class _Resources:
    """Minimal stand-in for the resource store: the workspace is a directory."""

    def __init__(self, root: Path):
        self.root = root

    def get_workspace(self, workspace_id: str):
        return {'repository': str(self.root)}

    def get_workspace_checkout(self, workspace_id: str):
        return None

    def resolve_local_repository(self, repository: str):
        return Path(repository)


@unittest.skipUnless(os.getenv('HOTLINE_SEMANTIC_EVAL') == '1',
                     '需要真实 embedding 服务，设置 HOTLINE_SEMANTIC_EVAL=1 后运行')
class SemanticRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ...bootstrap import load_environment
        load_environment()
        from ...config import Settings
        from ...vector_store import PgVectorStore
        cls.settings = Settings()
        cls.vector_store = PgVectorStore(cls.settings)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, text in FILES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        self.index = WorkspaceIndex(self.root / 'workspace-index.db')
        self.resources = _Resources(self.root)

    def _recall(self, query: str):
        return recall_workspace(self.resources, None, self.index, None,
                                self.vector_store.embed_batch, 'w1', query)

    def test_synonym_questions_reach_the_right_file(self):
        missed: list[str] = []
        for query, expected in SYNONYMS:
            result = self._recall(query)
            files = {hit.split(chr(10))[0].replace('文件 docs/', '')
                     for hit in result['semantic'] if hit.startswith('文件')}
            if expected.replace('docs/', '') not in files:
                missed.append(f'{query} -> {expected} (got {sorted(files)})')
        self.assertEqual(missed, [], f'语义召回未命中: {missed}')

    def test_keyword_layers_alone_cannot_answer_them(self):
        """The same queries must not be answered by the keyword layers alone."""
        for query, _expected in SYNONYMS:
            self.assertEqual(self.index.search('w1', query), [],
                             f'{query} 不该被词面层命中，否则这条用例证明不了语义通道')

    def test_unrelated_questions_do_not_reach_a_file(self):
        result = self._recall('今天天气怎么样')
        self.assertEqual(result['semantic'], [])


if __name__ == '__main__':
    unittest.main()
