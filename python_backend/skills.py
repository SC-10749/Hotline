from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import zipfile
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .config import Settings
from .skill_center import Catalog

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

    def _skill_dir(self, dir_name: str) -> Path:
        return self.root / dir_name

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
