from __future__ import annotations

import json
from pathlib import Path

from ..context_engineering.privacy import private_path
from ..retrieval.layers import GLOBAL_QUERY

# A file matched by the semantic channel is shown to the model up to this size.
_SEMANTIC_FILE_CHARS = 6000
_SEMANTIC_FILES = 3


def resolve_workspace_root(store, workspace_id: str) -> Path | None:
    """工作区文件根目录：优先受管检出目录，其次本地仓库。"""
    if not workspace_id:
        return None
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        return None
    checkout = store.get_workspace_checkout(workspace_id)
    if checkout and checkout.get('status') == 'ready':
        return Path(checkout['checkout_dir']).resolve()
    return store.resolve_local_repository(workspace['repository'])


def load_workspace_rules(store, workspace_id: str) -> str:
    if not workspace_id:
        return ''
    if not store.get_workspace(workspace_id):
        raise ValueError('工作区不存在')
    root = resolve_workspace_root(store, workspace_id)
    if root is None:
        return ''
    rules = Path(root) / 'AGENTS.md'
    if not rules.is_file() or rules.is_symlink():
        return ''
    if rules.stat().st_size > 64000:
        raise ValueError('工作区规则超过读取上限，请精简规则或调整工作区')
    return rules.read_text(encoding='utf-8-sig')


def recall_workspace(resources, storage, index, vector_store, embed, workspace_id: str, query: str,
                     source_id: str = '', limit: int = 8) -> dict:
    """工作区级召回：词面分层命中，加上不依赖词面候选的语义命中。

    工作区文件每次按内容标记增量同步；本轮用到的文档挂进该工作区的索引，
    于是同一工作区里用过的文档也能被词面层召回。语义通道按工作区成员关系
    取候选（该工作区用过的文档、该工作区的文件），不依赖这次查询命中了什么，
    所以没有共同词片段的同义问法也能召回。

    返回 hits（词面证据）、documents（该工作区的文档 ID）与 semantic（语义证据）。
    """
    if not workspace_id or not (query or '').strip():
        return {'hits': [], 'documents': [], 'semantic': []}
    root = resolve_workspace_root(resources, workspace_id)
    if root is not None and Path(root).is_dir():
        index.index_directory(workspace_id, Path(root))
        index.embed_directory(workspace_id, Path(root), embed)
    if source_id:
        bind_document(storage, index, vector_store, workspace_id, source_id)
    pairs = index.search_sources(workspace_id, query, limit=limit)
    hits = []
    if GLOBAL_QUERY.search(query):
        hits.append('工作区目录覆盖清单\n' + json.dumps(index.overview(workspace_id), ensure_ascii=False))
    for source, content in pairs:
        layer = index.read_source(workspace_id, source, level='overview')
        preview = layer['content'] if layer else ''
        content = json.dumps({'source': 'workspace:' + source, 'overview': preview,
                              'overviewNextOffset': layer['next_offset'] if layer else None,
                              'detail': content}, ensure_ascii=False)
        if source.startswith('doc:'):
            hits.append(f"文档《{_document_name(storage, source[len('doc:'):])}》\n{content}")
        else:
            hits.append(f"文件 {source.removeprefix('file:')}\n{content}")
    documents = index.documents_in(workspace_id)
    semantic = semantic_workspace(index, vector_store, embed, workspace_id, query, root, documents)
    return {'hits': hits, 'documents': documents, 'semantic': semantic}


def semantic_workspace(index, vector_store, embed, workspace_id: str, query: str,
                        root: Path | None, documents: list[str]) -> list[str]:
    """语义召回：范围由工作区成员关系决定，不由这次查询的词面命中决定。"""
    semantic: list[str] = []
    if vector_store is not None and documents:
        try:
            semantic.extend(vector_store.search_expanded_files(documents, query))
        except Exception:
            pass
    if embed is None or root is None:
        return semantic
    try:
        vectors = embed([query])
    except Exception:
        return semantic
    if not vectors:
        return semantic
    for source, _score in index.search_files_by_vector(workspace_id, vectors[0], limit=_SEMANTIC_FILES):
        relative = source.removeprefix('file:')
        detail = index.read_source(workspace_id, source, limit=_SEMANTIC_FILE_CHARS)
        if detail:
            semantic.append(f"文件 {relative}\n来源 workspace:{source}\n{detail['content']}")
    return semantic


def bind_document(storage, index, vector_store, workspace_id: str, source_id: str) -> None:
    """把一个文档挂进工作区索引；内容版本没变就不重复读取。"""
    document = storage.get_document(source_id)
    uploaded = storage.get_file(source_id)
    if not document and not uploaded:
        return
    # 文件编号上传时生成、内容不再变；文档则以版本号判断是否重建过。
    marker = f"v{document.version}" if document else 'v1'
    source = 'doc:' + source_id
    if index.source_marker(workspace_id, source) == marker:
        return
    chunks = vector_store.document_chunks(source_id) if vector_store is not None else []
    if not chunks and uploaded is not None:
        text = (uploaded.extractedText or '').strip()
        chunks = [text] if text else []
    if not chunks:
        return
    index.index_source(workspace_id, source, chunks, marker)


def _read_workspace_file(root: Path, relative: str) -> str:
    """Read a workspace file, refusing anything that points outside the workspace."""
    if private_path(relative):
        return ''
    try:
        target = (Path(root) / relative).resolve()
        target.relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return ''
    if target.is_symlink() or not target.is_file():
        return ''
    try:
        return target.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def _document_name(storage, source_id: str) -> str:
    record = storage.get_file(source_id) or storage.get_document(source_id)
    return str(getattr(record, 'fileName', '') or source_id)
