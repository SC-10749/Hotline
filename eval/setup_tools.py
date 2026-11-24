"""Download a versioned, unmodified BIRD Mini-Dev scorer, without a nested repo."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    headers = {'User-Agent': 'Hotline-benchmark-setup'}
    url = 'https://api.github.com/repos/bird-bench/mini_dev/commits/main'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        revision = json.load(response)['sha']
    target = ROOT / 'data/benchmarks/bird-tool'
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ('evaluation_ex.py', 'evaluation_utils.py'):
        source = f'https://raw.githubusercontent.com/bird-bench/mini_dev/{revision}/evaluation/{name}'
        with urllib.request.urlopen(source, timeout=30) as response:
            content = response.read()
        (target / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    (target / 'version.json').write_text(json.dumps({'repository': 'bird-bench/mini_dev',
        'revision': revision, 'sha256': files}, indent=2), encoding='utf-8')
    print('BIRD scorer installed in data/benchmarks/bird-tool; dataset is downloaded separately.')


if __name__ == '__main__':
    main()
