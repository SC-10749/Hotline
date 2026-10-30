"""阶段 2：用 Ragas 给采集到的样本打分。

    用隔离环境执行（不要用主环境，ragas 会和 langchain 版本打架）：
        eval\\.venv\\Scripts\\python.exe eval/score.py --samples "eval/runs/<时间戳>/samples.jsonl"

产物：report.md（人看）+ scores.json（机器比基线用）

默认三个指标：
- Faithfulness                     答案是否有上下文依据（反幻觉）
- ContextPrecisionWithoutReference 召回片段的相关性排序（不需要标准答案）
- AnswerRelevancy                  是否答非所问（需要 embedding 配置，没配就自动跳过）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent


def read_env_file() -> None:
    """读仓库根目录的 .env，不覆盖已有环境变量（沿用主项目的配置习惯）。"""
    env_path = Path(os.environ.get("DODO_ENV_FILE", ROOT / ".env"))
    if not env_path.is_file():
        return
    for line in env_path.read_text("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def pick(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def load_samples(path: Path) -> list[dict[str, Any]]:
    samples = []
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if line:
            samples.append(json.loads(line))
    return samples


def build_metrics(judge_model: str, judge_base: str, judge_key: str, embedding_model: str):
    from openai import AsyncOpenAI
    from ragas.embeddings import OpenAIEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithoutReference,
        Faithfulness,
    )

    client = AsyncOpenAI(base_url=judge_base or None, api_key=judge_key)
    llm = llm_factory(judge_model, client=client)

    scorers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    faithfulness = Faithfulness(llm=llm)
    scorers["faithfulness"] = lambda s: faithfulness.ascore(
        user_input=s["question"], response=s["answer"], retrieved_contexts=s["contexts"])
    precision = ContextPrecisionWithoutReference(llm=llm)
    scorers["context_precision"] = lambda s: precision.ascore(
        user_input=s["question"], response=s["answer"], retrieved_contexts=s["contexts"])

    if embedding_model:
        embeddings = OpenAIEmbeddings(
            client=AsyncOpenAI(base_url=pick("EVAL_EMBEDDING_BASE_URL", "DODO_EMBEDDING_BASE_URL") or None,
                               api_key=pick("EVAL_EMBEDDING_API_KEY", "DODO_EMBEDDING_API_KEY", "DASHSCOPE_API_KEY")),
            model=embedding_model)
        relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)
        scorers["answer_relevancy"] = lambda s: relevancy.ascore(
            user_input=s["question"], response=s["answer"])
    else:
        print("提示：未配置 EVAL_EMBEDDING_MODEL，跳过 answer_relevancy", file=sys.stderr)
    return scorers


async def score_all(samples, scorers, concurrency: int) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(sample: dict[str, Any]) -> dict[str, Any]:
        row = {"id": sample["id"], "question": sample["question"], "route": sample.get("route", ""),
               "contexts": len(sample.get("contexts") or []), "latency_ms": sample.get("latency_ms", 0),
               "scores": {}, "reasons": {}, "skipped": [], "error": sample.get("error", "")}
        if not sample.get("answer"):
            row["skipped"].append("空答案，跳过全部生成侧指标")
            return row
        if not sample.get("contexts"):
            row["skipped"].append("无召回片段，跳过上下文侧指标")
        async with semaphore:
            for name, scorer in scorers.items():
                if name in {"faithfulness", "context_precision"} and not sample.get("contexts"):
                    continue
                try:
                    result = await scorer(sample)
                    row["scores"][name] = float(getattr(result, "value", result))
                    reason = getattr(result, "reason", "")
                    if reason:
                        row["reasons"][name] = str(reason)[:400]
                except Exception as exc:
                    row["skipped"].append(f"{name}: {type(exc).__name__}: {exc}"[:200])
        return row

    return await asyncio.gather(*(one(sample) for sample in samples))


def summarize(rows: list[dict[str, Any]], metric_names: list[str]) -> dict[str, Any]:
    summary = {}
    for name in metric_names:
        values = [row["scores"][name] for row in rows if name in row["scores"]]
        if values:
            summary[name] = {"mean": round(statistics.fmean(values), 4), "min": round(min(values), 4),
                             "max": round(max(values), 4), "n": len(values)}
    return summary


def write_report(out_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any],
                 meta: dict[str, Any], baseline: dict[str, Any] | None, note: str) -> Path:
    lines = ["# RAGAS 评测报告", ""]
    lines.append(f"- 时间：{meta['created_at']}")
    if note:
        lines.append(f"- 备注：{note}")
    lines.append(f"- 样本数：{len(rows)}（采集时报错 {meta.get('errors', 0)} 条）")
    lines.append(f"- 判分模型：{meta.get('judge_model', '-')}")
    lines.append("")

    lines += ["## 汇总", "", "| 指标 | 均值 | 最低 | 最高 | 样本 | 对比基线 |", "|---|---|---|---|---|---|"]
    for name, stats in summary.items():
        delta = ""
        if baseline and name in baseline.get("summary", {}):
            old = baseline["summary"][name]["mean"]
            change = stats["mean"] - old
            arrow = "↑" if change > 0.005 else ("↓" if change < -0.005 else "→")
            delta = f"{old:.3f} → {stats['mean']:.3f} {arrow}{abs(change):.3f}"
        lines.append(f"| {name} | {stats['mean']:.3f} | {stats['min']:.3f} | {stats['max']:.3f} | {stats['n']} | {delta} |")
    lines.append("")

    metric_names = list(summary.keys())
    header = "| 用例 | 路由 | 片段 | 耗时 | " + " | ".join(metric_names) + " | 备注 |"
    lines += ["## 逐条", "", header, "|" + "---|" * (len(metric_names) + 5)]
    for row in rows:
        cells = [f"{row['scores'][m]:.3f}" if m in row["scores"] else "—" for m in metric_names]
        remark = row["error"] or "；".join(row["skipped"])
        lines.append(f"| {row['id']} | {row['route'] or '-'} | {row['contexts']} | {row['latency_ms']}ms | "
                     + " | ".join(cells) + f" | {remark[:80]} |")
    lines.append("")

    low = sorted((r for r in rows if "faithfulness" in r["scores"]), key=lambda r: r["scores"]["faithfulness"])[:5]
    if low:
        lines += ["## 最低分样本（看原因）", ""]
        for row in low:
            reason = row["reasons"].get("faithfulness", "")
            lines.append(f"- **{row['id']}** faithfulness={row['scores']['faithfulness']:.3f} — {reason or '无原因'}")
    report = out_dir / "report.md"
    report.write_text("\n".join(lines) + "\n", "utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="用 Ragas 给采集样本打分")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--out", default="", help="输出目录，默认与 samples 同级")
    parser.add_argument("--note", default="")
    parser.add_argument("--baseline", default="", help="基线 scores.json，用于对比")
    parser.add_argument("--set-baseline", action="store_true", help="把本次结果写成 baseline.json")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    read_env_file()
    samples_path = Path(args.samples)
    if not samples_path.is_file():
        print(f"找不到样本文件：{samples_path}", file=sys.stderr)
        return 2
    samples = load_samples(samples_path)
    out_dir = Path(args.out) if args.out else samples_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    judge_model = pick("EVAL_JUDGE_MODEL", "DODO_MODEL", default="")
    judge_base = pick("EVAL_JUDGE_BASE_URL", "OPENAI_BASE_URL", default="")
    judge_key = pick("EVAL_JUDGE_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", default="")
    embedding_model = pick("EVAL_EMBEDDING_MODEL", "DODO_EMBEDDING_MODEL", default="")
    if not judge_model or not judge_key:
        print("缺判分模型配置：设 EVAL_JUDGE_MODEL / EVAL_JUDGE_API_KEY（或复用 DODO_MODEL / DEEPSEEK_API_KEY）",
              file=sys.stderr)
        return 2

    scorers = build_metrics(judge_model, judge_base, judge_key, embedding_model)
    rows = asyncio.run(score_all(samples, scorers, args.concurrency))
    summary = summarize(rows, list(scorers.keys()))

    baseline = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.is_file():
            baseline = json.loads(baseline_path.read_text("utf-8"))

    meta = {"created_at": datetime.now().isoformat(timespec="seconds"), "judge_model": judge_model,
            "embedding_model": embedding_model or "(未启用)", "count": len(samples),
            "errors": sum(1 for s in samples if s.get("error"))}
    payload = {"meta": meta, "summary": summary, "rows": rows}

    (out_dir / "scores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    if args.set_baseline:
        (out_dir / "baseline.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    report = write_report(out_dir, rows, summary, meta, baseline, args.note)

    print(f"报告：{report}")
    for name, stats in summary.items():
        print(f"  {name:20} mean={stats['mean']:.3f} n={stats['n']}")
    if not summary:
        print("没有任何指标算出结果，检查样本是否为空答案或缺少片段", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
