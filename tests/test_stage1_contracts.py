"""Stage 1 tests: Schemas, time units, condition expressions, and effective requirements derivation."""

import unittest
from reviewer.schemas.models import (
    ApprovalRecord,
    Condition,
    EvidenceLocation,
    Operator,
    ReviewStatus,
    Severity,
    SourceRequirement,
    TimeUnit,
)
from reviewer.engine.units import normalize_numeric_value, are_numeric_conditions_equivalent
from reviewer.engine.expression import evaluate_condition, are_conditions_semantically_equivalent
from reviewer.engine.approvals import derive_effective_requirements


class TestStage1Contracts(unittest.TestCase):
    def test_evidence_location_serialization(self):
        loc = EvidenceLocation(
            artifact="requirements",
            version="1.0.0",
            file="policy.md",
            line=42,
            char_range=(10, 50),
            anchor_id="R1",
        )
        d = loc.to_dict()
        self.assertEqual(d["line"], 42)
        self.assertEqual(d["char_range"], (10, 50))
        reconstructed = EvidenceLocation.from_dict(d)
        self.assertEqual(reconstructed.anchor_id, "R1")

    def test_unit_normalization(self):
        # 0.5 hours == 30 minutes
        val_m, u_m = normalize_numeric_value(0.5, "hours")
        self.assertEqual(val_m, 30.0)
        self.assertEqual(u_m, "minutes")

        # 180 seconds == 3 minutes
        val_s, u_s = normalize_numeric_value(180, "seconds")
        self.assertEqual(val_s, 3.0)

        # 1 day == 1440 minutes
        val_d, u_d = normalize_numeric_value(1, "days")
        self.assertEqual(val_d, 1440.0)

        # Semantic equivalence between 30 minutes and 0.5 hours
        self.assertTrue(are_numeric_conditions_equivalent(">=", 30, "minutes", ">=", 0.5, "hours"))
        self.assertFalse(are_numeric_conditions_equivalent(">", 30, "minutes", ">=", 30, "minutes"))

    def test_condition_evaluation_missing_and_numeric(self):
        cond_null = Condition("category", Operator.IS_NULL.value)
        self.assertTrue(evaluate_condition(cond_null, {"category": None}))
        self.assertFalse(evaluate_condition(cond_null, {"category": "billing"}))

        cond_gte = Condition("waiting_time", Operator.GTE.value, 30, unit="minutes")
        self.assertTrue(evaluate_condition(cond_gte, {"waiting_time": 30}))
        self.assertTrue(evaluate_condition(cond_gte, {"waiting_time": 35}))
        self.assertFalse(evaluate_condition(cond_gte, {"waiting_time": 29.9}))

    def test_approvals_apply_top_level_metadata(self):
        base_req = SourceRequirement(
            id="R3",
            anchor="p3",
            version="1.0",
            precedence=3,
            condition=Condition("waiting_time", Operator.GTE.value, 30, unit="minutes"),
            target_route="escalation",
            raw_text="R3: waiting >= 30 min -> escalation.",
            evidence_location=EvidenceLocation("requirements", "1.0", "p.md", 3),
        )
        approved_chg = ApprovalRecord(
            change_id="CHG-1",
            target_rule_id="R3",
            approved=True,
            author="lead",
            timestamp="2026-03-01T10:00:00Z",
            scope="R3 threshold",
            description="Reduce to 25 min",
            evidence_location=EvidenceLocation("approvals", "1.0", "app.json", 1),
            proposed_condition=Condition("waiting_time", Operator.GTE.value, 25, unit="minutes"),
        )
        effective, findings = derive_effective_requirements([base_req], [approved_chg])
        self.assertEqual(len(findings), 0)
        self.assertEqual(effective[0].condition.value, 25)

    def test_unapproved_changes_not_applied(self):
        base_req = SourceRequirement(
            id="R3",
            anchor="p3",
            version="1.0",
            precedence=3,
            condition=Condition("waiting_time", Operator.GTE.value, 30, unit="minutes"),
            target_route="escalation",
            raw_text="R3: waiting >= 30 min -> escalation.",
            evidence_location=EvidenceLocation("requirements", "1.0", "p.md", 3),
        )
        unapproved = ApprovalRecord(
            change_id="CHG-REJECTED",
            target_rule_id="R3",
            approved=False,
            author="intern",
            timestamp="2026-03-01T10:00:00Z",
            scope="R3 threshold",
            description="Lower to 15 min",
            evidence_location=EvidenceLocation("approvals", "1.0", "app.json", 1),
            proposed_condition=Condition("waiting_time", Operator.GTE.value, 15, unit="minutes"),
        )
        effective, findings = derive_effective_requirements([base_req], [unapproved])
        self.assertEqual(len(findings), 0)
        self.assertEqual(effective[0].condition.value, 30)

    def test_contradictory_approval_detection(self):
        base_req = SourceRequirement(
            id="R3",
            anchor="p3",
            version="1.0",
            precedence=3,
            condition=Condition("waiting_time", Operator.GTE.value, 30, unit="minutes"),
            target_route="escalation",
            raw_text="R3: waiting >= 30 min -> escalation.",
            evidence_location=EvidenceLocation("requirements", "1.0", "p.md", 3),
        )
        app1 = ApprovalRecord("C1", "R3", True, "alice", "2026-03-01T10:00:00Z", "sc", "d", EvidenceLocation("app", "1", "a.json", 1), proposed_condition=Condition("waiting_time", Operator.GTE.value, 25, unit="minutes"))
        app2 = ApprovalRecord("C2", "R3", True, "bob", "2026-03-01T10:00:00Z", "sc", "d", EvidenceLocation("app", "1", "a.json", 2), proposed_condition=Condition("waiting_time", Operator.GTE.value, 20, unit="minutes"))
        effective, findings = derive_effective_requirements([base_req], [app1, app2])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].defect_type, "CONTRADICTORY_APPROVAL_RECORDS")
        self.assertTrue(effective[0].is_ambiguous)


if __name__ == "__main__":
    unittest.main()
