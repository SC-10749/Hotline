"""Versioned platform skill catalog. JSON RPC over stdin/stdout; Python 3.11+."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'data/skill-center/catalog.db'


def validate(content):
    match = re.match(r'\A---\s*\n(.*?)\n---\s*\n(.*)', content, re.S)
    if not match or not match[2].strip():
        raise ValueError('需要 YAML frontmatter 和非空技能正文')
    meta = {}
    for line in match[1].splitlines():
        key, sep, value = line.partition(':')
        if sep and key in ('name', 'description'):
            meta[key] = value.strip().strip('\"\'')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', meta.get('name', '')) or len(meta['name']) > 64:
        raise ValueError('name 必须是 1–64 位小写英文、数字或连字符')
    if not meta.get('description') or meta['description'] in ('|', '>'):
        raise ValueError('description 请使用非空的单行文本')
    return meta


class Catalog:
    def __init__(self, path=DEFAULT_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS versions (
          name TEXT, version TEXT, description TEXT, content TEXT, resources TEXT,
          source TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(name, version));
        CREATE TABLE IF NOT EXISTS bindings (
          project TEXT, name TEXT, version TEXT, PRIMARY KEY(project, name));
        ''')
        # Migrate historical hash IDs and their bindings together, once. The write
        # lock also prevents simultaneous service processes allocating the same vN.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in self.db.execute('PRAGMA table_info(versions)')}
            if 'content_hash' not in columns:
                self.db.execute('ALTER TABLE versions ADD COLUMN content_hash TEXT')
                counts = {}
                for row in self.db.execute('SELECT name, version FROM versions ORDER BY rowid').fetchall():
                    name, previous = row['name'], row['version']
                    counts[name] = counts.get(name, 0) + 1
                    version = f'v{counts[name]}'
                    self.db.execute('UPDATE versions SET version=?, content_hash=? WHERE name=? AND version=?',
                                    (version, previous, name, previous))
                    self.db.execute('UPDATE bindings SET version=? WHERE name=? AND version=?',
                                    (version, name, previous))
            self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS versions_content_hash ON versions(name, content_hash)')

    def call(self, action, args):
        if action == 'save':
            content = args['content']
            meta = validate(content)
            resources = args.get('resources', {})
            if not isinstance(resources, dict):
                raise ValueError('resources 必须是文件路径到文本的映射')
            for name, value in resources.items():
                p = PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or not isinstance(value, str):
                    raise ValueError('非法资源路径或内容')
            packed = json.dumps(resources, ensure_ascii=False, sort_keys=True)
            if len(content.encode()) + len(packed.encode()) > 5 * 1024 * 1024:
                raise ValueError('技能超过 5MB')
            content_hash = hashlib.sha256((content + '\0' + packed).encode()).hexdigest()
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                existing = self.db.execute('SELECT version FROM versions WHERE name=? AND content_hash=?',
                                           (meta['name'], content_hash)).fetchone()
                if existing:
                    version = existing['version']
                else:
                    number = self.db.execute('SELECT COALESCE(MAX(CAST(SUBSTR(version,2) AS INTEGER)),0)+1 FROM versions WHERE name=?',
                                             (meta['name'],)).fetchone()[0]
                    version = f'v{number}'
                    self.db.execute('INSERT INTO versions(name,version,description,content,resources,source,content_hash) VALUES(?,?,?,?,?,?,?)',
                                    (meta['name'], version, meta['description'], content, packed, json.dumps(args.get('source', {})), content_hash))
            return {'name': meta['name'], 'version': version}
        if action == 'bind':
            project, name = args['project'], args['name']
            version = args.get('version')
            with self.db:
                if version:
                    if not self.db.execute('SELECT 1 FROM versions WHERE name=? AND version=?', (name, version)).fetchone():
                        raise ValueError('技能版本不存在')
                    self.db.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?)', (project, name, version))
                else:
                    self.db.execute('DELETE FROM bindings WHERE project=? AND name=?', (project, name))
            return {'ok': True}
        if action == 'list':
            return {'skills': [dict(r) for r in self.db.execute('SELECT * FROM versions ORDER BY created_at DESC, rowid DESC')],
                    'bindings': [dict(r) for r in self.db.execute('SELECT * FROM bindings')]}
        if action == 'runtime':
            return {'skills': [dict(r) for r in self.db.execute('SELECT v.* FROM versions v JOIN bindings b ON v.name=b.name AND v.version=b.version WHERE b.project=? ORDER BY v.name', (args['project'],))]}
        raise ValueError('未知操作')


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        catalog = Catalog(os.getenv('HOTLINE_SKILL_DB', str(DEFAULT_DB)))
        try:
            result = catalog.call(request['action'], request.get('args', {}))
        finally:
            catalog.db.close()
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True))
        sys.exit(1)
