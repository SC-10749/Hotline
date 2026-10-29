from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import zipfile
import logging
import hashlib
import threading
from urllib.parse import urlsplit
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .config import Settings
from .skill_center import Catalog, validate_resource_path

SKILL_FILENAME = "SKILL.md"
# Skill packages are usually zipped one or two directories deep (my-skill/ or
# my-skill-main/docs/), so a bounded depth walk finds it without scanning junk.
MAX_DEPTH = 3
MAX_ENTRIES = 500
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_BODY_CHARS = 8000
META_NAME = ".skill-meta.json"


class SkillError(Exception):
    def __init__(self, message: str, entries: list[str] | None = None):
        super().__init__(message)
        self.entries = entries or []


@dataclass
class Skill:
    id: str
    name: str
    description: str
    entry: str
    sourceFile: str
    enabled: bool = True
    createdAt: str = ""
    dirName: str = ""
    platformContent: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("dirName")
        return data


@dataclass(frozen=True)
class SkillDescriptor:
    id: str
    name: str
    description: str
    version: str | None
    entry_uri: str


@dataclass(frozen=True)
class _SkillSource:
    descriptor: SkillDescriptor
    root: Path | None = None
    entry: Path | None = None
    stamp: tuple[int, int, int] | None = None
    installed_id: str | None = None


