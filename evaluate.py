#!/usr/bin/env python3
"""Single offline CPU-only evaluation and test runner entry point."""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation.runner import run_full_evaluation


def main():
    print("=" * 80)
    print("AI-ASSISTED WORKFLOW REVIEWER: FULL TEST & EVALUATION SUITE")
    print("=" * 80)
    print("\n[Step 1/2] Running Unit & Regression Test Suite...")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    if not test_result.wasSuccessful():
        print("\nERROR: Tests failed! Aborting evaluation.", file=sys.stderr)
        return 1

    print("\n[Step 2/2] Running Benchmark Evaluation on 14 Frozen Bundles...")
    summary = run_full_evaluation()
    print("\nAll offline CPU tests and evaluation benchmarks completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
