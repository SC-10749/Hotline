"""Import fetched samples as unbound research versions."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_backend.skill_center import Catalog


def main():
    root = Path(__file__).resolve().parent / 'samples'
    catalog = Catalog()
    try:
        for source in json.loads((root / 'sources.json').read_text('utf-8')):
            folder = root / source['name']
            resources = {}
            for path in sorted(folder.rglob('*')):
                if path.is_file() and path.name != 'SKILL.md':
                    try:
                        resources[path.relative_to(folder).as_posix()] = path.read_text('utf-8')
                    except UnicodeDecodeError:
                        continue  # Original binary assets remain in samples/.
            print(json.dumps(catalog.call('save', {
                'content': (folder / 'SKILL.md').read_text('utf-8'),
                'resources': resources, 'source': source,
            })))
    finally:
        catalog.db.close()


if __name__ == '__main__':
    main()
