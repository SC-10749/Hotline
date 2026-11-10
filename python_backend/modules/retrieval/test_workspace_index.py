from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from ...agents import AgentEngine, TaskManager
from ...config import Settings
from ...storage import Storage
from ..context_engineering.service import ContextService
from ..memory.store import MemoryStore
from ..workspaces.context import recall_workspace
from .workspace_index import WorkspaceIndex


class WorkspaceIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = WorkspaceIndex(self.root / 'index.db')

    def test_chinese_phrase_is_recalled_by_trigram(self):
        self.index.index_source('w1', 'doc-a', ['华东区超时阈值是 30 秒'], 'm1')
        hits = self.index.search('w1', '超时阈值')
        self.assertTrue(any('30 秒' in hit for hit in hits))

    def test_two_character_chinese_is_recalled_by_bigram_phrase(self):
        self.index.index_source('w1', 'doc-a', ['华东区负责华东业务'], 'm1')
        hits = self.index.search('w1', '华东')
        self.assertTrue(any('负责华东业务' in hit for hit in hits))

    def test_two_character_chinese_prefers_the_denser_match(self):
        self.index.index_source('w1', 'doc-dense', ['华东区超时阈值 30 秒，华东区值班表'], 'm1')
        self.index.index_source('w1', 'doc-thin', ['华东区办公室在上海'], 'm1')
        hits = self.index.search('w1', '华东')
        self.assertTrue(hits[0].startswith('doc-dense'))

    def test_exact_identifier_is_recalled(self):
        self.index.index_source('w1', 'doc-a', ['项目编号 ALPHA123 的状态是完成'], 'm1')
        hits = self.index.search('w1', 'ALPHA123')
        self.assertTrue(any('ALPHA123' in hit for hit in hits))

    def test_single_character_chinese_falls_back_to_like(self):
        self.index.index_source('w1', 'doc-a', ['华东区负责华东业务'], 'm1')
        self.assertTrue(self.index.search('w1', '华'))

    def test_workspaces_are_isolated(self):
        self.index.index_source('w1', 'doc-a', ['机密内容 SECRET_ONE'], 'm1')
        self.index.index_source('w2', 'doc-b', ['机密内容 SECRET_TWO'], 'm1')
        self.assertFalse(any('SECRET_ONE' in hit for hit in self.index.search('w2', 'SECRET_ONE')))
        self.assertTrue(any('SECRET_TWO' in hit for hit in self.index.search('w2', 'SECRET_TWO')))

    def test_source_can_be_excluded(self):
        self.index.index_source('w1', 'doc-a', ['共同关键词出现在两份文档'], 'm1')
        self.index.index_source('w1', 'doc-b', ['共同关键词出现在两份文档'], 'm1')
        hits = self.index.search('w1', '共同关键词', exclude_source='doc-a')
        self.assertTrue(hits)
        self.assertFalse(any(hit.startswith('doc-a') for hit in hits))

    def test_reindex_replaces_previous_chunks(self):
        self.index.index_source('w1', 'doc-a', ['旧内容'], 'm1')
        self.index.index_source('w1', 'doc-a', ['新内容'], 'm2')
        self.assertFalse(self.index.search('w1', '旧内容'))
        self.assertTrue(self.index.search('w1', '新内容'))

    def test_layers_are_interleaved(self):
        self.index.index_source('w1', 'doc-exact', ['编号 ALPHA123'], 'm')
        self.index.index_source('w1', 'doc-cn', ['中文短语 华东区超时'], 'm')
        self.index.index_source('w1', 'doc-short', ['简称 华'], 'm')
        hits = self.index.search('w1', 'ALPHA123 华东区 华')
        sources = [hit.split('\n')[0] for hit in hits]
        self.assertEqual(sources[:3], ['doc-exact', 'doc-cn', 'doc-short'])

    def test_index_directory_indexes_text_files_only(self):
        root = self.root / 'ws'
        (root / 'docs').mkdir(parents=True)
        (root / 'docs' / 'a.md').write_text('华东区超时阈值 30 秒', encoding='utf-8')
        (root / 'node_modules').mkdir()
        (root / 'node_modules' / 'b.md').write_text('不该被索引 IGNORED_SENTINEL', encoding='utf-8')
        (root / 'bin.dat').write_bytes(b'\x00\x01binary')
        self.assertEqual(self.index.index_directory('w1', root), 1)
        self.assertTrue(self.index.search('w1', '华东区超时阈值'))
        self.assertFalse(self.index.search('w1', 'IGNORED_SENTINEL'))

    def test_unchanged_files_are_not_reindexed(self):
        root = self.root / 'ws'
        root.mkdir()
        (root / 'a.md').write_text('保留内容 KEEP_SENTINEL', encoding='utf-8')
        self.assertEqual(self.index.index_directory('w1', root), 1)
        self.assertEqual(self.index.index_directory('w1', root), 0)

    def test_index_directory_prunes_deleted_files(self):
        root = self.root / 'ws'
        root.mkdir()
        target = root / 'a.md'
        target.write_text('保留内容 KEEP_SENTINEL', encoding='utf-8')
        self.index.index_directory('w1', root)
        target.unlink()
        self.index.index_directory('w1', root)
        self.assertFalse(self.index.search('w1', 'KEEP_SENTINEL'))

    def test_edited_file_is_reindexed_on_the_next_sync(self):
        root = self.root / 'ws'
        root.mkdir()
        target = root / 'a.md'
        target.write_text('旧版本内容 OLD_SENTINEL', encoding='utf-8')
        self.index.index_directory('w1', root)
        target.write_text('新版本内容 NEW_SENTINEL', encoding='utf-8')
        self.index.index_directory('w1', root)
        self.assertFalse(self.index.search('w1', 'OLD_SENTINEL'))
        self.assertTrue(self.index.search('w1', 'NEW_SENTINEL'))

    def test_recall_workspace_uses_the_workspace_directory(self):
        root = self.root / 'ws'
        root.mkdir()
        (root / 'a.md').write_text('工作区里的 华东区超时阈值 是 30 秒', encoding='utf-8')
        resources = Mock()
        resources.get_workspace.return_value = {'repository': str(root)}
        resources.get_workspace_checkout.return_value = {'status': 'ready', 'checkout_dir': str(root)}
        result = recall_workspace(resources, Mock(), self.index, None, None, 'w1', '华东区超时阈值')
        self.assertTrue(any('30 秒' in hit for hit in result['hits']))
        self.assertTrue(any(hit.startswith('文件 a.md') for hit in result['hits']))
        self.assertEqual(result['documents'], [])

    def test_bound_document_becomes_a_workspace_candidate(self):
        store = Mock()
        store.get_document.return_value = None
        store.get_file.return_value = SimpleNamespace(fileName='手册.txt',
                                                      extractedText='华东区超时阈值是 30 秒')
        resources = Mock()
        resources.get_workspace.return_value = {'repository': str(self.root)}
        resources.get_workspace_checkout.return_value = None
        resources.resolve_local_repository.return_value = self.root
        result = recall_workspace(resources, store, self.index, None, None, 'w1', '华东区超时阈值', 'file-1')
        self.assertTrue(any('30 秒' in hit for hit in result['hits']))
        self.assertEqual(result['documents'], ['file-1'])


    def test_semantic_channel_uses_workspace_membership_not_lexical_hits(self):
        store = Mock()
        store.get_document.return_value = None
        store.get_file.return_value = SimpleNamespace(fileName='手册.txt',
                                                      extractedText='员工每年享有 5 天带薪年假')
        resources = Mock()
        resources.get_workspace.return_value = {'repository': str(self.root)}
        resources.get_workspace_checkout.return_value = None
        resources.resolve_local_repository.return_value = self.root
        vector_store = Mock()
        vector_store.document_chunks.return_value = ['员工每年享有 5 天带薪年假']
        vector_store.search_expanded_files.return_value = ['语义证据']
        result = recall_workspace(resources, store, self.index, vector_store, None, 'w1',
                                   '休假能休几天', 'doc-1')
        # 词面层一无所获，语义层仍按工作区成员关系检索。
        self.assertEqual(result['hits'], [])
        vector_store.search_expanded_files.assert_called_once_with(['doc-1'], '休假能休几天')
        self.assertIn('语义证据', result['semantic'])

    def test_file_vectors_rank_by_cosine(self):
        self.index.store_file_vector('w1', 'file:a.md', [1.0, 0.0], 'm')
        self.index.store_file_vector('w1', 'file:b.md', [0.0, 1.0], 'm')
        hits = self.index.search_files_by_vector('w1', [1.0, 0.1])
        self.assertEqual(hits[0][0], 'file:a.md')

    def test_embed_directory_stores_vectors_only_for_changed_files(self):
        root = self.root / 'ws'
        root.mkdir()
        (root / 'a.md').write_text('员工每年享有 5 天带薪年假', encoding='utf-8')
        calls = []

        def embed(texts):
            calls.append(list(texts))
            return [[1.0, 0.0] for _ in texts]

        self.assertEqual(self.index.embed_directory('w1', root, embed), 1)
        self.assertEqual(self.index.embed_directory('w1', root, embed), 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.index.search_files_by_vector('w1', [1.0, 0.0])[0][0], 'file:a.md')

    def test_semantic_file_hit_reaches_the_evidence(self):
        root = self.root / 'ws'
        root.mkdir()
        (root / 'hr.md').write_text('员工每年享有 5 天带薪年假', encoding='utf-8')
        resources = Mock()
        resources.get_workspace.return_value = {'repository': str(root)}
        resources.get_workspace_checkout.return_value = None
        resources.resolve_local_repository.return_value = root

        def embed(texts):
            return [[1.0, 0.0] for _ in texts]

        result = recall_workspace(resources, Mock(), self.index, None, embed, 'w1', '休假能休几天')
        self.assertEqual(result['hits'], [])
        self.assertTrue(any('带薪年假' in hit for hit in result['semantic']))


class WorkspaceRecallWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(data_dir=self.root, storage_backend='sqlite', redis_enabled=False,
                                 vector_enabled=False, file_storage_backend='local', model_api_key='',
                                 openviking_url='', context_enabled=True)
        self.service = ContextService(self.settings, store=MemoryStore(self.root / 'memory.db'))

    def _engine(self, workspace_recall):
        storage = Storage(self.settings)
        engine = AgentEngine(self.settings, storage, TaskManager(self.settings), context_service=self.service,
                              workspace_recall=workspace_recall)
        engine.model.stream = Mock(return_value=iter(['回答']))
        engine._search = Mock(return_value=[])
        return engine

    def test_chat_without_document_uses_workspace_evidence(self):
        engine = self._engine(lambda workspace_id, query, source_id='': {
            'hits': ['WORKSPACE_EVIDENCE_SENTINEL'], 'documents': []})
        events = list(engine.stream('chat', 'a', '华东区超时阈值是多少', workspace_id='work-a'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertIn('WORKSPACE_EVIDENCE_SENTINEL', repr(engine.model.stream.call_args.args[0]))

    def test_workspace_evidence_merges_the_semantic_channel(self):
        engine = self._engine(lambda workspace_id, query, source_id='': {
            'hits': ['WORKSPACE_EVIDENCE_SENTINEL'], 'documents': [], 'semantic': ['SEMANTIC_SENTINEL']})
        events = list(engine.stream('chat', 'a', '华东区超时阈值是多少', workspace_id='work-a'))
        self.assertEqual(events[-1]['type'], 'complete')
        prompt = repr(engine.model.stream.call_args.args[0])
        self.assertIn('WORKSPACE_EVIDENCE_SENTINEL', prompt)
        self.assertIn('SEMANTIC_SENTINEL', prompt)

    def test_workspace_evidence_is_fused_with_document_evidence(self):
        merged = AgentEngine._merge_hits(['文档证据'], ['工作区证据'], '证据')
        self.assertEqual(sorted(merged), ['工作区证据', '文档证据'])

    def test_without_workspace_recall_the_scope_stays_on_the_document(self):
        engine = self._engine(None)
        events = list(engine.stream('chat', 'a', '华东区超时阈值是多少', workspace_id='work-a'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertNotIn('WORKSPACE_EVIDENCE_SENTINEL', repr(engine.model.stream.call_args.args[0]))


if __name__ == '__main__':
    unittest.main()
