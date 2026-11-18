"""Data contracts and schemas for AI-assisted workflow reviewer.

Preserves artifact versions, evidence locations, structured condition expressions,
approval metadata, workflow graphs, and linked Python snippets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class Operator(str, Enum):
    EQ = "=="
    NEQ = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IN = "in"
    NOT_IN = "not_in"
    ALWAYS_TRUE = "always_true"


class LogicalOp(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class TimeUnit(str, Enum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"

    @classmethod
    def to_minutes(cls, value: float, unit: Union[str, TimeUnit]) -> float:
        u = unit.value if isinstance(unit, TimeUnit) else str(unit).lower()
        if u in ("s", "sec", "second", "seconds"):
            return value / 60.0
        elif u in ("m", "min", "minute", "minutes"):
            return float(value)
        elif u in ("h", "hr", "hour", "hours"):
            return value * 60.0
        elif u in ("d", "day", "days"):
            return value * 1440.0
        else:
            raise ValueError(f"Unknown time unit: {unit}")


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class ReviewStatus(str, Enum):
    PASS = "PASS"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    INCOMPLETE = "INCOMPLETE"


@dataclass
class EvidenceLocation:
    artifact: str  # "requirements", "specification", "workflow", "script", "approvals"
    version: str = "1.0.0"
    file: str = "bundle.json"
    line: Optional[int] = None
    char_range: Optional[Tuple[int, int]] = None
    anchor_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceLocation:
        if isinstance(data.get("char_range"), list):
            data["char_range"] = tuple(data["char_range"])
        return cls(**data)


@dataclass
class Condition:
    field: Optional[str] = None  # None for compound expressions
    operator: Optional[str] = None  # Operator value e.g. "==", ">="
    value: Any = None
    unit: Optional[str] = None  # e.g. "minutes", "hours"
    logical_op: Optional[str] = None  # "AND", "OR", "NOT"
    conditions: List[Condition] = dc_field(default_factory=list)
    raw_expression: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {}
        if self.field is not None:
            res["field"] = self.field
        if self.operator is not None:
            res["operator"] = self.operator
        if self.value is not None:
            res["value"] = self.value
        if self.unit is not None:
            res["unit"] = self.unit
        if self.logical_op is not None:
            res["logical_op"] = self.logical_op
        if self.conditions:
            res["conditions"] = [c.to_dict() for c in self.conditions]
        if self.raw_expression is not None:
            res["raw_expression"] = self.raw_expression
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Condition:
        if not data:
            return cls(operator=Operator.ALWAYS_TRUE.value)
        conds = [cls.from_dict(c) for c in data.get("conditions", [])]
        return cls(
            field=data.get("field"),
            operator=data.get("operator"),
            value=data.get("value"),
            unit=data.get("unit"),
            logical_op=data.get("logical_op"),
            conditions=conds,
            raw_expression=data.get("raw_expression"),
        )

    @classmethod
    def always_true(cls) -> Condition:
        return cls(operator=Operator.ALWAYS_TRUE.value)


@dataclass
class SourceRequirement:
    id: str  # e.g. "R1", "R2", "R3", "R_default"
    anchor: str  # section or line anchor
    version: str
    precedence: int  # lower = higher precedence (1 is highest)
    condition: Condition
    target_route: str  # "manual review", "priority queue", "escalation", "normal queue"
    raw_text: str
    evidence_location: EvidenceLocation
    is_default: bool = False
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    unsupported_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["condition"] = self.condition.to_dict()
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SourceRequirement:
        data = dict(data)
        data["condition"] = Condition.from_dict(data.get("condition", {}))
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class SpecificationRule:
    rule_id: str
    version: str
    precedence: int
    condition: Condition
    target_route: str
    evidence_location: EvidenceLocation
    source_requirement_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["condition"] = self.condition.to_dict()
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SpecificationRule:
        data = dict(data)
        data["condition"] = Condition.from_dict(data.get("condition", {}))
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class WorkflowNode:
    node_id: str
    type: str  # "decision", "action", "terminal"
    evidence_location: EvidenceLocation
    action_route: Optional[str] = None
    linked_rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowNode:
        data = dict(data)
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class WorkflowBranch:
    branch_id: str
    source_node: str
    target_node: str
    priority: int  # 1 evaluated before 2
    evidence_location: EvidenceLocation
    condition: Optional[Condition] = None
    linked_rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.condition:
            d["condition"] = self.condition.to_dict()
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowBranch:
        data = dict(data)
        if data.get("condition"):
            data["condition"] = Condition.from_dict(data["condition"])
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class WorkflowGraph:
    version: str
    entry_node: str
    nodes: Dict[str, WorkflowNode]
    branches: List[WorkflowBranch]
    evidence_location: EvidenceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "entry_node": self.entry_node,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "branches": [b.to_dict() for b in self.branches],
            "evidence_location": self.evidence_location.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowGraph:
        nodes = {k: WorkflowNode.from_dict(v) for k, v in data.get("nodes", {}).items()}
        branches = [WorkflowBranch.from_dict(b) for b in data.get("branches", [])]
        ev = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(
            version=data["version"],
            entry_node=data["entry_node"],
            nodes=nodes,
            branches=branches,
            evidence_location=ev,
        )


@dataclass
class LinkedPythonSnippet:
    snippet_id: str
    version: str
    function_name: str
    code: str
    evidence_location: EvidenceLocation
    linked_node_or_branch: Optional[str] = None
    linked_rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LinkedPythonSnippet:
        data = dict(data)
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class ApprovalRecord:
    change_id: str
    target_rule_id: str
    approved: bool  # Top-level approval metadata is trusted; prose claims are not
    author: str
    timestamp: str  # ISO 8601
    scope: str
    description: str
    evidence_location: EvidenceLocation
    proposed_condition: Optional[Condition] = None
    proposed_route: Optional[str] = None
    proposed_precedence: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.proposed_condition:
            d["proposed_condition"] = self.proposed_condition.to_dict()
        d["evidence_location"] = self.evidence_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApprovalRecord:
        data = dict(data)
        if data.get("proposed_condition"):
            data["proposed_condition"] = Condition.from_dict(data["proposed_condition"])
        data["evidence_location"] = EvidenceLocation.from_dict(data["evidence_location"])
        return cls(**data)


@dataclass
class Finding:
    finding_id: str
    severity: Severity
    defect_type: str
    artifact_location: EvidenceLocation
    supporting_evidence: str
    correction: str
    rule_reference: Optional[str] = None
    counterexample: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["artifact_location"] = self.artifact_location.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Finding:
        data = dict(data)
        data["severity"] = Severity(data["severity"])
        data["artifact_location"] = EvidenceLocation.from_dict(data["artifact_location"])
        return cls(**data)


@dataclass
class ReviewBundle:
    bundle_id: str
    description: str
    requirements: List[SourceRequirement]
    specification: List[SpecificationRule]
    workflow: WorkflowGraph
    snippets: List[LinkedPythonSnippet]
    approvals: List[ApprovalRecord]
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "description": self.description,
            "requirements": [r.to_dict() for r in self.requirements],
            "specification": [s.to_dict() for s in self.specification],
            "workflow": self.workflow.to_dict(),
            "snippets": [s.to_dict() for s in self.snippets],
            "approvals": [a.to_dict() for a in self.approvals],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReviewBundle:
        reqs = [SourceRequirement.from_dict(r) for r in data.get("requirements", [])]
        specs = [SpecificationRule.from_dict(s) for s in data.get("specification", [])]
        wf = WorkflowGraph.from_dict(data["workflow"])
        snippets = [LinkedPythonSnippet.from_dict(s) for s in data.get("snippets", [])]
        approvals = [ApprovalRecord.from_dict(a) for a in data.get("approvals", [])]
        return cls(
            bundle_id=data["bundle_id"],
            description=data["description"],
            requirements=reqs,
            specification=specs,
            workflow=wf,
            snippets=snippets,
            approvals=approvals,
            metadata=data.get("metadata", {}),
        )


@dataclass
class ReviewReport:
    status: ReviewStatus
    summary: str
    findings: List[Finding]
    coverage: Dict[str, Any]
    check_results: Dict[str, Any]
    provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "coverage": self.coverage,
            "check_results": self.check_results,
            "provenance": self.provenance,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReviewReport:
        data = dict(data)
        data["status"] = ReviewStatus(data["status"])
        data["findings"] = [Finding.from_dict(f) for f in data.get("findings", [])]
        return cls(**data)
