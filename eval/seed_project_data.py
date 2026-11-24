"""Install curated project evaluation data locally; never invokes a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_backend.infrastructure.evaluation_store import EvaluationStore


def install(data_dir: Path, source_id: str = "") -> dict:
    pack = json.loads((ROOT / "eval/project_cases.json").read_text("utf-8"))
    folder = data_dir / "benchmarks/hotline"
    folder.mkdir(parents=True, exist_ok=True)
    document = ROOT / "docs/testing/hotline-knowledge.md"
    (folder / document.name).write_text(document.read_text("utf-8"), "utf-8")
    cases = [{"id": c["id"], "question": c["question"], "reference": c["reference"],
              "source_id": source_id} for c in pack]
    # Keep previously bound document IDs when simply reinstalling the pack.
    target = folder / "questions.jsonl"
    if source_id or not target.exists():
        target.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), "utf-8")
    samples = []
    for c in pack:
        if c.get("answerable", True):
            samples.append({"id": c["id"], "question": c["question"], "answer": c["reference"],
                            "reference": c["reference"], "contexts": [c["context"]],
                            "sample_origin": "human_authored_calibration"})
    for c, answer in zip(pack[:3], ["项目只使用 Node.js。", "只启动网关就能执行 Agent。", "运行数据应提交到 Git。"]):
        samples.append({"id": c["id"] + "-wrong", "question": c["question"], "answer": answer,
                        "reference": c["reference"], "contexts": [c["context"]],
                        "sample_origin": "human_authored_negative_calibration"})
    (folder / "calibration.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples), "utf-8")
    store = EvaluationStore(data_dir / "evaluation.db")
    name = "Hotline 项目知识与拒答 v1（自带上下文）"
    existing = next((d for d in store.list_datasets() if d["name"] == name), None)
    if existing:
        dataset = store.get_dataset(existing["dataset_id"])
    else:
        dataset = store.create_dataset(name, "通用", "基于本项目源码与协作规则的人工标注；上下文随问题提供，不测检索。")
    if not dataset["cases"]:
        store.add_cases(dataset["dataset_id"], [{
            "input": f"仅根据以下资料回答。资料不足时只回答：资料未提供。\n资料：{c['context']}\n问题：{c['question']}",
            "expectedOutput": c["reference"], "rubric": c["rubric"],
        } for c in pack])
    return {"datasetId": dataset["dataset_id"], "caseCount": len(pack),
            "calibrationCount": len(samples), "sourceBound": bool(source_id)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data",
                        help="Must match the running server's DODO_DATA_DIR")
    parser.add_argument("--source-id", default="", help="Uploaded fileId/docId for real retrieval")
    args = parser.parse_args()
    print(json.dumps(install(args.data_dir.resolve(), args.source_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
