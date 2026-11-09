"""Workspace-scoped recall over a local index: Chinese keyword layers plus file vectors.

The vector store keeps semantic recall for documents; this module keeps the
workspace itself searchable, so identifiers, error codes and Chinese wording
are found across every file and every document the workspace has used, instead
of only the selected one.

Keyword matching is layered, in the order the design calls for:
  1. exact tokens (identifiers, error codes) matched through FTS5 trigrams;
  2. Chinese terms of three characters or more matched as trigrams, which
     needs no word segmenter;
  3. Chinese terms of two characters matched as a phrase in a bigram table,
     because the trigram tokenizer cannot index anything shorter;
  4. LIKE fallback for what is left, such as a single Chinese character.

Every layer is ranked by its own relevance, so a short Chinese term is not
pushed below the longer ones just because it needs a different table.

Workspace files also get one vector each, stored locally. That gives the
workspace a semantic channel of its own: a question can reach a file without
sharing a single character with it.
"""
from __future__ import annotations

import math
import os
import re
import sqlite3
import time
from array import array
from contextlib import contextmanager
from pathlib import Path

from ..context_engineering.privacy import private_path
from .layers import source_layers

# FTS5 trigram only indexes three characters or more, so shorter terms need LIKE.
_MIN_TRIGRAM = 3
_MAX_TERMS = 12
_TIER_LIMIT = 50
_LIKE_LIMIT = 20
_CHUNK_CHARS = 1500
_MAX_FILE_BYTES = 256 * 1024
# A file profile is one embedding per file; the excerpt keeps a long file honest.
_PROFILE_CHARS = 1200
_PROFILE_READ = 20000
_EMBED_BATCH = 10
_DEFAULT_EMBED_BUDGET = 40
_MIN_VECTOR_SCORE = 0.35

_ASCII = re.compile(r'[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*')
_CJK = re.compile(r'[\u4e00-\u9fff]+')
_CJK_CHAR = re.compile(r'([\u4e00-\u9fff])')
_SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
              'target', '.idea', '.vscode', '.pytest_cache', '.mypy_cache', 'coverage', 'data'}


def _escape_like(term: str) -> str:
    return term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _bigram_body(text: str) -> str:
    """Space out every Chinese character so a two-character term becomes a phrase."""
    return _CJK_CHAR.sub(r' \1 ', text)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return list(vector)
    return [value / norm for value in vector]


def _chunk(text: str) -> list[str]:
    """Split text into line-aligned chunks small enough to stay inside a prompt."""
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for line in text.splitlines():
        if buffer and size + len(line) > _CHUNK_CHARS:
            chunks.append('\n'.join(buffer))
            buffer, size = [], 0
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        chunks.append('\n'.join(buffer))
    return [chunk for chunk in chunks if chunk.strip()]


def _profile(text: str) -> str:
    """A stable head, middle and tail sample, so one embedding represents the file."""
    text = text[:_PROFILE_READ]
    if len(text) <= _PROFILE_CHARS:
        return text
    middle = len(text) // 2
    return f"{text[:400]}\n{text[middle - 200:middle + 200]}\n{text[-400:]}"


def workspace_files(root: Path, max_file_bytes: int = _MAX_FILE_BYTES):
    """Yield (path, relative posix path, stat) for the candidate files of a workspace."""
    stack = [Path(root)]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for entry in entries:
            if entry.name in _SKIP_DIRS or private_path(entry.name):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.st_size == 0 or stat.st_size > max_file_bytes:
                continue
            path = Path(entry.path)
            yield path, path.relative_to(root).as_posix(), stat


