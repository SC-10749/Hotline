"""Labelled recall set for the workspace keyword index.

The design document asks for recall to be measured on a labelled set instead of
tuned by feel (section 7.2: fact recall, identifiers, Chinese wording, and
similar distractors). This file is that set: a small workspace corpus with
deliberate distractors, the queries a user would really type, and the sources
that must come back for each query.

Run it directly to print the measured recall:

    python -m unittest python_backend.modules.retrieval.test_recall_quality -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .workspace_index import WorkspaceIndex

# One workspace, eight files, each split into two chunks.
CORPUS: dict[str, list[str]] = {
    'ops.md': [
        '华东区超时阈值为 30 秒，超过后进入降级模式，华东区不再单独告警。',
        '华东区值班表按周轮换，夜间由值班工程师兜底。',
    ],
    'billing.md': [
        '订单编号 ORD-2024-118 的结算金额是 1280 元。',
        '对账任务每日凌晨执行，失败会重试三次。',
    ],
    'deploy.md': [
        '发布使用 release 分支，回滚命令为 git revert。',
        '灰度批次默认 10%，观察 30 分钟后逐步放量。',
    ],
    'errors.md': [
        '错误码 ERR_404 表示资源不存在，前端应提示重试。',
        '错误码 ERR_500 表示服务端异常，需要上报。',
    ],
    'hr.md': [
        '员工每年享有 5 天带薪年假，申请需提前 3 个工作日。',
        '入职当月不享受年假，按自然折算。',
    ],
    'api.md': [
        '接口 /v1/orders 的分页参数是 page 与 size，默认值为 20，最大 100。',
        '接口 /v1/users 按创建时间倒序返回。',
    ],
    # Distractors: same wording, different subject.
    'office.md': ['华东区办公室位于上海，班车每天两班。'],
    'metrics.md': ['超时阈值的单位是毫秒，与运维文档口径不同。'],
}

# query -> sources that must come back for it.
QUERIES: list[tuple[str, set[str]]] = [
    ('华东区超时阈值是多少', {'ops.md'}),
    ('值班表怎么轮换', {'ops.md'}),
    ('ORD-2024-118', {'billing.md'}),
    ('对账任务什么时候执行', {'billing.md'}),
    ('回滚命令是什么', {'deploy.md'}),
    ('灰度批次默认多少', {'deploy.md'}),
    ('ERR_404', {'errors.md'}),
    ('错误码 ERR_500 表示什么', {'errors.md'}),
    ('带薪年假有几天', {'hr.md'}),
    ('年假申请需要提前几天', {'hr.md'}),
    ('分页参数默认值为多少', {'api.md'}),
    ('users 接口返回什么', {'api.md'}),
    # A two-character term: both files mention 华东, the denser one must lead.
    ('华东', {'ops.md', 'office.md'}),
]

PRODUCTION_LIMIT = 8
MEASURED_LIMIT = 20


class RecallQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.index = WorkspaceIndex(Path(self.temp.name) / 'index.db')
        for source, chunks in CORPUS.items():
            self.index.index_source('w1', source, chunks, 'fixture')

    def _sources(self, query: str, limit: int) -> list[str]:
        return [hit.split(chr(10))[0] for hit in self.index.search('w1', query, limit=limit)]

    def test_recall_on_the_labelled_set(self):
        missed: list[tuple[str, str]] = []
        wanted = 0
        for query, expected in QUERIES:
            sources = set(self._sources(query, MEASURED_LIMIT))
            for source in expected:
                wanted += 1
                if source not in sources:
                    missed.append((query, source))
        recall = 1 - len(missed) / wanted if wanted else 1.0
        self.assertGreaterEqual(recall, 0.95, f'missed={missed}')

    def test_recall_holds_at_the_production_limit(self):
        missed: list[tuple[str, str]] = []
        wanted = 0
        for query, expected in QUERIES:
            sources = set(self._sources(query, PRODUCTION_LIMIT))
            for source in expected:
                wanted += 1
                if source not in sources:
                    missed.append((query, source))
        recall = 1 - len(missed) / wanted if wanted else 1.0
        self.assertGreaterEqual(recall, 0.95, f'missed={missed}')

    def test_two_character_term_ranks_the_denser_match_first(self):
        sources = self._sources('华东', PRODUCTION_LIMIT)
        self.assertEqual(sources[0], 'ops.md')

    def test_workspace_scope_does_not_leak(self):
        self.index.index_source('w2', 'other.md', ['华东区超时阈值为 99 秒'], 'fixture')
        self.assertFalse(any('other.md' in hit for hit in self.index.search('w1', '华东区超时阈值')))


if __name__ == '__main__':
    unittest.main()
