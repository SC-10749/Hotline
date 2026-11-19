"""Offline checks for the curated project test pack."""
import json
from pathlib import Path
import tempfile
import unittest

from seed_project_data import ROOT, install
from python_backend.infrastructure.evaluation_store import EvaluationStore
from python_backend.modules.evaluation import score_case


class ProjectDataTests(unittest.TestCase):
    def test_install_is_repeatable_and_preserves_bound_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = install(root, "test-document")
            second = install(root)
            self.assertEqual(first["datasetId"], second["datasetId"])
            store = EvaluationStore(root / "evaluation.db")
            self.assertEqual(len(store.list_datasets()), 1)
            self.assertEqual(store.get_dataset(first["datasetId"])["case_count"], 16)
            questions = [json.loads(s) for s in (root / "benchmarks/hotline/questions.jsonl").read_text("utf-8").splitlines()]
            self.assertTrue(all(c["source_id"] == "test-document" for c in questions))
            samples = [json.loads(s) for s in (root / "benchmarks/hotline/calibration.jsonl").read_text("utf-8").splitlines()]
            self.assertEqual(len(samples), 17)
            self.assertTrue(all(s["contexts"] and s["answer"] and s["reference"] for s in samples))

    def test_reference_answers_pass_and_empty_answers_fail(self):
        cases = json.loads((ROOT / "eval/project_cases.json").read_text("utf-8"))
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        for c in cases:
            with self.subTest(case=c["id"]):
                self.assertEqual(score_case(c["reference"], c["reference"], c["rubric"])["verdict"], "passed")
                self.assertEqual(score_case("", c["reference"], c["rubric"])["verdict"], "failed")


if __name__ == "__main__":
    unittest.main()