class WorkspaceIndex:
    """Keyword layers and file vectors for the documents of a workspace."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_source (
                    workspace_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    marker TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,
                    PRIMARY KEY(workspace_id, source_id));
                CREATE VIRTUAL TABLE IF NOT EXISTS workspace_chunk_fts USING fts5(
                    content, chunk_id UNINDEXED, workspace_id UNINDEXED,
                    source_id UNINDEXED, tokenize='trigram');
                CREATE VIRTUAL TABLE IF NOT EXISTS workspace_chunk_bi USING fts5(
                    body, content UNINDEXED, chunk_id UNINDEXED, workspace_id UNINDEXED,
                    source_id UNINDEXED, tokenize='unicode61');
                CREATE TABLE IF NOT EXISTS workspace_file_vec (
                    workspace_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    dim INTEGER NOT NULL, vector BLOB NOT NULL,
                    marker TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,
                    PRIMARY KEY(workspace_id, source_id));
            """)
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(workspace_source)')}
            for name in ('abstract', 'overview'):
                if name not in columns:
                    db.execute(f"ALTER TABLE workspace_source ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        with self.db() as db:
            previous = db.execute('SELECT workspace_id,source_id FROM workspace_source UNION '
                                  'SELECT workspace_id,source_id FROM workspace_file_vec').fetchall()
        for row in previous:
            if row['source_id'].startswith('file:') and private_path(row['source_id'][5:]):
                self.remove_source(row['workspace_id'], row['source_id'])

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def source_marker(self, workspace_id: str, source_id: str) -> str:
        with self.db() as db:
            row = db.execute("SELECT CASE WHEN overview='' THEN '' ELSE marker END AS marker FROM workspace_source WHERE workspace_id=? AND source_id=?",
                             (workspace_id, source_id)).fetchone()
        return row['marker'] if row else ''

    def list_sources(self, workspace_id: str) -> dict[str, str]:
        """source_id -> content marker, used to skip unchanged files and prune deleted ones."""
        with self.db() as db:
            rows = db.execute('SELECT source_id, marker FROM workspace_source WHERE workspace_id=?',
                              (workspace_id,)).fetchall()
        return {row['source_id']: row['marker'] for row in rows}

    def documents_in(self, workspace_id: str) -> list[str]:
        """Every document bound to the workspace, independent of what a query matched."""
        return [source[len('doc:'):] for source in self.list_sources(workspace_id)
                if source.startswith('doc:')]

    def remove_source(self, workspace_id: str, source_id: str) -> None:
        with self.db() as db:
            db.execute('DELETE FROM workspace_chunk_fts WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))
            db.execute('DELETE FROM workspace_chunk_bi WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))
            db.execute('DELETE FROM workspace_file_vec WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))
            db.execute('DELETE FROM workspace_source WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))

    def index_source(self, workspace_id: str, source_id: str, chunks: list[str], marker: str = '') -> int:
        """Replace the chunks of one source inside one workspace."""
        if source_id.startswith('file:') and private_path(source_id[5:]):
            self.remove_source(workspace_id, source_id)
            return 0
        abstract, overview = source_layers(source_id, chunks)
        with self.db() as db:
            db.execute('DELETE FROM workspace_chunk_fts WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))
            db.execute('DELETE FROM workspace_chunk_bi WHERE workspace_id=? AND source_id=?',
                       (workspace_id, source_id))
            stored = 0
            for position, content in enumerate(chunks):
                text = (content or '').strip()
                if not text:
                    continue
                chunk_id = f'{source_id}#{position}'
                db.execute('''INSERT INTO workspace_chunk_fts
                    (content, chunk_id, workspace_id, source_id) VALUES (?,?,?,?)''',
                           (text, chunk_id, workspace_id, source_id))
                db.execute('''INSERT INTO workspace_chunk_bi
                    (body, content, chunk_id, workspace_id, source_id) VALUES (?,?,?,?,?)''',
                           (_bigram_body(text), text, chunk_id, workspace_id, source_id))
                stored += 1
            db.execute('''INSERT INTO workspace_source(workspace_id, source_id, marker, updated_at, abstract, overview)
                VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id, source_id) DO UPDATE SET
                marker=excluded.marker, updated_at=excluded.updated_at,
                abstract=excluded.abstract, overview=excluded.overview''',
                       (workspace_id, source_id, marker, time.time(), abstract, overview))
        return stored

    def read_source(self, workspace_id: str, source_id: str, offset: int = 0, limit: int = 4000,
                    level: str = 'detail') -> dict | None:
        if offset < 0 or not 1 <= limit <= 12000 or level not in {'abstract', 'overview', 'detail'}:
            raise ValueError('来源读取参数无效')
        if source_id.startswith('file:') and private_path(source_id[5:]):
            return None
        with self.db() as db:
            source = db.execute('SELECT * FROM workspace_source WHERE workspace_id=? AND source_id=?',
                                (workspace_id, source_id)).fetchone()
            if source is None:
                return None
            if level == 'detail':
                rows = db.execute('SELECT content FROM workspace_chunk_fts WHERE workspace_id=? AND source_id=? '
                                  "ORDER BY CAST(substr(chunk_id,length(source_id)+2) AS INTEGER)",
                                  (workspace_id, source_id)).fetchall()
                content = '\n'.join(row['content'] for row in rows)
            else:
                content = source[level]
        return {'source_id': source_id, 'level': level, 'content': content[offset:offset + limit],
                'next_offset': offset + limit if offset + limit < len(content) else None,
                'totalCharacters': len(content), 'version': source['marker']}

    def overview(self, workspace_id: str, limit: int = 64) -> dict:
        with self.db() as db:
            total = db.execute('SELECT COUNT(*) FROM workspace_source WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
            rows = db.execute('SELECT source_id,abstract,marker FROM workspace_source WHERE workspace_id=? '
                              'ORDER BY source_id LIMIT ?', (workspace_id, limit)).fetchall()
            inventory = db.execute('SELECT source_id,abstract FROM workspace_source WHERE workspace_id=? '
                                   'ORDER BY source_id', (workspace_id,)).fetchall()
        directories = {}
        for row in inventory:
            source = row['source_id']
            parts = source.removeprefix('file:').split('/')
            directory = '/'.join(parts[:min(2, len(parts) - 1)]) if source.startswith('file:') else 'documents'
            entry = directories.setdefault(directory or '.', {'directory': directory or '.', 'sourceCount': 0, 'abstracts': []})
            entry['sourceCount'] += 1
            if len(entry['abstracts']) < 4:
                entry['abstracts'].append({'source': source, 'abstract': row['abstract']})
        return {'scope': workspace_id, 'totalSources': total, 'listedSources': len(rows),
                'complete': len(rows) == total, 'method': 'extractive', 'sources': [dict(row) for row in rows],
                'totalDirectories': len(directories), 'directories': list(directories.values())[:64],
                'directoryInventoryComplete': len(directories) <= 64}

    def index_directory(self, workspace_id: str, root: Path) -> int:
        """Index the text files of one workspace directory.

        Files are stamped with their mtime and size, so unchanged files are not
        re-read, and files deleted from the workspace are dropped. The walk uses
        scandir and skips symlinks, so it stays inside the workspace.
        """
        root = Path(root)
        if not root.is_dir():
            return 0
        indexed = 0
        seen: set[str] = set()
        for path, relative, stat in workspace_files(root):
            source_id = 'file:' + relative
            seen.add(source_id)
            marker = f"{stat.st_mtime_ns}:{stat.st_size}"
            if self.source_marker(workspace_id, source_id) == marker:
                continue
            chunks = _chunk(self._read_text(path))
            if not chunks:
                continue
            self.index_source(workspace_id, source_id, chunks, marker)
            indexed += 1
        for source_id in self.list_sources(workspace_id):
            if source_id.startswith('file:') and source_id not in seen:
                self.remove_source(workspace_id, source_id)
        return indexed

    def embed_directory(self, workspace_id: str, root: Path, embed, budget: int = _DEFAULT_EMBED_BUDGET) -> int:
        """Give every changed file of the workspace one vector, stored locally.

        The embedder is a callable taking a list of texts and returning one
        vector per text. The budget caps how many files are embedded per call,
        so a large workspace fills up over several calls instead of stalling one.
        """
        root = Path(root)
        if not root.is_dir() or embed is None:
            return 0
        pending: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for path, relative, stat in workspace_files(root):
            source_id = 'file:' + relative
            seen.add(source_id)
            marker = f"{stat.st_mtime_ns}:{stat.st_size}"
            if self.file_vector_marker(workspace_id, source_id) == marker:
                continue
            text = self._read_text(path)
            if not text.strip():
                continue
            pending.append((source_id, marker, _profile(text)))
        for source_id in self.list_sources(workspace_id):
            if source_id.startswith('file:') and source_id not in seen:
                self.remove_source(workspace_id, source_id)
        embedded = 0
        for start in range(0, len(pending), _EMBED_BATCH):
            if embedded >= budget:
                break
            batch = pending[start:start + _EMBED_BATCH]
            try:
                vectors = embed([item[2] for item in batch])
            except Exception:
                break
            if not vectors or len(vectors) != len(batch):
                break
            for (source_id, marker, _), vector in zip(batch, vectors):
                self.store_file_vector(workspace_id, source_id, vector, marker)
            embedded += len(batch)
        return embedded

    def file_vector_marker(self, workspace_id: str, source_id: str) -> str:
        with self.db() as db:
            row = db.execute('SELECT marker FROM workspace_file_vec WHERE workspace_id=? AND source_id=?',
                             (workspace_id, source_id)).fetchone()
        return row['marker'] if row else ''

    def store_file_vector(self, workspace_id: str, source_id: str, vector: list[float], marker: str = '') -> None:
        if source_id.startswith('file:') and private_path(source_id[5:]):
            self.remove_source(workspace_id, source_id)
            return
        values = array('f', _normalize(vector))
        with self.db() as db:
            db.execute('''INSERT INTO workspace_file_vec
                (workspace_id, source_id, dim, vector, marker, updated_at) VALUES (?,?,?,?,?,?)
                ON CONFLICT(workspace_id, source_id) DO UPDATE SET
                dim=excluded.dim, vector=excluded.vector, marker=excluded.marker,
                updated_at=excluded.updated_at''',
                       (workspace_id, source_id, len(values), values.tobytes(), marker, time.time()))

    def search_files_by_vector(self, workspace_id: str, query_vector: list[float],
                               limit: int = 3, min_score: float = _MIN_VECTOR_SCORE) -> list[tuple[str, float]]:
        """Rank the workspace files by cosine similarity, no keyword involved."""
        query = _normalize(query_vector)
        with self.db() as db:
            rows = db.execute('SELECT source_id, vector FROM workspace_file_vec WHERE workspace_id=?',
                              (workspace_id,)).fetchall()
        scored: list[tuple[str, float]] = []
        for row in rows:
            if private_path(row['source_id'].removeprefix('file:')):
                continue
            vector = array('f', row['vector'])
            if len(vector) != len(query):
                continue
            score = sum(a * b for a, b in zip(query, vector))
            if score >= min_score:
                scored.append((row['source_id'], score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def search(self, workspace_id: str, query: str, limit: int = 8, exclude_source: str = '') -> list[str]:
        """Layered keyword recall limited to one workspace."""
        return [f"{source}\n{content}"
                for source, content in self.search_sources(workspace_id, query, limit, exclude_source)]

    def search_sources(self, workspace_id: str, query: str, limit: int = 8,
                       exclude_source: str = '') -> list[tuple[str, str]]:
        """Same as search, but keeps the source id so callers can route the hit."""
        if not workspace_id or not (query or '').strip():
            return []
        exact, chinese, bigram, short = self._terms(query)
        tiers = []
        if exact:
            tiers.append(self._match(workspace_id, exact, exclude_source))
        if chinese:
            tiers.append(self._match(workspace_id, chinese, exclude_source))
        if bigram:
            tiers.append(self._bigram_match(workspace_id, bigram, exclude_source))
        if short:
            tiers.append(self._like(workspace_id, short, exclude_source))
        tiers = [[(source, content) for source, content in tier
                  if not (source.startswith('file:') and private_path(source[5:]))] for tier in tiers]
        return self._merge(tiers, limit)

    def _terms(self, query: str) -> tuple[list[str], list[str], list[str], list[str]]:
        """Split a query into exact tokens, Chinese trigrams, bigrams and short terms."""
        exact: list[str] = []
        short: list[str] = []
        for token in _ASCII.findall(query):
            (exact if len(token) >= _MIN_TRIGRAM else short).append(token)
        chinese: list[str] = []
        bigram: list[str] = []
        for run in _CJK.findall(query):
            if len(run) >= _MIN_TRIGRAM:
                chinese.extend(run[index:index + _MIN_TRIGRAM]
                               for index in range(len(run) - _MIN_TRIGRAM + 1))
            elif len(run) == 2:
                bigram.append(run)
            else:
                short.append(run)
        return exact[:_MAX_TERMS], chinese[:_MAX_TERMS], bigram[:_MAX_TERMS], short[:_MAX_TERMS]

    def _match(self, workspace_id: str, terms: list[str], exclude_source: str) -> list[tuple[str, str]]:
        expression = ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms)
        sql = '''SELECT source_id, content FROM workspace_chunk_fts
                 WHERE workspace_chunk_fts MATCH ? AND workspace_id = ?'''
        params: list = [expression, workspace_id]
        if exclude_source:
            sql += ' AND source_id != ?'
            params.append(exclude_source)
        sql += ' ORDER BY rank LIMIT ?'
        params.append(_TIER_LIMIT)
        with self.db() as db:
            rows = db.execute(sql, params).fetchall()
        return [(row['source_id'], row['content']) for row in rows]

    def _bigram_match(self, workspace_id: str, terms: list[str], exclude_source: str) -> list[tuple[str, str]]:
        """Two-character Chinese terms, matched as phrases in the bigram table."""
        expression = ' OR '.join('"' + _bigram_body(term) + '"' for term in terms)
        sql = '''SELECT source_id, content FROM workspace_chunk_bi
                 WHERE workspace_chunk_bi MATCH ? AND workspace_id = ?'''
        params: list = [expression, workspace_id]
        if exclude_source:
            sql += ' AND source_id != ?'
            params.append(exclude_source)
        sql += ' ORDER BY rank LIMIT ?'
        params.append(_TIER_LIMIT)
        with self.db() as db:
            rows = db.execute(sql, params).fetchall()
        return [(row['source_id'], row['content']) for row in rows]

    def _like(self, workspace_id: str, terms: list[str], exclude_source: str) -> list[tuple[str, str]]:
        """Last resort for terms no FTS table can index, such as a single character.

        Ranked by how often the term occurs, so a dense match is not buried
        behind an incidental one.
        """
        found: list[tuple[str, str]] = []
        for term in terms:
            sql = """SELECT source_id, content FROM workspace_chunk_fts
                     WHERE workspace_id = ? AND content LIKE ? ESCAPE '\\'"""
            params: list = [workspace_id, f'%{_escape_like(term)}%']
            if exclude_source:
                sql += ' AND source_id != ?'
                params.append(exclude_source)
            sql += ''' ORDER BY (LENGTH(content) - LENGTH(REPLACE(content, ?, ''))) DESC,
                      LENGTH(content) ASC LIMIT ?'''
            params.extend([term, _LIKE_LIMIT])
            with self.db() as db:
                rows = db.execute(sql, params).fetchall()
            found.extend((row['source_id'], row['content']) for row in rows)
        return found

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read a text file; binary files are skipped instead of being mangled."""
        try:
            with path.open('rb') as handle:
                if b'\x00' in handle.read(4096):
                    return ''
            return path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            return ''

    @staticmethod
    def _merge(tiers: list[list[tuple[str, str]]], limit: int) -> list[tuple[str, str]]:
        """Interleave the tiers so one strong layer cannot crowd out the others."""
        merged: list[tuple[str, str]] = []
        seen: set[str] = set()
        depth = max((len(tier) for tier in tiers), default=0)
        for position in range(depth):
            for tier in tiers:
                if position >= len(tier):
                    continue
                source_id, content = tier[position]
                key = re.sub(r'\s+', ' ', content).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append((source_id, content))
                if len(merged) >= limit:
                    return merged
        return merged
