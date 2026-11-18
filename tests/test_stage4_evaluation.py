"""Stage 4 tests: Evaluation dataset integrity and benchmark validation."""

import json
import unittest
from pathlib import Path
from fixtures.oracle import EXPECTED_BUNDLE_LABELS
from evaluation.runner import load_bundles, evaluate_system
from reviewer.core import WorkflowReviewer


class TestStage4Evaluation(unittest.TestCase):
    def test_frozen_dataset_counts(self):
        bundles = load_bundles()
        self.assertGreaterEqual(len(bundles), 12, "Assessment requires at least 12 review bundles")

        categories = {"valid": 0, "defective": 0, "incomplete": 0}
        for _, _, label in bundles:
            cat = label.get("category")
            if cat in categories:
                categories[cat] += 1

        self.assertGreaterEqual(categories["valid"], 3, "At least 3 valid cases required")
        self.assertGreaterEqual(categories["defective"], 6, "At least 6 defective cases required")
        self.assertGreaterEqual(categories["incomplete"], 3, "At least 3 incomplete cases required")

        unseen_count = sum(1 for _, _, l in bundles if l.get("is_reserved_unseen"))
        self.assertGreaterEqual(unseen_count, 4, "At least 4 bundles reserved from tuning")

    def test_final_system_perfect_accuracy_on_frozen_set(self):
        bundles = load_bundles()
        reviewer = WorkflowReviewer()
        metrics = evaluate_system(reviewer, bundles, "Final_Reviewer")
        self.assertEqual(metrics["accuracy_percentage"], 100.0)
        self.assertEqual(metrics["decision_correctness"]["false_passes"], 0)
        self.assertEqual(metrics["decision_correctness"]["false_blocks"], 0)
        self.assertGreater(metrics["finding_quality"]["counterexamples_synthesized"], 0)


if __name__ == "__main__":
    unittest.main()
