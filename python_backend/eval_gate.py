"""按评测配置里的门禁检查一轮测评；不通过时退出码为 1。

用法：
    python -m python_backend.eval_gate --target <运行编号> [--base <基线运行编号>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .infrastructure.evaluation_store import EvaluationStore
from .modules.evaluation.analysis import check_gates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m python_backend.eval_gate",
                                     description="按评测配置的门禁检查一轮测评")
    parser.add_argument("--target", required=True, help="被检查的测评运行编号")
    parser.add_argument("--base", default="", help="基线运行编号（可选，用于对比）")
    parser.add_argument("--db", default="", help="测评库路径（默认取配置里的 data 目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = Path(args.db) if args.db else Path(settings.data_dir) / "evaluation.db"
    store = EvaluationStore(db_path)
    run = store.get_run(args.target)
    if not run:
        print(f"测评运行不存在：{args.target}", file=sys.stderr)
        return 2
    base_summary = None
    if args.base:
        base_run = store.get_run(args.base)
        if not base_run:
            print(f"基线测评运行不存在：{args.base}", file=sys.stderr)
            return 2
        base_summary = base_run.get("summary") or {}
    config = store.get_config()
    report = check_gates(config.get("gates") or [], run.get("summary") or {}, base_summary)
    if args.json:
        print(json.dumps({**report, "target": args.target, "base": args.base},
                         ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    print(f"测评运行 {args.target}")
    if report["checks"]:
        for check in report["checks"]:
            mark = "通过" if check["passed"] else "未通过"
            print(f"  [{mark}] {check['label']} · {check['metric']} {check['op']} {check['value']}"
                  f" · 实际 {check['actual']}")
    else:
        print("  未配置门禁")
    print("门禁结果：" + ("通过" if report["passed"] else "未通过"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