def _file_stamp(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _read_skill_header(path: Path) -> dict[str, str]:
    lines = []
    with path.open('r', encoding='utf-8') as stream:
        first = stream.readline(8193)
        if first.strip() != '---':
            return {}
        lines.append(first)
        remaining = 8192 - len(first)
        while remaining > 0:
            line = stream.readline(remaining + 1)
            if not line or len(line) > remaining:
                return {}
            lines.append(line)
            remaining -= len(line)
            if line.strip() == '---':
                return parse_frontmatter(''.join(lines))[0]
    return {}


class SkillResourceSession:
    def __init__(self, registry: SkillRegistry, sources: list[_SkillSource], request_id: str):
        self.registry = registry
        self.request_id = request_id
        self.descriptors = tuple(source.descriptor for source in sources)
        self._sources = {source.descriptor.id: source for source in sources}
        self._texts: dict[str, str] = {}
        self._lock = threading.RLock()

    def read_skill(self, skill_id: str, path: str = 'SKILL.md', offset: int = 0, limit: int = 12000) -> dict:
        source = self._sources.get(skill_id) if isinstance(skill_id, str) else None
        if source is None or not isinstance(path, str) or not path or len(path) > 2048:
            return {'error': '技能资源不可读：请检查技能标识、相对路径或分页参数；技能变化后请重试。'}
        resource_uri = source.descriptor.entry_uri.rsplit('/', 1)[0] + '/' + path
        return self.read_file(resource_uri, offset, limit)

    def read_file(self, resource_uri: str, offset: int = 0, limit: int = 12000) -> dict:
        try:
            if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 12000:
                raise SkillError('分页参数无效')
            if not isinstance(resource_uri, str) or len(resource_uri) > 2048:
                raise SkillError('资源地址无效')
            parsed = urlsplit(resource_uri)
            if parsed.scheme != 'skill' or parsed.query or parsed.fragment or not parsed.path.startswith('/'):
                raise SkillError('仅允许已登记的技能资源地址')
            source = self._sources.get(parsed.netloc)
            if source is None:
                raise SkillError('技能资源未登记')
            relative = validate_resource_path(parsed.path[1:])
            with self._lock:
                if source.root is not None:
                    text = self._local_text(source, relative, resource_uri)
                else:
                    text = self._catalog_text(source, relative, resource_uri)
                if offset > len(text):
                    raise SkillError('读取位置超出文本范围')
                end = min(offset + limit, len(text))
                return {'uri': resource_uri, 'text': text[offset:end],
                        'next_offset': end if end < len(text) else None, 'eof': end == len(text)}
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, sqlite3.Error, SkillError):
            return {'error': '技能资源不可读：请检查地址、权限、文件类型或分页参数；技能变化后请重试。'}

    def _local_text(self, source: _SkillSource, relative: str, uri: str) -> str:
        if source.installed_id:
            current = self.registry.get(source.installed_id)
            if not current or not current.enabled:
                raise SkillError('技能已禁用')
            if self.registry.skill_file(current).resolve() != source.entry:
                raise SkillError('技能入口已变化')
        if not source.root.is_dir() or source.root.is_symlink() or not source.entry.is_file():
            raise SkillError('技能已移除')
        target = source.entry if relative == 'SKILL.md' else source.root / relative
        if not target.resolve().is_relative_to(source.root):
            raise SkillError('资源越界')
        if not target.is_file():
            raise SkillError('仅允许普通文本文件')
        cursor = target
        while cursor != source.root:
            if cursor.is_symlink():
                raise SkillError('不支持链接资源')
            cursor = cursor.parent
        if uri in self._texts:
            return self._texts[uri]
        if _file_stamp(source.entry) != source.stamp:
            raise SkillError('技能入口已变化，请重新开始')
        stamp = _file_stamp(target)
        with target.open('rb') as stream:
            content = stream.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024 or b'\x00' in content or _file_stamp(target) != stamp:
            raise SkillError('资源过大、非文本或读取期间变化')
        text = content.decode('utf-8')
        self._texts[uri] = text
        return text

    def _catalog_text(self, source: _SkillSource, relative: str, uri: str) -> str:
        catalog = Catalog.open_readonly(self.registry.settings.skill_catalog_db)
        try:
            if not catalog.call('authorize_runtime_skill', {
                'project': self.registry.settings.skill_project, 'name': source.descriptor.name,
                'version': source.descriptor.version,
            })['authorized']:
                raise SkillError('技能授权已撤销')
            if uri not in self._texts:
                result = catalog.call('read_runtime_file', {
                    'project': self.registry.settings.skill_project, 'requestId': self.request_id,
                    'name': source.descriptor.name, 'version': source.descriptor.version, 'path': relative,
                })
                self._texts[uri] = result['text']
            return self._texts[uri]
        finally:
            catalog.db.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or path.drive:
        return False
    return not any(part == ".." for part in path.parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise SkillError(f"压缩包文件数超过上限 {MAX_ENTRIES}")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise SkillError("压缩包解压后体积超过上限 50MB")
    root = dest.resolve()
    for info in infos:
        if not _safe_member(info.filename):
            raise SkillError(f"压缩包包含非法路径，已拒绝解压：{info.filename}")
        if _is_symlink(info):
            raise SkillError(f"压缩包包含软链接，已拒绝解压：{info.filename}")
        target = dest / PurePosixPath(info.filename.replace("\\", "/"))
        if not target.resolve().is_relative_to(root):
            raise SkillError(f"压缩包包含越界路径，已拒绝解压：{info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)


def locate_skill_md(root: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    """Return SKILL.md candidates at the shallowest depth within max_depth."""
    level = [root]
    for _ in range(max_depth):
        children: list[Path] = []
        found: list[Path] = []
        for directory in level:
            for child in sorted(directory.iterdir()):
                if child.is_file() and child.name.lower() == SKILL_FILENAME.lower():
                    found.append(child)
                elif child.is_dir():
                    children.append(child)
        if found:
            return found
        if not children:
            break
        level = children
    return []


def relative_entries(root: Path, limit: int = MAX_ENTRIES) -> list[str]:
    paths = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return [p for p in paths if p != META_NAME][:limit]


def deep_skill_candidates(root: Path, limit: int = MAX_ENTRIES) -> list[str]:
    """SKILL.md below MAX_DEPTH: the manual picker should offer these first."""
    return [p.relative_to(root).as_posix() for p in sorted(root.rglob(SKILL_FILENAME))][:limit]


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.lstrip()
    meta: dict[str, str] = {}
    # Deliberately minimal: SKILL.md frontmatter is flat "key: value" pairs, and
    # depending on PyYAML here would add an undeclared runtime requirement.
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("\"'")
        if key and value and key not in meta:
            meta[key] = value
    return meta, text[match.end():].lstrip()


_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD = re.compile(r"[0-9a-z]+")


def _match_grams(text: str) -> set[str]:
    """Chinese has no word boundaries, so match on CJK bigrams plus ASCII words."""
    lowered = text.lower()
    grams: set[str] = set()
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            grams.add(run)
        grams.update(run[i:i + 2] for i in range(len(run) - 1))
    grams.update(word for word in _ASCII_WORD.findall(lowered) if len(word) >= 3)
    return grams


class SkillRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.skills_dir
        self._metadata_lock = threading.RLock()
        self._descriptor_cache: dict[tuple[str, str], tuple[tuple[int, int, int], tuple[str, str] | None, SkillDescriptor]] = {}
        self._installed_metadata_cache: dict[str, tuple[tuple[int, int, int], Skill | None]] = {}

    def _skill_dir(self, dir_name: str) -> Path:
        return self.root / dir_name

    def open_resource_session(self, request_id: str) -> SkillResourceSession:
        with self._metadata_lock:
            return self._build_resource_session(request_id)

    def _build_resource_session(self, request_id: str) -> SkillResourceSession:
        sources: list[_SkillSource] = []
        seen_cache_keys: set[tuple[str, str]] = set()

        def local_source(entry: Path, name: str, description: str, key: str,
                         source_kind: str, installed_id: str | None = None) -> None:
            if not entry.is_file() or entry.is_symlink() or entry.parent.is_symlink():
                return None
            if not isinstance(name, str) or not isinstance(description, str):
                return None
            resolved_entry = entry.resolve()
            cache_key = (source_kind, str(resolved_entry))
            seen_cache_keys.add(cache_key)
            stamp = _file_stamp(entry)
            metadata_hint = (name, description) if source_kind == 'installed' else None
            cached = self._descriptor_cache.get(cache_key)
            if cached and cached[0] == stamp and cached[1] == metadata_hint:
                descriptor = cached[2]
            else:
                identity = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
                descriptor = SkillDescriptor(identity, name, description, None, f'skill://{identity}/SKILL.md')
                self._descriptor_cache[cache_key] = (stamp, metadata_hint, descriptor)
            sources.append(_SkillSource(descriptor, entry.parent.resolve(), entry.resolve(),
                                        _file_stamp(entry), installed_id))

        def repository_source(entry: Path, directory_name: str) -> None:
            if not entry.is_file() or entry.is_symlink() or entry.parent.is_symlink():
                return
            resolved_entry = entry.resolve()
            cache_key = ('repo', str(resolved_entry))
            seen_cache_keys.add(cache_key)
            stamp = _file_stamp(entry)
            cached = self._descriptor_cache.get(cache_key)
            if cached and cached[0] == stamp:
                descriptor = cached[2]
            else:
                metadata = _read_skill_header(entry)
                name, description = metadata.get('name'), metadata.get('description')
                if not name or not description:
                    self._descriptor_cache.pop(cache_key, None)
                    return
                identity = hashlib.sha256(f'repo:{directory_name}'.encode('utf-8')).hexdigest()[:24]
                descriptor = SkillDescriptor(identity, name, description, None, f'skill://{identity}/SKILL.md')
                self._descriptor_cache[cache_key] = (stamp, None, descriptor)
            sources.append(_SkillSource(descriptor, entry.parent.resolve(), resolved_entry, stamp))

        repo = Path(getattr(self.settings, 'repo_skills_dir', Path(__file__).resolve().parents[1] / 'skills'))
        if repo.is_dir():
            for directory in sorted(repo.iterdir()):
                entry = directory / SKILL_FILENAME
                if directory.is_symlink() or not directory.is_dir() or not entry.is_file() or entry.is_symlink():
                    continue
                try:
                    validate_resource_path(directory.name + '/SKILL.md')
                    repository_source(entry, directory.name)
                except (OSError, UnicodeError, ValueError):
                    continue
        installed_skills, installed_meta_paths = self._installed_skills_for_discovery()
        for skill in installed_skills:
            if skill.enabled:
                try:
                    validate_resource_path(skill.dirName + '/' + skill.entry)
                    entry = self.skill_file(skill)
                    if entry.resolve().is_relative_to(self.root.resolve()):
                        local_source(entry, skill.name, skill.description, 'installed:' + skill.id,
                                     'installed', skill.id)
                except (OSError, ValueError, TypeError):
                    continue
        self._descriptor_cache = {
            cache_key: cached for cache_key, cached in self._descriptor_cache.items()
            if cache_key[0] not in {'repo', 'installed'} or cache_key in seen_cache_keys
        }
        self._installed_metadata_cache = {
            key: cached for key, cached in self._installed_metadata_cache.items()
            if key in installed_meta_paths
        }
        if self.settings.skill_catalog_db.is_file():
            catalog = Catalog.open_readonly(self.settings.skill_catalog_db)
            try:
                rows = catalog.call('runtime_metadata', {
                    'project': self.settings.skill_project, 'requestId': request_id,
                })['skills']
                for row in rows:
                    identity = hashlib.sha256(f"catalog:{row['name']}:{row['version']}".encode()).hexdigest()[:24]
                    descriptor = SkillDescriptor(identity, row['name'], row['description'], row['version'],
                                                 f'skill://{identity}/SKILL.md')
                    sources.append(_SkillSource(descriptor))
            finally:
                catalog.db.close()
        return SkillResourceSession(self, sources, request_id)

    def _installed_skills_for_discovery(self) -> tuple[list[Skill], set[str]]:
        skills: list[Skill] = []
        seen: set[str] = set()
        if not self.root.is_dir() or self.root.is_symlink():
            return skills, seen
        for directory in sorted(self.root.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                continue
            meta = directory / META_NAME
            if meta.is_symlink() or not meta.is_file():
                continue
            try:
                key = str(meta.resolve())
                stamp = _file_stamp(meta)
                seen.add(key)
                cached = self._installed_metadata_cache.get(key)
                if cached and cached[0] == stamp:
                    skill = cached[1]
                else:
                    try:
                        skill = Skill(**json.loads(meta.read_text('utf-8')))
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        skill = None
                    self._installed_metadata_cache[key] = (stamp, skill)
                if skill is not None:
                    skills.append(skill)
            except OSError:
                continue
        return skills, seen

    def list(self) -> list[Skill]:
        if not self.root.exists():
            return []
        skills: list[Skill] = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir():
                continue
            meta = directory / META_NAME
            if not meta.exists():
                continue
            try:
                skills.append(Skill(**json.loads(meta.read_text("utf-8"))))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return skills

    def get(self, skill_id: str) -> Skill | None:
        return next((s for s in self.list() if s.id == skill_id), None)

    def enabled(self) -> list[Skill]:
        return [s for s in self.list() if s.enabled] + self.catalog_skills()

    def catalog_skills(self) -> list[Skill]:
        """Skills bound to this project in the local skill catalog (SQLite)."""
        try:
            catalog = Catalog(self.settings.skill_catalog_db)
            try:
                rows = catalog.call('runtime', {'project': self.settings.skill_project})['skills']
            finally:
                catalog.db.close()
            return [Skill(
                id='catalog:' + item['name'] + ':' + item['version'],
                name=item['name'], description=item['description'], entry='SKILL.md',
                sourceFile='技能中心', platformContent=item['content'],
            ) for item in rows]
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            logging.getLogger(__name__).warning('技能中心目录不可用: %s', exc)
            return []

    def install(self, content: bytes, source_file: str, entry: str | None = None) -> Skill:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise SkillError("文件不是有效的 zip 压缩包") from exc

        skill_id = uuid4().hex
        dir_name = skill_id
        target = self._skill_dir(dir_name)
        staging = self._skill_dir(f"{skill_id}.staging")
        target.mkdir(parents=True, exist_ok=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            with archive:
                safe_extract(archive, staging)
            candidates = locate_skill_md(staging)
            if entry:
                chosen = self._resolve_entry(staging, entry, candidates)
            elif len(candidates) == 1:
                chosen = candidates[0]
            elif candidates:
                raise SkillError(
                    "压缩包内有多个 SKILL.md，请手动指定使用哪一个",
                    [p.relative_to(staging).as_posix() for p in candidates],
                )
            else:
                deep = deep_skill_candidates(staging)
                raise SkillError(
                    f"未在压缩包前 {MAX_DEPTH} 层内找到 {SKILL_FILENAME}"
                    + ("，在更深层级发现了同名文件，请手动指定" if deep else "，请手动指定技能文件"),
                    deep or relative_entries(staging),
                )
            meta, _ = parse_frontmatter(chosen.read_text("utf-8", errors="replace"))
            rel_entry = chosen.relative_to(staging).as_posix()
            name = meta.get("name") or Path(rel_entry).parent.name or skill_id[:8]
            skill = Skill(
                id=skill_id,
                name=name,
                description=meta.get("description", ""),
                entry=rel_entry,
                sourceFile=source_file,
                enabled=True,
                createdAt=_now(),
                dirName=dir_name,
            )
            (staging / META_NAME).write_text(json.dumps(asdict(skill), ensure_ascii=False, indent=2), "utf-8")
            shutil.rmtree(target, ignore_errors=True)
            staging.rename(target)
            return skill
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            if not any(target.iterdir()):
                target.rmdir()
            raise

    @staticmethod
    def _resolve_entry(staging: Path, entry: str, candidates: list[Path]) -> Path:
        wanted = PurePosixPath(entry.replace("\\", "/"))
        if not _safe_member(entry):
            raise SkillError(f"非法的技能路径：{entry}")
        resolved = (staging / wanted).resolve()
        if not resolved.is_relative_to(staging.resolve()) or not resolved.is_file():
            raise SkillError(f"指定的技能文件不存在：{entry}")
        if resolved.name.lower() != SKILL_FILENAME.lower():
            raise SkillError(f"指定的文件不是 {SKILL_FILENAME}")
        # Keep the unresolved path: callers compare it against `staging`, which is
        # relative when SKILLS_DIRECTORY is left at its default.
        return staging / wanted

    def delete(self, skill_id: str) -> bool:
        skill = self.get(skill_id)
        if not skill:
            return False
        shutil.rmtree(self._skill_dir(skill.dirName), ignore_errors=True)
        return True

    def set_enabled(self, skill_id: str, enabled: bool) -> Skill | None:
        skill = self.get(skill_id)
        if not skill:
            return None
        meta = self._skill_dir(skill.dirName) / META_NAME
        data = json.loads(meta.read_text("utf-8"))
        data["enabled"] = enabled
        meta.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        skill.enabled = enabled
        return skill

    def skill_file(self, skill: Skill) -> Path:
        return self._skill_dir(skill.dirName) / PurePosixPath(skill.entry)

    def select(self, query: str) -> Skill | None:
        """Pick the skill whose name/description best matches the query."""
        pool = self.enabled()
        if not pool:
            return None
        explicit = re.findall(r'\$([a-z0-9]+(?:-[a-z0-9]+)*)', query.lower())
        if explicit:
            return next((s for s in pool if s.name in explicit), None)
        asked = _match_grams(query)
        scored: list[tuple[int, Skill]] = []
        for skill in pool:
            score = 2 * len(asked & _match_grams(skill.name)) + len(asked & _match_grams(skill.description))
            if score >= 2:
                scored.append((score, skill))
        if scored:
            return max(scored, key=lambda item: item[0])[1]
        return pool[0] if len(pool) == 1 else None

    def prompt_block(self, skill: Skill) -> str:
        if skill.platformContent:
            _, body = parse_frontmatter(skill.platformContent)
            return (f"正在执行技能中心技能「{skill.name}」，版本 {skill.id.rsplit(':', 1)[-1]}。\n"
                    "当前运行器只加载技能指令，不具备脚本执行或平台资源文件读取工具。"
                    "若任务需要这些能力，请明确说明缺少的能力，不要声称已执行。\n\n" + body)
        try:
            _, body = parse_frontmatter(self.skill_file(skill).read_text("utf-8", errors="replace"))
        except OSError:
            body = ""
        directory = self._skill_dir(skill.dirName)
        return (
            f"你正在执行技能「{skill.name}」。技能说明目录：{directory}\n"
            f"请严格遵循以下技能定义来完成用户请求，需要引用包内文件时使用该目录下的相对路径。\n\n"
            f"{body[:MAX_BODY_CHARS]}"
        )
