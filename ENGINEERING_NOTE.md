# Engineering Note: AI-Assisted Workflow Reviewer

**Author:** AI & ML Engineer Intern Candidate  
**Target:** Shodh AI Take Home Assessment 2026  
**System:** AI-Assisted Workflow Reviewer across 4 Cumulative Stages  
**Evaluation:** 14 Frozen Bundles (100% Deterministic Decision Correctness)

---

## 1. Supported Scope and Domain Contracts

The AI-Assisted Workflow Reviewer evaluates whether structured specifications, versioned workflow graphs, and linked Python execution scripts faithfully adhere to written policy requirements.

### Supported Condition Grammar
1. **Missing / Null Values:** Explicit checks for unassigned fields (`field is_null` / `is_not_null`, `missing`).
2. **Numeric Comparisons:** Relational operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) with strict boundary inclusivity/exclusivity checking.
3. **Declared Time Units:** Automatic normalization of time expressions across `seconds`, `minutes`, `hours`, and `days` to canonical minutes. For example, `0.5 hours` is recognized as equivalent to `30 minutes`.
4. **Logical Composition:** Arbitrary nesting of `AND`, `OR`, and `NOT` boolean nodes.
5. **Ordered Precedence & Exceptions:** Deterministic sequential evaluation (`precedence: int`), ensuring specific exception overrides take precedence over fallback routes.

### Restricted Python Subset
To guarantee safe offline CPU execution without invoking arbitrary or untrusted code:
- **Allowed AST Nodes:** `Module`, `FunctionDef`, `arguments`, `arg`, `Return`, `If`, `Assign`, `Store`, `Compare`, `BoolOp`, `UnaryOp`, `Name`, `Load`, `Constant`, `Attribute`, `Dict`, `Subscript`, and `Call` (restricted to safe built-ins `float`, `int`, `str`, `bool`, `len`, `min`, `max` and dictionary `.get()`).
- **Forbidden Constructs:** Any `import`, `exec()`, `eval()`, `while`/`for` loops, file I/O, OS, or networking primitives are intercepted via AST inspection and flagged as `UNSUPPORTED_PYTHON_SUBSET` without execution.
- **Pure-Functional Symbolic Interpreter:** Snippet evaluation runs in a custom `SafeASTInterpreter` that walks the AST environment over synthetic ticket dictionaries.

---

