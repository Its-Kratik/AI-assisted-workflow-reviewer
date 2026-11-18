# AI-Assisted Workflow Reviewer

An evidence-backed, deterministic and AI-assisted reviewer that verifies whether a structured specification, workflow graph, and linked Python execution snippets faithfully implement written business requirements.

Built for the **Shodh AI & ML Engineer Intern Take Home Assessment 2026**.

---

## Quickstart (Single Offline CPU Command)

This project has zero external runtime dependencies and executes purely on the standard Python 3.10+ library.

```bash
# Run all unit tests, regression tests, and the 14-bundle evaluation benchmark
./run_eval.sh
```

Or directly via python:
```bash
python3 evaluate.py
```

---

## CLI Usage

### Review a Workflow Bundle
```bash
# Pretty human-readable review report
python3 -m reviewer.cli review fixtures/bundles/bundle_01_valid_baseline.json

# Machine-readable JSON report
python3 -m reviewer.cli review fixtures/bundles/bundle_06_defective_changed_threshold.json --json
```

---

## Key Capabilities Across Stages

1. **Stage 1: Input Contracts & Effective Requirements**
   - Anchored source requirements, structured specifications, versioned workflow graphs, linked Python snippets, and top-level approval records.
   - Preserves artifact versions, evidence locations, and maps omissions with source references.
   - Normalizes numeric boundaries and declared time units (`seconds`, `minutes`, `hours`, `days`).
   - Derives effective requirements from approved revisions, ignores prose claims, and flags contradictory approvals without silently picking a convenient version.

2. **Stage 2: Deterministic Semantic Review & Counterexample Synthesis**
   - Graph path traversal: reachability, dead-end detection, and branch destination verification.
   - Safe restricted AST Python inspection (no `exec` or arbitrary code execution).
   - Generates concrete counterexample ticket inputs (e.g. at boundary thresholds $T - 0.001$, $T$, $T + 0.001$) demonstrating expected vs. actual routing divergence.

3. **Stage 3: Model Trust & Guardrails**
   - Pluggable model-client interface with an offline deterministic `FakeModelClient` for reproducible local testing.
   - Robust failure handling for timeouts, malformed/truncated JSON, and hallucinated rule references.
   - Adversarial prompt injection defense (neutralizes instructions inside requirement text or code comments).
   - Tri-state status determination: `PASS`, `CHANGES_REQUIRED`, and `INCOMPLETE`.
   - Content-hash cache invalidation (preventing stale passing reports when artifacts change).

4. **Stage 4: Controlled Evaluation & Ablation**
   - 14 frozen evaluation bundles (4 valid, 7 defective, 3 incomplete; 4 reserved unseen).
   - Baseline checkpoint vs. Final implementation vs. Ablation (No AST Script Inspector).
   - Machine-readable evaluation reports generated in `reports/`.
   - Preserved debugging stories and regression tests in `tests/test_debugging_regressions.py`.

---

## Benchmark Results Summary

```text
================================================================================
EVALUATION BENCHMARK RESULTS (14 FROZEN BUNDLES)
================================================================================
Metric                              | Baseline     | Ablation     | Final       
--------------------------------------------------------------------------------
Overall Accuracy                    |       50.0% |       92.9% |      100.0%
False Passes (Defective -> PASS)    |            4 |            1 |            0
False Blocks (Valid -> BLOCK)       |            2 |            0 |            0
Counterexamples Produced            |            0 |           16 |           21
Avg Runtime per Case (ms)           |       0.01ms |       2.27ms |       3.71ms
================================================================================
```

---

## Directory Structure

```text
workflow reviewer/
├── evaluate.py                  # Single CPU entry point running tests & evaluation
├── run_eval.sh                  # Shell wrapper for single-command reproduction
├── requirements.txt             # Pinned dependencies
├── README.md                    # Project overview & instructions
├── ENGINEERING_NOTE.md          # 4-page engineering note + 1-page AI assistance statement
├── reviewer/
│   ├── schemas/                 # Strongly-typed data contracts & serialization
│   ├── engine/                  # Deterministic checks, AST evaluator, graph traversal
│   ├── model/                   # Model interface, fake client, prompt, & guardrails
│   ├── core.py                  # Orchestrator with cache invalidation
│   └── cli.py                   # CLI entry point
├── fixtures/
│   ├── oracle.py                # Independent reference routing oracle
│   ├── make_bundles.py          # Bundle generation script
│   ├── expected_labels.json     # Frozen ground-truth labels
│   └── bundles/                 # 14 evaluation bundle JSON fixtures
├── evaluation/
│   ├── runner.py                # Evaluation runner & metric generator
│   ├── baseline_checkpoint.py   # Preserved initial working checkpoint
│   └── ablation.py              # Controlled ablation (no AST inspector)
├── reports/                     # Machine-readable output metrics (JSON)
└── tests/
    ├── test_stage1_contracts.py
    ├── test_stage2_semantic.py
    ├── test_stage3_model_trust.py
    ├── test_stage4_evaluation.py
    └── test_debugging_regressions.py
```
