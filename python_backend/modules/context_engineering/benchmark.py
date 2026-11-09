"""Reproducible local capacity/recall benchmark over synthetic cl100k_base chunks."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from ..retrieval.workspace_index import WorkspaceIndex


def run_benchmark(directory: Path, tokens: int, *, queries: int = 40) -> dict:
    import tiktoken

    if tokens < 1000 or queries < 1:
        raise ValueError('tokens 至少 1000，queries 至少 1')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / 'capacity.db'
    if database.exists():
        raise ValueError('验收目录已有数据库，请使用新的目录以保留原报告')
    encoder = tiktoken.get_encoding('cl100k_base')
    index = WorkspaceIndex(database)
    rng = random.Random(20261109)
    started = time.perf_counter()
    actual = 0
    source_count = 0
    chunk_count = 0
    probes = []
    hashes = {}
    while actual < tokens:
        source = f'doc:capacity-{source_count:06d}'
        chunks = []
        for _ in range(128):
            if actual >= tokens:
                break
            identity = f'RECORD{chunk_count:08d}'
            prefix = f'{identity} retention {30 + chunk_count % 97} days.\n'
            prefix_tokens = len(encoder.encode(prefix))
            filler = max(0, min(800, tokens - actual) - prefix_tokens)
            content = prefix + ' a' * filler
            encoded = encoder.encode(content)
            if len(encoded) > tokens - actual:
                content = encoder.decode(encoded[:tokens - actual])
            count = len(encoder.encode(content))
            actual += count
            chunks.append(content)
            if len(probes) < queries or rng.random() < queries / (chunk_count + 1):
                sample = (identity, source)
                if len(probes) < queries:
                    probes.append(sample)
                else:
                    probes[rng.randrange(queries)] = sample
            chunk_count += 1
        index.index_source('capacity', source, chunks, marker='synthetic-v1')
        hashes[source] = hashlib.sha256('\n'.join(text.strip() for text in chunks).encode()).hexdigest()
        source_count += 1
        if source_count % 100 == 0:
            print(json.dumps({'indexedTokens': actual, 'targetTokens': tokens, 'sources': source_count}), flush=True)
    index_seconds = time.perf_counter() - started
    latencies = []
    recalled = 0
    for query, expected in probes:
        before = time.perf_counter()
        hits = index.search_sources('capacity', query, limit=8)
        latencies.append((time.perf_counter() - before) * 1000)
        recalled += any(source == expected for source, _ in hits)
    recovered = 0
    sampled = rng.sample(list(hashes), min(5, len(hashes)))
    for source in sampled:
        offset = 0
        parts = []
        while True:
            page = index.read_source('capacity', source, offset=offset, limit=12000)
            parts.append(page['content'])
            if page['next_offset'] is None:
                break
            offset = page['next_offset']
        recovered += hashlib.sha256(''.join(parts).encode()).hexdigest() == hashes[source]
    ordered = sorted(latencies)
    with index.db() as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    result = {
        'schemaVersion': 1, 'corpus': 'synthetic-repeated-ascii', 'backend': 'sqlite-fts5',
        'tokenizer': 'cl100k_base', 'tokenCountMethod': 'sum-of-indexed-chunk-token-counts',
        'targetTokens': tokens, 'indexedTokens': actual, 'sources': source_count, 'chunks': chunk_count,
        'indexSeconds': round(index_seconds, 3), 'indexBytes': database.stat().st_size,
        'queries': len(probes), 'recallAt8': recalled / len(probes),
        'retrievalP50Ms': round(statistics.median(latencies), 3),
        'retrievalP95Ms': round(ordered[max(0, int(len(ordered) * .95) - 1)], 3),
        'sourceRecoverySamples': len(sampled), 'sourceRecoveryRate': recovered / len(sampled),
        'workspaceIsolationPassed': not index.search_sources('foreign-workspace', probes[0][0]),
        'providerCalls': 0, 'semanticQualityMeasured': False, 'openVikingMeasured': False,
    }
    result['passed'] = (actual >= tokens and result['recallAt8'] >= .95
                        and result['sourceRecoveryRate'] == 1 and result['workspaceIsolationPassed'])
    (directory / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokens', type=int, default=1000000)
    parser.add_argument('--queries', type=int, default=40)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_benchmark(args.output, args.tokens, queries=args.queries)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
