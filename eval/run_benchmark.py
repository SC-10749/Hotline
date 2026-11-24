"""On-demand subprocess entrypoint for Harness benchmark jobs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_backend.modules.evaluation.benchmarks import BenchmarkService
from python_backend.modules.context_engineering.privacy import sanitize_value


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')


def command(args, env=None):
    subprocess.run([str(a) for a in args], cwd=ROOT, env=env, check=True, timeout=3300)


def retrieval_metrics(samples, k=5):
    values = []
    for sample in samples:
        relevant = set(sample.get('relevant_ids') or [])
        if not relevant:
            continue
        retrieved = list(dict.fromkeys(sample.get('retrieved_ids') or []))[:k]
        first = next((i + 1 for i, value in enumerate(retrieved) if value in relevant), None)
        values.append((len(relevant.intersection(retrieved)) / len(relevant), 1 / first if first else 0))
    return {'recallAt5': sum(v[0] for v in values) / len(values),
            'mrrAt5': sum(v[1] for v in values) / len(values), 'labelledCases': len(values)} if values else {}


def rag(service, spec, folder):
    source = service.input_path(spec['input'])
    if spec['collect']:
        command([sys.executable, ROOT / 'eval/collect.py', '--cases', source,
                 '--limit', spec['limit'], '--out', folder])
        source = folder / 'samples.jsonl'
    samples = [json.loads(line) for line in source.read_text('utf-8').splitlines() if line.strip()][:spec['limit']]
    if not samples:
        raise ValueError('样本为空')
    for i, sample in enumerate(samples):
        if not isinstance(sample.get('question'), str) or not isinstance(sample.get('answer'), str):
            raise ValueError('RAG 样本需要 question、answer 和 contexts 字段')
        if not isinstance(sample.get('contexts'), list) or not all(isinstance(c, str) for c in sample['contexts']):
            raise ValueError('contexts 必须是字符串列表')
        sample.setdefault('id', str(i))
    safe_samples = folder / 'judge-samples.jsonl'
    safe_samples.write_text('\n'.join(json.dumps(sanitize_value(s), ensure_ascii=False) for s in samples), 'utf-8')
    command([service.python, ROOT / 'eval/score.py', '--samples', safe_samples, '--out', folder])
    scores = read_json(folder / 'scores.json')
    count = sum(bool(r['scores']) for r in scores['rows'])
    return {'sampleCount': len(samples), 'scoredCases': count,
            'unscoredCases': len(samples) - count,
            'variants': {k: v['summary'] for k, v in scores['variants'].items()},
            'retrieval': retrieval_metrics(samples), 'scope': 'RAG 组件评测'}


def bird(service, spec, folder):
    source = service.input_path(spec['input'])
    text = source.read_text('utf-8')
    cases = json.loads(text) if text.lstrip().startswith('[') else [json.loads(s) for s in text.splitlines() if s.strip()]
    cases = cases[:spec['limit']]
    if not cases:
        raise ValueError('BIRD 样本为空')
    if {c.get('difficulty') for c in cases} != {'simple', 'moderate', 'challenging'}:
        raise ValueError('官方 Mini-Dev EX 脚本要求样本覆盖 simple、moderate、challenging 三类，请增加样本数')
    databases = service.input_path(spec['databases'], directory=True)
    for case in cases:
        db_id = case['db_id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', db_id):
            raise ValueError('非法数据库标识')
        db = (databases / db_id / f'{db_id}.sqlite').resolve()
        if not db.is_relative_to(databases) or not db.is_file():
            raise ValueError('BIRD 数据库不存在')
    predictions = {}
    if spec.get('predictions'):
        provided = read_json(service.input_path(spec['predictions']))
        for i, case in enumerate(cases):
            key = str(case.get('question_id', i))
            if key not in provided or not isinstance(provided[key], str):
                raise ValueError('预测文件必须按 question_id 提供每道题的 SQL 字符串')
            predictions[str(i)] = provided[key].split('\t----- bird -----\t')[0] + '\t----- bird -----\t' + case['db_id']
        mode = '已有预测 SQL'
    else:
        from python_backend.bootstrap import load_environment
        load_environment()
        from python_backend.config import settings
        from python_backend.llm import model_ready
        from python_backend.modules.execution.engine import ModelClient
        if not model_ready(settings):
            raise ValueError('未配置 SQL 生成模型；也可提供已有预测文件')
        model = ModelClient(settings)
        for i, case in enumerate(cases):
            db_id = case['db_id']
            with closing(sqlite3.connect((databases / db_id / f'{db_id}.sqlite').as_uri() + '?mode=ro', uri=True)) as connection:
                schema = '\n'.join(r[0] for r in connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"))
            prompt = {'schema': schema, 'question': case['question'],
                      'evidence': case.get('evidence', '') if spec['evidence'] else ''}
            sql = model.chat([{'role': 'system', 'content': 'Generate one read-only SQLite SELECT query. Output SQL only.'},
                              {'role': 'user', 'content': json.dumps(sanitize_value(prompt), ensure_ascii=False)}]).strip()
            sql = re.sub(r'^```(?:sql)?\s*|\s*```$', '', sql, flags=re.I).strip()
            if not sql:
                raise ValueError('SQL 模型返回空结果')
            predictions[str(i)] = sql + '\t----- bird -----\t' + db_id
        mode = '单次模型生成 SQL（非完整 SQL Agent）'
    tool = service.inputs / 'bird-tool'
    version = read_json(tool / 'version.json')
    for name in ('evaluation_ex.py', 'evaluation_utils.py'):
        if hashlib.sha256((tool / name).read_bytes()).hexdigest() != version['sha256'][name]:
            raise ValueError('BIRD 官方评分脚本与安装版本不一致，请重新安装')
    write_json(folder / 'predictions.json', predictions)
    (folder / 'gold.sql').write_text(''.join(c['SQL'].replace('\n', ' ').replace('\t', ' ') + '\t' + c['db_id'] + '\n' for c in cases), 'utf-8')
    (folder / 'questions.jsonl').write_text('\n'.join(json.dumps(c) for c in cases), 'utf-8')
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'eval/bird_guard'), PYTHONUTF8='1')
    command([service.python, tool / 'evaluation_ex.py', '--predicted_sql_path', folder / 'predictions.json',
             '--ground_truth_path', folder / 'gold.sql', '--db_root_path', str(databases) + os.sep,
             '--diff_json_path', folder / 'questions.jsonl', '--num_cpus', '1', '--meta_time_out', '15',
             '--sql_dialect', 'SQLite', '--output_log_path', folder / 'official.txt'], env)
    report = (folder / 'official.txt').read_text('utf-8')
    match = re.search(r'^EX\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', report, re.M)
    if not match:
        raise ValueError('官方 EX 报告未产出有效指标')
    return {'sampleCount': len(cases), 'executionAccuracy': float(match[4]) / 100,
            'difficultyAccuracy': {k: float(v) / 100 for k, v in zip(('simple', 'moderate', 'challenging'), match.groups()[:3])},
            'birdRevision': version['revision'], 'datasetSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'evidence': None if spec.get('predictions') else spec['evidence'],
            'scope': mode, 'dialect': 'SQLite'}


def load(service, spec, folder):
    target = 'http://127.0.0.1:' + ('8888' if spec['target'] == 'python' else '8080')
    env = dict(os.environ, HOTLINE_LOAD_PROFILE=spec['profile'], HOTLINE_LOAD_OUTPUT=str(folder))
    command([service.python, '-m', 'locust', '-f', ROOT / 'eval/locustfile.py', '--headless',
             '--host', target, '--users', spec['users'], '--spawn-rate', spec['spawnRate'],
             '--run-time', f"{spec['duration']}s", '--stop-timeout', '5',
             '--csv', folder / 'locust', '--only-summary', '--exit-code-on-error', '0'], env)
    summary = read_json(folder / 'load-summary.json')
    summary.update(target=spec['target'], profile=spec['profile'], users=spec['users'])
    detail = folder / 'stream-summary.json'
    if detail.is_file():
        summary['stream'] = read_json(detail)
    if not summary['requestCount']:
        raise ValueError('没有完成的请求，请检查目标服务和运行时长')
    return summary


def main():
    path = Path(sys.argv[1]).resolve()
    job = read_json(path)
    service = BenchmarkService(Path(os.environ.get('HOTLINE_BENCHMARK_DATA', ROOT / 'data')), recover=False)
    try:
        summary = {'rag': rag, 'bird': bird, 'load': load}[job['kind']](service, job['spec'], path.parent)
        write_json(path.parent / 'result.json', {'summary': summary})
        return 0
    except Exception as exc:
        # Exception text can contain credentials from upstream SDKs; keep details local.
        print(f'Benchmark failed: {type(exc).__name__}', file=sys.stderr)
        message = str(exc) if isinstance(exc, ValueError) else '工具执行失败，请检查本地依赖、数据集与模型配置'
        write_json(path.parent / 'result.json', {'error': sanitize_value(message), 'summary': {}})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
