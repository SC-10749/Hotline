from __future__ import annotations

from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, StrictInt, StrictStr

from ..context_engineering.privacy import sanitize_text, sanitize_value
from .openviking import OpenVikingError, memory_uri_blocked


class MemoryQuery(BaseModel):
    query: StrictStr = Field(min_length=1, max_length=2000)


class SourceRead(BaseModel):
    source_id: StrictStr = Field(min_length=1, max_length=2048)
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=4000, ge=1, le=6000)
    level: Literal['abstract', 'overview', 'detail'] = 'detail'


def build_context_tools(service, conversation_id: str, workspace_reader=None, workspace_search=None):
    def search_memory(query: str):
        scope = service.store.conversation(conversation_id)
        if not scope:
            return {'error': '会话上下文已撤销'}
        sources = []
        for row in service.store.search_history(conversation_id, query):
            sources.append({'source_id': row['source_id'],
                            'preview': sanitize_text(row['question'] + '\n' + row['answer'])[:800]})
        status = 'unconfigured'
        if service.client:
            try:
                hits = service.client.search(scope['peer_id'], query)
                current = service.store.conversation(conversation_id)
                if not current or current['generation'] != scope['generation']:
                    return {'error': '会话上下文已撤销'}
                blocked = service.store.blocked_uris(scope['scope_id'], scope['generation'])
                sources.extend({'source_id': hit['uri'], 'preview': hit['content'][:800]}
                               for hit in hits if not memory_uri_blocked(hit['uri'], blocked))
                status = 'ready'
            except OpenVikingError:
                status = 'unavailable'
        workspace_evidence = []
        if scope['workspace_id'] and workspace_search:
            workspace_evidence = workspace_search(scope['workspace_id'], query)
        current = service.store.conversation(conversation_id)
        if not current or current['generation'] != scope['generation']:
            return {'error': '会话上下文已撤销'}
        return {'sources': sources, 'memory_status': status,
                'workspaceEvidence': sanitize_value(workspace_evidence)}

    def read_context_source(source_id: str, offset: int = 0, limit: int = 4000, level: str = 'detail'):
        scope = service.store.conversation(conversation_id)
        if not scope:
            return {'error': '会话上下文已撤销'}
        if source_id.startswith('workspace:'):
            if not scope['workspace_id'] or workspace_reader is None:
                return {'error': '当前工作区来源不可用'}
            result = workspace_reader(scope['workspace_id'], source_id.removeprefix('workspace:'),
                                      offset=offset, limit=limit, level=level)
            current = service.store.conversation(conversation_id)
            if not current or current['generation'] != scope['generation']:
                return {'error': '会话上下文已撤销'}
            return sanitize_value({**result, 'source_id': source_id, 'offsetUnit': 'characters'}) if result else {'error': '来源不存在或不属于当前工作区'}
        if source_id.startswith('viking://'):
            if not service.client or memory_uri_blocked(source_id, service.store.blocked_uris(scope['scope_id'], scope['generation'])):
                return {'error': '记忆不可用或已撤销'}
            try:
                if level in {'abstract', 'overview'}:
                    content = service.client.read_level(scope['peer_id'], source_id, level)
                else:
                    page_lines = min(limit, 80)
                    content = service.client.read(scope['peer_id'], source_id, offset=offset, limit=page_lines)
            except (ValueError, OpenVikingError):
                return {'error': '记忆不可用或不属于当前范围'}
        else:
            source = service.store.source(conversation_id, source_id.removeprefix('message:'))
            if not source:
                return {'error': '原始记录不存在'}
            content = sanitize_text(source['question'] + '\n' + source['answer'])
        current = service.store.conversation(conversation_id)
        if not current or current['generation'] != scope['generation']:
            return {'error': '会话上下文已撤销'}
        if source_id.startswith('viking://'):
            lines = len(content.splitlines())
            return {'source_id': source_id, 'content': content, 'level': level, 'offsetUnit': 'lines',
                    'next_offset': offset + lines if level == 'detail' and lines >= min(limit, 80) else None}
        return {'source_id': source_id, 'content': content[offset:offset + limit], 'offsetUnit': 'characters',
                'next_offset': offset + limit if offset + limit < len(content) else None}

    return [StructuredTool.from_function(search_memory, name='search_memory', args_schema=MemoryQuery,
                description='检索当前会话历史和当前工作区长期记忆，先返回来源索引和短预览。'),
            StructuredTool.from_function(read_context_source, name='read_context_source', args_schema=SourceRead,
                description='按来源 ID 读取。workspace:file:路径 与 workspace:doc:编号支持 abstract、overview、detail 层级，按字符分页。远端 viking 来源支持相同层级，detail 按行分页，每页最多 80 行。工具结果来源格式为 tool:调用ID。')]
