"""阶段 1：跑仓库真实的 RAG，收集「答案 + 召回片段」。

    在仓库根目录、用主环境执行：
        uv run python eval/collect.py --cases eval/cases.jsonl --limit 5

产物：eval/runs/<时间戳>/samples.jsonl（阶段 2 的输入）

为什么单独一个阶段：
- 收集要 import python_backend，必须在主环境跑；
- 打分只需要 ragas，放在隔离环境（eval/.venv）；
- 分开之后可以换模型、换指标重打分，不用重跑检索和生成。
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 与 python_backend/agents.py 的 _fallback 保持一致。
# 主链路改 prompt 时这里要同步，否则评的不是线上那套。
SYSTEM_PROMPT = "你是 Hotline Agent，请用中文给出准确、结构清晰的回答。"


def build_prompt(query: str, contexts: list[str], route: str) -> str:
    context = "\n\n".join(contexts)
    return f"本次选择的召回链路：{route}\n请基于以下知识库内容回答问题：\n{context}\n\n问题：{query}"


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


def collect_one(engine, case: dict[str, Any]) -> dict[str, Any]:
    question = case["question"]
    source_id = case.get("source_id")
    record: dict[str, Any] = {
        "id": case["id"],
        "question": question,
        "reference": case.get("reference", ""),
        "source_id": source_id,
        "route": "",
        "contexts": [],
        "answer": "",
        "latency_ms": 0,
        "error": "",
    }
    started = time.perf_counter()
    try:
        # 复用主链路的两个步骤：路由分类 + 分路召回。
        route = engine._choose_retrieval(question)
        record["route"] = route
        if source_id:
            record["contexts"] = list(engine._retrieve(source_id, question, route))
        if not engine.settings.model_api_key:
            record["error"] = "未配置模型 Key，答案为空（上下文仍可用于检索侧指标）"
        else:
            record["answer"] = engine.model.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(question, record["contexts"], route)},
            ])
            if not record["answer"]:
                record["error"] = "模型返回空答案（被静默降级或调用失败）"
    except Exception as exc:  # 单条失败不拖垮整批
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return record


def mock_one(case: dict[str, Any]) -> dict[str, Any]:
    """不连数据库、不调模型，只验证管线是否通。"""
    question = case["question"]
    contexts = [f"（mock）与「{question}」相关的第 {i} 个片段" for i in range(1, 4)]
    return {
        "id": case["id"],
        "question": question,
        "reference": case.get("reference", ""),
        "source_id": case.get("source_id"),
        "route": "hybrid",
        "contexts": contexts,
        "answer": f"（mock）根据检索到的内容回答：{question}",
        "latency_ms": 1,
        "error": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="收集 RAG 答案与召回片段")
    parser.add_argument("--cases", default=str(Path(__file__).parent / "cases.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="", help="输出目录，默认 eval/runs/<时间戳>")
    parser.add_argument("--mock", action="store_true", help="不连库不调模型，只验证管线")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases), args.limit)
    if not cases:
        print("没有用例，先在 eval/cases.jsonl 里加几条", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else Path(__file__).parent / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = None
    settings = None
    if not args.mock:
        engine, settings = build_engine()
        print(f"storage={settings.storage_backend} vector={settings.vector_enabled} model={settings.model_name or '-'}")

    samples: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        record = mock_one(case) if args.mock else collect_one(engine, case)
        samples.append(record)
        mark = "ERR" if record["error"] else "ok "
        print(f"[{index}/{len(cases)}] {mark} {record['id']} route={record['route'] or '-'} "
              f"ctx={len(record['contexts'])} {record['latency_ms']}ms")

    samples_path = out_dir / "samples.jsonl"
    with samples_path.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "mock" if args.mock else "real",
        "cases_file": str(args.cases),
        "count": len(samples),
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
