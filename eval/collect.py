"""阶段 1：跑真实 RAG，收集「答案 + 召回片段 + 用的哪版提示词」。

    在仓库根目录、用主环境执行：
        uv run python eval/collect.py --limit 5
        uv run python eval/collect.py --limit 5 --prompt current,cited   # 提示词 A/B

产物：eval/runs/<时间戳>/samples.jsonl（阶段 2 的输入）

设计要点：
- 每个用例只检索一次，所有提示词变体共用同一份召回 —— 比较的是提示词，不是检索波动。
- 每条样本记录 prompt_variant 和 prompt_sha：分数掉了先看指纹变没变。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = Path(__file__).resolve().parent
for path in (ROOT, EVAL_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import prompts  # noqa: E402  (同目录模块，需先补 sys.path)


def load_cases(path: Path, limit: int | None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except ValueError as exc:
            raise SystemExit(f"{path}:{number} 不是合法 JSON：{exc}") from exc
        if "question" not in case:
            raise SystemExit(f"{path}:{number} 缺少 question 字段")
        case.setdefault("id", f"case-{number:03d}")
        cases.append(case)
    return cases[:limit] if limit else cases


def build_engine():
    """按 .env 组装真实的 AgentEngine（和线上同一套对象）。"""
    from python_backend.bootstrap import load_environment

    load_environment()

    from python_backend.agents import AgentEngine, TaskManager
    from python_backend.config import settings
    from python_backend.documents import DocumentService
    from python_backend.object_store import ObjectStorage
    from python_backend.skills import SkillRegistry
    from python_backend.storage import Storage
    from python_backend.vector_store import PgVectorStore

    settings.ensure_dirs()
    storage = Storage(settings)
    store = ObjectStorage(settings)
    vector = PgVectorStore(settings)
    skills = SkillRegistry(settings)
    documents = DocumentService(settings, storage, store, vector)
    engine = AgentEngine(settings, storage, TaskManager(settings), vector, skills, documents)
    return engine, settings


def retrieve(engine, question: str, source_id: str | None) -> tuple[str, list[str]]:
    """复用主链路的两个步骤：路由分类 + 分路召回。"""
    route = engine._choose_retrieval(question)
    contexts = list(engine._retrieve(source_id, question, route)) if source_id else []
    return route, contexts


def collect_case(engine, case: dict[str, Any], variants: list[prompts.PromptVariant]) -> list[dict[str, Any]]:
    question = case["question"]
    source_id = case.get("source_id")
    started = time.perf_counter()

    route, contexts, error = "", [], ""
    try:
        route, contexts = retrieve(engine, question, source_id)
    except Exception as exc:
        error = f"检索失败 {type(exc).__name__}: {exc}"
    retrieval_ms = int((time.perf_counter() - started) * 1000)

    rows = []
    for variant in variants:
        row = {
            "id": case["id"],
            "question": question,
            "reference": case.get("reference", ""),
            "source_id": source_id,
            "prompt_variant": variant.name,
            "prompt_sha": variant.fingerprint(),
            "route": route,
            "contexts": contexts,
            "answer": "",
            "latency_ms": retrieval_ms,
            "error": error,
        }
        if not error and engine.settings.model_api_key:
            begin = time.perf_counter()
            try:
                row["answer"] = engine.model.chat(prompts.render(variant, question, contexts, route))
                if not row["answer"]:
                    row["error"] = "模型返回空答案（被静默降级或调用失败）"
            except Exception as exc:
                row["error"] = f"生成失败 {type(exc).__name__}: {exc}"
            row["latency_ms"] = int((time.perf_counter() - begin) * 1000)
        elif not error:
            row["error"] = "未配置模型 Key，答案为空（上下文仍可用于检索侧指标）"
        rows.append(row)
    return rows


def mock_case(case: dict[str, Any], variants: list[prompts.PromptVariant]) -> list[dict[str, Any]]:
    """不连数据库、不调模型，只验证管线是否通。"""
    question = case["question"]
    contexts = [f"与「{question}」相关的第 {i} 个片段" for i in range(1, 4)]
    return [{
        "id": case["id"],
        "question": question,
        "reference": case.get("reference", ""),
        "source_id": case.get("source_id"),
        "prompt_variant": variant.name,
        "prompt_sha": variant.fingerprint(),
        "route": "hybrid",
        "contexts": contexts,
        "answer": f"（mock:{variant.name}）根据检索内容回答：{question}",
        "latency_ms": 1,
        "error": "",
    } for variant in variants]


def main() -> int:
    parser = argparse.ArgumentParser(description="收集 RAG 答案与召回片段（支持提示词 A/B）")
    parser.add_argument("--cases", default=str(EVAL_DIR / "cases.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--prompt", default="current", help="提示词变体，逗号分隔：current,cited")
    parser.add_argument("--list-prompts", action="store_true", help="列出所有变体后退出")
    parser.add_argument("--out", default="", help="输出目录，默认 eval/runs/<时间戳>")
    parser.add_argument("--mock", action="store_true", help="不连库不调模型，只验证管线")
    args = parser.parse_args()

    if args.list_prompts:
        for variant in prompts.VARIANTS.values():
            print(f"{variant.name:12} sha={variant.fingerprint()}  {variant.description}")
        return 0

    names = [name.strip() for name in args.prompt.split(",") if name.strip()]
    variants = [prompts.get(name) for name in names]

    cases = load_cases(Path(args.cases), args.limit)
    if not cases:
        print("没有用例，先在 eval/cases.jsonl 里加几条", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else EVAL_DIR / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = settings = None
    if not args.mock:
        engine, settings = build_engine()
        print(f"storage={settings.storage_backend} vector={settings.vector_enabled} "
              f"model={settings.model_name or '-'} prompts={','.join(names)}")

    samples: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        rows = mock_case(case, variants) if args.mock else collect_case(engine, case, variants)
        samples.extend(rows)
        for row in rows:
            mark = "ERR" if row["error"] else "ok "
            print(f"[{index}/{len(cases)}] {mark} {row['id']}/{row['prompt_variant']} "
                  f"route={row['route'] or '-'} ctx={len(row['contexts'])} {row['latency_ms']}ms")

    samples_path = out_dir / "samples.jsonl"
    with samples_path.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "mock" if args.mock else "real",
        "cases_file": str(args.cases),
        "cases": len(cases),
        "samples": len(samples),
        "prompts": {v.name: v.fingerprint() for v in variants},
        "errors": sum(1 for s in samples if s["error"]),
        "storage": getattr(settings, "storage_backend", "-"),
        "vector_enabled": getattr(settings, "vector_enabled", "-"),
        "model": getattr(settings, "model_name", "-"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n样本已写入 {samples_path}")
    print(f"下一步：eval\\.venv\\Scripts\\python.exe eval/score.py --samples \"{samples_path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