## 2. System Architecture & Semantic Checks

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ReviewBundle (Input Data)                       │
│  [Source Requirements] [Specifications] [Workflow Graph] [Python AST]  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Stage 1: Effective Requirements                      │
│ - Derives chronological changes with top-level metadata authority      │
│ - Rejects unapproved changes & ignores prose approval claims           │
│ - Detects contradictory approval records (yields INCOMPLETE/WARNING)   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Stage 2: Deterministic Semantic Review & Synthesis         │
│ - Graph Path Traversal: reachability, dead-end, & loop verification    │
│ - AST Inspection: safe symbolic evaluation on ticket partitions        │
│ - Counterexample Generator: synthesizes boundary tickets (e.g. 29.999, │
│   30.0, 30.001 min) and isolates exact artifact disagreements          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│            Stage 3: Model Trust, Guardrails & Reconciler               │
│ - Prompt Boundary Isolation: isolates untrusted text & injections      │
│ - Hallucination Filter: sanitizes invented rule/artifact references    │
│ - Tri-State Reconciler: PASS | CHANGES_REQUIRED | INCOMPLETE           │
│ - Hash-Based Cache Invalidation: prevents stale passing reuse          │
└────────────────────────────────────────────────────────────────────────┘
```

### Equivalence & Counterexample Generation
Rather than relying on brittle numeric substring matches, the engine extracts all partition boundaries (thresholds $T \in \{0, 15, 20, 25, 30, 45, 60\}$ minutes) and probes tickets across:
- Exact boundaries: $T - 5$, $T - 0.001$, $T$ (inclusive test), $T + 0.001$, $T + 5$.
- Categorical attributes: `category \in {None, 'billing', 'technical'}`.
- Urgency flags: `urgent \in {True, False}`.

For each synthetic ticket, routes are evaluated across (1) Effective Requirements, (2) Specification, (3) Workflow Graph traversal, and (4) Python AST interpreter. Any discrepancy generates a concrete counterexample with expected vs. actual route and artifact location.

### Tri-State Status Semantics
- **`PASS`**: Complete review of all effective requirements within declared supported scope; zero blocker findings.
- **`CHANGES_REQUIRED`**: Evidenced behavioral defect identified (omission, threshold divergence, precedence inversion, script disagreement, or injection attempt).
- **`INCOMPLETE`**: Missing evidence, ambiguity, contradictory approvals, or model timeout prevents full verification and no blocker is yet established.

---

## 3. Preserved Substantive Debugging Examples

### Debugging Example 1: Dataclass Class-Scope Attribute Shadowing
- **Failing Output:**
  ```text
  File ".../reviewer/schemas/models.py", line 94, in Condition
    conditions: List[Condition] = field(default_factory=list)
  TypeError: 'NoneType' object is not callable
  ```
- **Diagnosis:** In `Condition`, attribute `field: Optional[str] = None` was declared at line 89. Inside the class body namespace, this assignment shadowed the imported `from dataclasses import field` function, setting `field` to `None`. Subsequent declarations calling `field(default_factory=...)` failed with `TypeError`.
- **Focused Fix:** Aliased dataclass field helper as `from dataclasses import dataclass, field as dc_field, asdict` and used `dc_field(default_factory=...)`.
- **Regression Test:** `tests/test_debugging_regressions.py::test_regression_1_dataclass_attribute_shadowing`.

### Debugging Example 2: Ticket Time-Unit Default Inheritance Bug
- **Failing Output:**
  ```text
  bundle_03_valid_unusual_formulation -> Got: CHANGES_REQUIRED Exp: PASS
  Finding: SPECIFICATION_DISAGREEMENT Specification routes ticket to 'escalation' but effective requirement 'R_default' specifies 'normal queue'.
  Counterexample: {'ticket_input': {'waiting_time': 0.999}, 'expected_route': 'normal queue', 'actual_route': 'escalation'}
  ```
- **Diagnosis:** When checking `waiting_time >= 0.5 hours`, the condition evaluation code had a fallback:
  `ticket_unit = ticket.get("waiting_time_unit") or (cond.unit if cond.unit else None)`.
  When a ticket did not specify a unit, it inherited `cond.unit` (`"hours"`). A test probe of `0.999` was converted as `0.999 * 60 = 59.94 minutes`, which erroneously satisfied `59.94 >= 30`!
- **Focused Fix:** Tickets without an explicit unit default to the domain base standard unit (`"minutes"`), rather than inheriting the rule's comparison unit.
- **Regression Test:** `tests/test_debugging_regressions.py::test_regression_2_unit_normalization_ticket_default`.

---

## 4. Controlled Evaluation & Ablation

The frozen evaluation set contains **14 comprehensive bundles** spanning all required conditions:
- **Valid (4 cases):** Baseline (`01`), Approved Change (`02`), Unusual Formulation (`03`), Paired Syntactic Variant (`04`).
- **Defective (7 cases):** Omitted Requirement (`05`), Changed Threshold (`06`), Precedence Inversion (`07`), Wrong Branch (`08`), Script Disagreement (`09`), Unapproved Change (`10`), Multi-Rule Interaction (`11`).
- **Incomplete / Edge (3 cases):** Contradictory Approvals (`12`), Ambiguous Requirement (`13`), Adversarial Prompt Injection (`14`).
- **Reserved Unseen Partitions:** Bundles `11`, `12`, `13`, and `14` were frozen and reserved from tuning.

### Benchmark Summary Table

| Metric | Baseline Checkpoint | Ablation (No Script Inspector) | Final Implementation |
| :--- | :---: | :---: | :---: |
| **Overall Decision Accuracy** | **50.0%** (7/14) | **92.9%** (13/14) | **100.0%** (14/14) |
| **False Passes (Defective $\rightarrow$ PASS)** | 4 | 1 | **0** |
| **False Blocks (Valid $\rightarrow$ BLOCK)** | 2 | 0 | **0** |
| **Counterexamples Synthesized** | 0 | 16 | **21** |
| **Avg Runtime per Case (CPU)** | 0.01 ms | 2.27 ms | 3.71 ms |

### Ablation Analysis
Disabling the AST Script Inspector mechanism (`AblationWorkflowReviewer`) while holding all other inputs and graph checks constant caused `bundle_09_defective_script_disagreement` to produce a **False Pass**. The specification and workflow graph appeared structurally sound, but the underlying execution script returned `'normal queue'` for escalated tickets. This demonstrates that specification and graph validation alone cannot guarantee execution correctness without AST verification.

---

## 5. Limitations and Operational Scope

1. **Stateful Workflows:** The reviewer currently evaluates stateless single-ticket routing graphs. Loops with state mutation across multiple tickets require dynamic trace analysis.
2. **Arbitrary Python Constructs:** Python snippets are limited to the verified pure-functional subset. User-defined external libraries or database queries are rejected for safety and must be encapsulated behind declarative nodes.
3. **Natural Language Ambiguities:** While the model integration flags unstructured prose ambiguity, ground-truth operationalization requires human stakeholder clarification.

---

# Material AI Assistance Statement & Verification Note

### 1. Scope of AI Assistance
During the development of this project, AI assistance (Antigravity with Gemini 3.8 Flash) was utilized for:
- Initial drafting of dataclass schemas and serialization boilerplate.
- Synthesizing boundary partition values for the synthetic candidate ticket generator.
- Constructing JSON test fixtures and paired syntactic permutations.
- Drafting initial documentation and benchmark formatting utilities.

### 2. Independent Verification & Validation
All AI-generated code and outputs were subjected to rigorous independent validation:
1. **Mathematical & Logical Soundness:** Condition interval boundaries and unit normalization equations were manually checked against ground-truth routing rules.
2. **Defensive Sandbox Verification:** Python AST execution was isolated to a custom visitor pattern and symbolic interpreter, ensuring zero execution of untrusted `eval()` or `exec()`.
3. **Independent Oracle:** Expected evaluation labels were established in `fixtures/oracle.py` completely independent of reviewer heuristics to prevent circular validation.
4. **Reproducibility:** The entire suite was executed repeatedly from clean CPU environments using `run_eval.sh`, validating 19 unit/regression tests and generating machine-readable JSON metrics in under 0.15 seconds.
