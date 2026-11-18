"""CLI entry point for AI-assisted workflow reviewer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from reviewer.schemas.models import ReviewBundle
from reviewer.core import WorkflowReviewer
from reviewer.model.fake_client import FakeModelClient
from reviewer.model.real_client import RealModelClient


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="workflow-reviewer",
        description="AI-assisted reviewer for decision workflows and specifications.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: review
    review_parser = subparsers.add_parser("review", help="Review a workflow bundle JSON file.")
    review_parser.add_argument("bundle_path", type=str, help="Path to bundle.json")
    review_parser.add_argument("--json", action="store_true", help="Output full report as JSON.")
    review_parser.add_argument("--no-cache", action="store_true", help="Disable caching.")
    review_parser.add_argument("--live-model", action="store_true", help="Attempt connection to live API using GEMINI_API_KEY / OPENAI_API_KEY.")

    # Command: evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Run full benchmark evaluation on frozen bundles.")

    args = parser.parse_args()

    if args.command == "review":
        path = Path(args.bundle_path)
        if not path.exists():
            print(f"Error: File not found at '{args.bundle_path}'", file=sys.stderr)
            return 1

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        bundle = ReviewBundle.from_dict(data)
        client = RealModelClient() if args.live_model else FakeModelClient()
        reviewer = WorkflowReviewer(model_client=client, enable_caching=not args.no_cache)
        report = reviewer.review(bundle)

        if args.json:
            print(report.to_json())
        else:
            print(f"=== WORKFLOW REVIEW REPORT: {bundle.bundle_id} ===")
            print(f"Status:   {report.status.value}")
            print(f"Summary:  {report.summary}")
            print(f"Findings: {len(report.findings)} total")
            for idx, f in enumerate(report.findings, 1):
                rule_info = f" [Rule: {f.rule_reference}]" if f.rule_reference else ""
                print(f"  {idx}. [{f.severity.value}] {f.defect_type}{rule_info}")
                print(f"     Evidence: {f.supporting_evidence}")
                if f.counterexample:
                    print(f"     Counterexample: {f.counterexample}")
                print(f"     Correction: {f.correction}")
            print(f"Coverage: {report.coverage.get('coverage_percentage', 0.0):.1f}%")
            print(f"Client:   {report.provenance.get('client_type')}")
            print(f"Runtime:  {report.provenance.get('runtime_ms')} ms")

        return 0 if report.status.value == "PASS" else 2

    elif args.command == "evaluate":
        from evaluation.runner import run_full_evaluation
        run_full_evaluation()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
