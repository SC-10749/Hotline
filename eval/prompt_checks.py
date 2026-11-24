r"""提示词检查：静态 lint + 输出契约断言。全部是确定性判定，不调模型、不花钱。

    # 只查提示词本身（秒出）
    uv run python eval/prompt_checks.py

    # 再查输出有没有守住承诺（需要先跑 collect.py）
    uv run python eval/prompt_checks.py --samples "eval\runs\<时间戳>\samples.jsonl"

两类检查：
1. 静态：占位符齐不齐、声明的契约在提示词里有没有对应的指令
2. 输出：答案里是否真的出现了引用标记/拒答话术，有没有泄露系统提示或残留占位符

退出码：静态检查有失败，或任一输出检查通过率低于 --min-pass，返回 1。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import prompts  # noqa: E402

ALLOWED_PLACEHOLDERS = {"route", "context", "query"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
CITATION = re.compile(r"\[片段\d+\]")
REFUSAL_WORDS = ("没有", "未提及", "无法回答", "不足", "不包含", "无相关", "未找到")

# 契约 → 提示词里必须出现的指令关键词（任一命中即可）
CONTRACT_KEYWORDS = {
    "cites_sources": ("来源", "引用", "片段", "标注"),
    "refuses_when_empty": ("没有", "不足", "无法", "未提及", "不存在"),
}
MAX_ANSWER_CHARS = 2000


def static_checks(variant: prompts.PromptVariant) -> list[dict[str, Any]]:
    found = set(PLACEHOLDER.findall(variant.user))
    text = f"{variant.system}\n{variant.user}"
    checks = [
        {
            "name": "placeholder.query",
            "ok": "query" in found,
            "note": "用户模板必须包含 {query}" if "query" not in found else "",
        },
        {
            "name": "placeholder.context",
            "ok": "context" in found,
            "note": "模板没放 {context}，召回内容根本到不了模型" if "context" not in found else "",
        },
        {
            "name": "placeholder.unknown",
            "ok": found <= ALLOWED_PLACEHOLDERS,
            "note": f"未知占位符：{sorted(found - ALLOWED_PLACEHOLDERS)}" if found - ALLOWED_PLACEHOLDERS else "",
        },
        {
            "name": "system.not_empty",
            "ok": bool(variant.system.strip()),
            "note": "" if variant.system.strip() else "系统提示为空",
        },
    ]
    for contract in variant.contracts:
        keywords = CONTRACT_KEYWORDS.get(contract, ())
        hits = [word for word in keywords if word in text]
        checks.append({
            "name": f"contract.{contract}.instructed",
            "ok": bool(hits),
            "note": "" if hits else f"声明了 {contract}，但提示词里没有任何相关指令（关键词：{keywords}）",
        })
    return checks


def output_checks(variant_name: str, variant: prompts.PromptVariant,
                  samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [s for s in samples if s.get("prompt_variant", "current") == variant_name and s.get("answer")]
    if not rows:
        return []
    results: list[dict[str, Any]] = []

    def add(name: str, failed: list[str], total: int, note: str = "") -> None:
        results.append({"name": name, "passed": total - len(failed), "total": total,
                        "failed": failed[:5], "note": note})

    hard = [
        ("answer.no_system_leak",
         lambda s: variant.system[:16] not in s["answer"] and "system prompt" not in s["answer"].lower()),
        ("answer.no_placeholder_leak",
         lambda s: not PLACEHOLDER.search(s["answer"])),
        ("answer.length_limit",
         lambda s: len(s["answer"]) <= MAX_ANSWER_CHARS),
    ]
    for name, predicate in hard:
        failed = [s["id"] for s in rows if not predicate(s)]
        add(name, failed, len(rows))

    if "cites_sources" in variant.contracts:
        with_ctx = [s for s in rows if s.get("contexts")]
        failed = [s["id"] for s in with_ctx if not CITATION.search(s["answer"])]
        add("contract.cites_sources", failed, len(with_ctx), "只看有召回片段的样本")

    if "refuses_when_empty" in variant.contracts:
        without_ctx = [s for s in rows if not s.get("contexts")]
        failed = [s["id"] for s in without_ctx if not any(w in s["answer"] for w in REFUSAL_WORDS)]
        add("contract.refuses_when_empty", failed, len(without_ctx), "只看无召回片段的样本")

    return results


def render(report_path: Path, static_rows: list[dict[str, Any]],
           output_rows: list[dict[str, Any]], min_pass: float) -> None:
    lines = ["# 提示词检查报告", "", "## 静态检查", "", "| 变体 | 检查项 | 结果 | 说明 |", "|---|---|---|---|"]
    static_failed = 0
    for row in static_rows:
        mark = "✅" if row["ok"] else "❌"
        if not row["ok"]:
            static_failed += 1
        lines.append(f"| {row['variant']} | {row['name']} | {mark} | {row['note']} |")

    lines += ["", "## 输出契约检查", ""]
    if not output_rows:
        lines.append("（没有样本，跳过；先跑 collect.py 再带 --samples）")
    else:
        lines += ["| 变体 | 检查项 | 通过 | 总数 | 通过率 | 失败用例 |", "|---|---|---|---|---|---|"]
        for row in output_rows:
            rate = row["passed"] / row["total"] if row["total"] else 1.0
            mark = "✅" if rate >= min_pass else "❌"
            failed = ", ".join(row["failed"]) or "-"
            lines.append(f"| {row['variant']} | {row['name']} | {row['passed']} | {row['total']} | "
                         f"{rate:.0%} {mark} | {failed} |")
    report_path.write_text("\n".join(lines) + "\n", "utf-8")

    print(f"报告：{report_path}")
    print(f"静态检查：{len(static_rows) - static_failed}/{len(static_rows)} 通过")
    for row in output_rows:
        rate = row["passed"] / row["total"] if row["total"] else 1.0
        print(f"  {row['variant']:10} {row['name']:28} {row['passed']}/{row['total']} ({rate:.0%})")


def main() -> int:
    parser = argparse.ArgumentParser(description="提示词静态检查 + 输出契约断言")
    parser.add_argument("--samples", default="", help="samples.jsonl；给了才查输出")
    parser.add_argument("--out", default="", help="报告输出路径，默认与 samples 同目录")
    parser.add_argument("--min-pass", type=float, default=0.8, help="输出检查的最低通过率")
    parser.add_argument("--only", default="", help="只查某个变体")
    args = parser.parse_args()

    names = [args.only] if args.only else list(prompts.VARIANTS)
    static_rows = []
    for name in names:
        variant = prompts.get(name)
        for row in static_checks(variant):
            static_rows.append({"variant": name, **row})

    samples: list[dict[str, Any]] = []
    if args.samples:
        path = Path(args.samples)
        if not path.is_file():
            print(f"找不到样本文件：{path}", file=sys.stderr)
            return 2
        samples = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]

    output_rows: list[dict[str, Any]] = []
    for name in names:
        if samples:
            for row in output_checks(name, prompts.get(name), samples):
                output_rows.append({"variant": name, **row})

    out_path = Path(args.out) if args.out else (
        Path(args.samples).parent / "checks.md" if args.samples else EVAL_DIR / "runs" / "checks.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render(out_path, static_rows, output_rows, args.min_pass)

    failed_static = any(not row["ok"] for row in static_rows)
    failed_output = any(row["total"] and row["passed"] / row["total"] < args.min_pass for row in output_rows)
    return 1 if (failed_static or failed_output) else 0


if __name__ == "__main__":
    raise SystemExit(main())
