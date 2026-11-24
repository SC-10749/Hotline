"""OpenViking HTTP adapter. Credentials and namespace selection stay server-side."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..context_engineering.privacy import sanitize_text


class OpenVikingError(RuntimeError):
    def __init__(self, code: str = 'unavailable'):
        self.code = code
        super().__init__('长期记忆服务暂不可用')


def memory_uri_belongs(peer_id: str, uri: str, *, allow_root: bool = False) -> bool:
    decoded = urllib.parse.unquote(uri)
    parsed = urllib.parse.urlsplit(decoded)
    parts = parsed.path.strip('/').split('/')
    if parsed.scheme != 'viking' or parsed.query or parsed.fragment or '..' in parts:
        return False
    if parsed.netloc == 'user' and len(parts) >= 4:
        parts = parts[1:]
    elif parsed.netloc != '~':
        return False
    root = ['peers', peer_id, 'memories']
    return parts[:3] == root and (len(parts) > 3 or (allow_root and len(parts) == 3))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OpenVikingError('redirect_rejected')


def memory_uri_blocked(uri: str, blocked) -> bool:
    def key(value):
        parsed = urllib.parse.urlsplit(urllib.parse.unquote(value))
        parts = parsed.path.strip('/').split('/')
        return '/'.join(parts[1:] if parsed.netloc == 'user' else parts)
    return key(uri) in {key(value) for value in blocked}


class OpenVikingClient:
    def __init__(self, url: str, api_key: str = '', timeout: float = 10):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('OpenViking 连接配置无效')
        if parsed.query or parsed.fragment:
            raise ValueError('OpenViking 连接配置无效')
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, path: str, peer_id: str, payload: dict | None = None,
                *, missing_ok: bool = False):
        if not re.fullmatch(r'hotline-[a-f0-9]{32}-\d+', peer_id):
            raise ValueError('记忆命名空间无效')
        headers = {'Content-Type': 'application/json', 'X-OpenViking-Actor-Peer': peer_id}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = urllib.request.Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise OpenVikingError('response_too_large')
            result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise OpenVikingError(f'http_{exc.code}') from None
        except OpenVikingError:
            raise
        except Exception:
            raise OpenVikingError() from None
        if not isinstance(result, dict) or result.get('status') != 'ok':
            raise OpenVikingError('invalid_response')
        return result.get('result')

    def upload(self, peer_id: str, session_id: str, messages: list[dict]) -> None:
        path = '/api/v1/sessions/' + urllib.parse.quote(session_id, safe='')
        # A delivery owns its session. Rebuilding an uncommitted upload makes retries idempotent.
        self.request('DELETE', path, peer_id, missing_ok=True)
        self.request('POST', '/api/v1/sessions', peer_id, {
            'session_id': session_id,
            'memory_policy': {'self': {'enabled': False}, 'peer': {'enabled': True},
                              'working_memory': {'enabled': False},
                              'memory_types': ['preferences', 'entities', 'events', 'experiences']},
        })
        self.request('PATCH', path + '/config', peer_id, {'auto_commit_policy': None})
        safe_messages = []
        for item in messages:
            safe_messages.append({'role': item['role'], 'peer_id': peer_id,
                                  'content': sanitize_text(item['content']),
                                  'source_message_ids': item['source_message_ids'],
                                  'turn_id': session_id})
        self.request('POST', path + '/messages/batch', peer_id, {'messages': safe_messages})

    def commit(self, peer_id: str, session_id: str) -> dict:
        result = self.request('POST', '/api/v1/sessions/' + urllib.parse.quote(session_id, safe='') + '/commit',
                              peer_id, {'keep_recent_count': 0})
        if not isinstance(result, dict):
            raise OpenVikingError('invalid_commit')
        return result

    def task(self, peer_id: str, task_id: str) -> dict:
        result = self.request('GET', '/api/v1/tasks/' + urllib.parse.quote(task_id, safe=''), peer_id)
        if not isinstance(result, dict):
            raise OpenVikingError('invalid_task')
        return result

    def find_commit_task(self, peer_id: str, session_id: str) -> dict | None:
        path = '/api/v1/tasks?' + urllib.parse.urlencode({
            'task_type': 'session_commit', 'resource_id': session_id, 'limit': 1})
        result = self.request('GET', path, peer_id)
        if not isinstance(result, list):
            raise OpenVikingError('invalid_tasks')
        return next((item for item in result if isinstance(item, dict)
                     and item.get('resource_id') == session_id and item.get('task_id')), None)

    def search(self, peer_id: str, query: str, limit: int = 8) -> list[dict]:
        result = self.request('POST', '/api/v1/search/search', peer_id, {
            'query': sanitize_text(query), 'mode': 'list', 'context_type': 'memory',
            'target_uri': f'viking://~/peers/{peer_id}/memories',
            'limit': min(20, max(1, limit)), 'read_content': False, 'include_provenance': True,
        })
        if not isinstance(result, dict) or not isinstance(result.get('memories', []), list):
            raise OpenVikingError('invalid_search')
        hits = []
        for hit in result.get('memories', []):
            if not isinstance(hit, dict):
                continue
            uri = str(hit.get('uri', ''))
            if not uri.startswith('viking://user/') or not memory_uri_belongs(peer_id, uri):
                continue
            content = hit.get('abstract') or hit.get('content') or ''
            if isinstance(content, str):
                hits.append({'uri': uri, 'content': sanitize_text(content),
                             'score': hit.get('score', 0), 'level': hit.get('level', 2),
                             'provenance': hit.get('provenance', {})})
        return hits[:limit]

    def read_level(self, peer_id: str, uri: str, level: str = 'overview') -> str:
        if level not in {'abstract', 'overview'} or not memory_uri_belongs(peer_id, uri, allow_root=True):
            raise ValueError('记忆层级或路径无效')
        directory = uri.rsplit('/', 1)[0] if uri.endswith('.md') else uri
        path = '/api/v1/content/' + level + '?' + urllib.parse.urlencode({'uri': directory})
        result = self.request('GET', path, peer_id, missing_ok=True)
        if result is None:
            return ''
        if not isinstance(result, str):
            raise OpenVikingError('invalid_content')
        return sanitize_text(result)

    def recall(self, peer_id: str, query: str, limit: int = 4, *, blocked=()) -> list[dict]:
        """Locate with L0, inspect L1 once per directory, and read bounded L2 pages."""
        hits = [hit for hit in self.search(peer_id, query, limit) if not memory_uri_blocked(hit['uri'], blocked)]
        overviews = {}
        for index, hit in enumerate(hits):
            uri = hit['uri']
            directory = uri.rsplit('/', 1)[0] if uri.endswith('.md') else uri
            if directory not in overviews:
                try:
                    overviews[directory] = self.read_level(peer_id, directory)
                except OpenVikingError:
                    overviews[directory] = ''
            content = {'abstract': hit['content'], 'overview': overviews[directory]}
            hit['loadedLayers'] = ['L0', 'L1'] if content['overview'] else ['L0']
            if index < 2 and hit['level'] == 2 and not uri.endswith(('/.abstract.md', '/.overview.md')):
                try:
                    content['detail'] = self.read(peer_id, uri, offset=0, limit=80)
                    hit['loadedLayers'].append('L2')
                except OpenVikingError:
                    pass
            hit['content'] = json.dumps(content, ensure_ascii=False)
        return hits

    def delete_memory(self, peer_id: str, uri: str) -> None:
        if not memory_uri_belongs(peer_id, uri, allow_root=True):
            raise ValueError('记忆路径不属于当前范围')
        path = '/api/v1/fs?' + urllib.parse.urlencode({'uri': uri, 'recursive': 'true'})
        self.request('DELETE', path, peer_id, missing_ok=True)

    def read(self, peer_id: str, uri: str, offset: int = 0, limit: int = 100) -> str:
        if not memory_uri_belongs(peer_id, uri):
            raise ValueError('记忆路径不属于当前范围')
        path = '/api/v1/content/read?' + urllib.parse.urlencode({'uri': uri, 'offset': offset, 'limit': limit})
        result = self.request('GET', path, peer_id)
        if not isinstance(result, str):
            raise OpenVikingError('invalid_content')
        return sanitize_text(result)

    def delete_session(self, peer_id: str, session_id: str):
        self.request('DELETE', '/api/v1/sessions/' + urllib.parse.quote(session_id, safe=''),
                     peer_id, missing_ok=True)
