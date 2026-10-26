"""Versioned skill catalog for Dodo Agent. JSON RPC over stdin/stdout; Python 3.11+.

Also imported in-process by the FastAPI backend (python_backend.fastapi_app) and
SkillRegistry, so keep this module standard-library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'data/skill-center/catalog.db'
DEFAULT_PROJECT = 'dodo-agent'


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


MAX_PATCHES = 8
MAX_CONTENT_BYTES = 5 * 1024 * 1024
SENSITIVE_RE = re.compile(r"(?i)(api[_ -]?key|secret|password|token)\s*[:=]\s*[^\s]+")
INJECTION_RE = re.compile(r"(?i)(ignore previous instructions|reveal system prompt|disable safety|bypass security)")


def security_scan(content):
    if SENSITIVE_RE.search(content):
        raise ValueError('技能内容疑似包含密钥或凭据')
    if INJECTION_RE.search(content):
        raise ValueError('技能内容包含疑似提示注入指令')


def apply_patches(content, patches):
    if not isinstance(patches, list) or not patches or len(patches) > MAX_PATCHES:
        raise ValueError(f'patch 数量必须为 1–{MAX_PATCHES}')
    result = content
    for patch in patches:
        if not isinstance(patch, dict) or patch.get('op') not in {'add', 'delete', 'replace'}:
            raise ValueError('仅支持 add、delete、replace patch')
        op = patch['op']
        if op == 'add':
            text = patch.get('text')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('add patch 缺少非空 text')
            result = result.rstrip() + '\n\n' + text.strip() + '\n'
        else:
            old = patch.get('old')
            if not isinstance(old, str) or not old or result.count(old) != 1:
                raise ValueError('replace/delete 的 old 必须在正文中恰好出现一次')
            result = result.replace(old, '' if op == 'delete' else patch.get('new', ''), 1)
    return result


def score_case(content, case):
    required = case.get('required', [])
    forbidden = case.get('forbidden', [])
    if not isinstance(required, list) or not isinstance(forbidden, list):
        raise ValueError('评测用例 required/forbidden 必须是数组')
    hits = sum(1 for item in required if isinstance(item, str) and item in content)
    misses = sum(1 for item in forbidden if isinstance(item, str) and item in content)
    total = len(required) + len(forbidden)
    return {'score': (hits + len(forbidden) - misses) / total if total else 1.0,
            'passed': hits == len(required) and misses == 0, 'hits': hits, 'misses': misses}


def score_cases(content, cases):
    rows = [dict(case, result=score_case(content, case)) for case in cases]
    return {'score': sum(row['result']['score'] for row in rows) / len(rows) if rows else 0.0,
            'passed': all(row['result']['passed'] for row in rows) if rows else False, 'cases': rows}


def score_output(output, case):
    required = case.get('required', [])
    forbidden = case.get('forbidden', [])
    hits = sum(1 for item in required if isinstance(item, str) and item in output)
    misses = sum(1 for item in forbidden if isinstance(item, str) and item in output)
    total = len(required) + len(forbidden)
    return {'score': (hits + len(forbidden) - misses) / total if total else 1.0,
            'passed': hits == len(required) and misses == 0, 'hits': hits, 'misses': misses}


def model_json(prompt, env_prefix):
    base = os.getenv(f'{env_prefix}_BASE_URL', '').rstrip('/')
    key = os.getenv(f'{env_prefix}_API_KEY', '')
    model = os.getenv(f'{env_prefix}_MODEL', '')
    if not base or not key or not model:
        raise ValueError(f'未配置 {env_prefix}_BASE_URL、API_KEY、MODEL')
    payload = json.dumps({'model': model, 'temperature': 0, 'messages': [
        {'role': 'system', 'content': '只输出合法 JSON，不要 Markdown。'}, {'role': 'user', 'content': prompt}
    ]}).encode()
    request = urllib.request.Request(base + '/chat/completions', data=payload,
                                     headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read())
    text = data['choices'][0]['message']['content']
    return json.loads(text)


def run_sandbox(case):
    command = case.get('command')
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError('沙箱用例 command 必须是字符串数组')
    timeout = min(max(int(case.get('timeout', 30)), 1), 120)
    with tempfile.TemporaryDirectory(prefix='skill-run-') as workdir:
        result = subprocess.run(command, cwd=workdir, capture_output=True, text=True,
                                timeout=timeout, shell=False, env={'PATH': os.getenv('PATH', ''), 'PYTHONUTF8': '1'})
    output = (result.stdout + '\n' + result.stderr).strip()
    return {'returncode': result.returncode, 'output': output, 'verifier': score_output(output, case)}


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
        CREATE TABLE IF NOT EXISTS eval_cases (
          case_id TEXT PRIMARY KEY, split TEXT NOT NULL, payload TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS evolution_runs (
          run_id TEXT PRIMARY KEY, name TEXT NOT NULL, base_version TEXT NOT NULL,
          candidate_version TEXT, status TEXT NOT NULL, artifact TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS rollouts (
          project TEXT, name TEXT, candidate_version TEXT, previous_version TEXT,
          percentage INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(project, name));
        CREATE TABLE IF NOT EXISTS metrics (
          id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, name TEXT, version TEXT,
          request_id TEXT, metric TEXT, value REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
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
            # Single-project layout: fold the historical Hotline project ID into the
            # new one so existing bindings, rollouts and metrics keep working.
            for table in ('bindings', 'rollouts', 'metrics'):
                self.db.execute(
                    f"UPDATE {table} SET project=? WHERE project='projects/ai/dodo-agent'",
                    (DEFAULT_PROJECT,),
                )

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
        if action == 'eval_case':
            case_id, split = args.get('caseId'), args.get('split')
            if not isinstance(case_id, str) or not case_id or split not in {'train', 'selection', 'test'}:
                raise ValueError('caseId 和 split 必须有效')
            payload = args.get('case', {})
            if not isinstance(payload, dict):
                raise ValueError('case 必须是对象')
            score_case('', payload)
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO eval_cases(case_id,split,payload) VALUES(?,?,?)',
                                 (case_id, split, json.dumps(payload, ensure_ascii=False)))
            return {'caseId': case_id, 'split': split}
        if action == 'eval_cases':
            rows = self.db.execute('SELECT * FROM eval_cases ORDER BY split, case_id').fetchall()
            return {'cases': [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows]}
        if action == 'evaluate':
            name, version = args['name'], args['version']
            row = self.db.execute('SELECT content FROM versions WHERE name=? AND version=?', (name, version)).fetchone()
            if not row: raise ValueError('技能版本不存在')
            selected = args.get('splits', ['selection'])
            cases = self.db.execute('SELECT split,payload FROM eval_cases WHERE split IN (%s)' % ','.join('?' * len(selected)), selected).fetchall()
            grouped = {split: [] for split in selected}
            for item in cases: grouped[item['split']].append(json.loads(item['payload']))
            return {'name': name, 'version': version, 'scores': {split: score_cases(row['content'], values) for split, values in grouped.items()}}
        if action == 'evolve':
            import uuid
            name, base_version = args['name'], args['baseVersion']
            row = self.db.execute('SELECT content FROM versions WHERE name=? AND version=?', (name, base_version)).fetchone()
            if not row: raise ValueError('基础技能版本不存在')
            candidate = apply_patches(row['content'], args.get('patches'))
            if len(candidate.encode()) > MAX_CONTENT_BYTES or len(candidate.encode()) > len(row['content'].encode()) * 1.2:
                raise ValueError('静态门禁失败：候选内容为空、过大或超过原版 20%')
            validate(candidate); security_scan(candidate)
            all_cases = {split: [] for split in ('train', 'selection', 'test')}
            rows = self.db.execute('SELECT split,payload FROM eval_cases').fetchall()
            for item in rows: all_cases[item['split']].append(json.loads(item['payload']))
            old_scores = {split: score_cases(row['content'], values) for split, values in all_cases.items()}
            new_scores = {split: score_cases(candidate, values) for split, values in all_cases.items()}
            selection_gain = new_scores['selection']['score'] - old_scores['selection']['score']
            regression = any(n['result']['passed'] is False and o['result']['passed'] is True
                             for n, o in zip(new_scores['selection']['cases'], old_scores['selection']['cases']))
            security_ok = True
            gates = {'static': True, 'dynamic': selection_gain > 0, 'regression': not regression,
                     'gain': new_scores['test']['score'] >= old_scores['test']['score'], 'security': security_ok}
            passed = all(gates.values())
            run_id = uuid.uuid4().hex
            artifact = {'patches': args.get('patches'), 'gates': gates, 'old': old_scores, 'new': new_scores}
            candidate_version = None
            if passed:
                saved = self.call('save', {'content': candidate, 'source': {'evolutionRun': run_id, 'baseVersion': base_version}})
                candidate_version = saved['version']
            status = 'staged' if passed else 'rejected'
            with self.db:
                self.db.execute('INSERT INTO evolution_runs(run_id,name,base_version,candidate_version,status,artifact) VALUES(?,?,?,?,?,?)',
                                 (run_id, name, base_version, candidate_version, status, json.dumps(artifact, ensure_ascii=False)))
            return {'runId': run_id, 'status': status, 'candidateVersion': candidate_version, 'gates': gates, 'scores': {'old': old_scores, 'new': new_scores}}
        if action == 'promote':
            project, name, version = args['project'], args['name'], args['version']
            current = self.db.execute('SELECT version FROM bindings WHERE project=? AND name=?', (project, name)).fetchone()
            if not self.db.execute('SELECT 1 FROM versions WHERE name=? AND version=?', (name, version)).fetchone(): raise ValueError('技能版本不存在')
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO rollouts VALUES(?,?,?,?,?,1)', (project, name, version, current['version'] if current else None, min(max(int(args.get('percentage', 10)), 0), 100)))
                self.db.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?)', (project, name, version))
            return {'ok': True, 'status': 'active', 'percentage': int(args.get('percentage', 10))}
        if action == 'rollback':
            project, name = args['project'], args['name']
            row = self.db.execute('SELECT previous_version FROM rollouts WHERE project=? AND name=?', (project, name)).fetchone()
            if not row or not row['previous_version']: raise ValueError('没有可回滚版本')
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?)', (project, name, row['previous_version']))
                self.db.execute('UPDATE rollouts SET active=0 WHERE project=? AND name=?', (project, name))
            return {'ok': True, 'version': row['previous_version']}
        if action == 'run_case':
            return run_sandbox(args.get('case', {}))
        if action == 'judge':
            rubric = args.get('rubric', '判断输出是否完成任务，返回 score、passed、reason。')
            result = model_json(json.dumps({'rubric': rubric, 'input': args.get('input', ''), 'output': args.get('output', '')}, ensure_ascii=False), 'SKILL_JUDGE')
            if not isinstance(result, dict) or 'score' not in result:
                raise ValueError('judge 必须返回包含 score 的 JSON')
            return result
        if action == 'auto_evolve':
            name, base_version = args['name'], args['baseVersion']
            row = self.db.execute('SELECT content FROM versions WHERE name=? AND version=?', (name, base_version)).fetchone()
            if not row: raise ValueError('基础技能版本不存在')
            failures = []
            for item in self.db.execute("SELECT payload FROM eval_cases WHERE split='train'").fetchall():
                case = json.loads(item['payload'])
                result = score_case(row['content'], case)
                if not result['passed']: failures.append({'case': case, 'result': result})
            proposed = model_json(json.dumps({'skill': row['content'], 'failures': failures,
                                              'instruction': '分析失败原因，只生成最多 8 条 bounded patch，格式为 {patches:[{op,old,new,text}]}。'}, ensure_ascii=False), 'SKILL_EVOLUTION')
            return self.call('evolve', {'name': name, 'baseVersion': base_version, 'patches': proposed.get('patches')})
        if action == 'metric':
            project, name, version = args['project'], args['name'], args['version']
            metric, value = str(args['metric']), float(args['value'])
            with self.db:
                self.db.execute('INSERT INTO metrics(project,name,version,request_id,metric,value) VALUES(?,?,?,?,?,?)',
                                 (project, name, version, args.get('requestId'), metric, value))
            auto = False
            threshold = float(os.getenv('SKILL_ROLLOUT_ERROR_THRESHOLD', '0.05'))
            min_samples = int(os.getenv('SKILL_ROLLOUT_MIN_SAMPLES', '30'))
            if metric == 'error_rate':
                row = self.db.execute('SELECT COUNT(*) n, AVG(value) avg FROM metrics WHERE project=? AND name=? AND version=? AND metric=?', (project, name, version, metric)).fetchone()
                if row['n'] >= min_samples and row['avg'] >= threshold:
                    try: self.call('rollback', {'project': project, 'name': name}); auto = True
                    except ValueError: pass
            return {'ok': True, 'autoRolledBack': auto}
        if action == 'metrics':
            rows = self.db.execute('SELECT * FROM metrics ORDER BY id DESC LIMIT 500').fetchall()
            return {'metrics': [dict(row) for row in rows]}
        if action == 'evolution_runs':
            rows = self.db.execute('SELECT * FROM evolution_runs ORDER BY created_at DESC LIMIT 200').fetchall()
            return {'runs': [dict(row) for row in rows]}
        if action == 'rollouts':
            rows = self.db.execute('SELECT * FROM rollouts ORDER BY project, name').fetchall()
            return {'rollouts': [dict(row) for row in rows]}
        if action == 'list':
            return {'skills': [dict(r) for r in self.db.execute('SELECT * FROM versions ORDER BY created_at DESC, rowid DESC')],
                    'bindings': [dict(r) for r in self.db.execute('SELECT * FROM bindings')]}
        if action == 'runtime':
            project = args['project']
            rows = self.db.execute('SELECT v.* FROM versions v JOIN bindings b ON v.name=b.name AND v.version=b.version WHERE b.project=? ORDER BY v.name', (project,)).fetchall()
            request_id = str(args.get('requestId', ''))
            for index, row in enumerate(rows):
                rollout = self.db.execute('SELECT * FROM rollouts WHERE project=? AND name=? AND active=1', (project, row['name'])).fetchone()
                if rollout and rollout['percentage'] > 0 and request_id:
                    bucket = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16) % 100
                    if bucket >= rollout['percentage']:
                        previous = self.db.execute('SELECT * FROM versions WHERE name=? AND version=?', (row['name'], rollout['previous_version'])).fetchone()
                        if previous: rows[index] = previous
            return {'skills': [dict(r) for r in rows]}
        raise ValueError('未知操作')


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        catalog = Catalog(os.getenv('DODO_SKILL_CENTER_DB', str(DEFAULT_DB)))
        try:
            result = catalog.call(request['action'], request.get('args', {}))
        finally:
            catalog.db.close()
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True))
        sys.exit(1)
