"""Fetch complete sample folders at a pinned GitHub commit; never execute them."""
import io
import json
import urllib.request
import zipfile
from pathlib import Path

REPO = 'anthropics/skills'
NAMES = ['frontend-design', 'webapp-testing', 'mcp-builder', 'skill-creator']
DEST = Path(__file__).resolve().parent / 'samples'


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'HotlineAgent-Skill-Research'}), timeout=90) as response:
        return response.read()


def main():
    commit = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    archive = zipfile.ZipFile(io.BytesIO(fetch(f'https://codeload.github.com/{REPO}/zip/{commit}')))
    prefix = f'skills-{commit}/'
    records = []
    for name in NAMES:
        target = DEST / name
        target.mkdir(parents=True, exist_ok=True)
        start = prefix + f'skills/{name}/'
        count = 0
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith(start):
                continue
            relative = Path(entry.filename[len(start):])
            path = target / relative
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError('Invalid archive path')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(entry))
            count += 1
        if not (target / 'SKILL.md').is_file():
            raise ValueError(f'Missing sample: {name}')
        records.append({'name': name, 'repository': f'https://github.com/{REPO}', 'commit': commit, 'path': f'skills/{name}', 'files': count})
    for name in ['LICENSE', 'LICENSE.txt', 'README.md']:
        if prefix + name in archive.namelist():
            (DEST / ('UPSTREAM-' + name)).write_bytes(archive.read(prefix + name))
    (DEST / 'sources.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()

