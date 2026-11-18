"""Workflow graph verification and path traversal.

Performs:
- Reachability analysis from entry_node
- Unreachable node and dead-end detection
- Branch destination validation
- Route tracing for a ticket input
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
from reviewer.schemas.models import (
    EvidenceLocation,
    Finding,
    Severity,
    WorkflowBranch,
    WorkflowGraph,
    WorkflowNode,
)
from reviewer.engine.expression import evaluate_condition


def analyze_workflow_graph(workflow: WorkflowGraph) -> List[Finding]:
    """Perform structural and reachability checks on the workflow graph."""
    findings: List[Finding] = []
    nodes = workflow.nodes
    entry = workflow.entry_node

    if entry not in nodes:
        findings.append(
            Finding(
                finding_id="MISSING_ENTRY_NODE",
                severity=Severity.BLOCKER,
                defect_type="MISSING_ENTRY_NODE",
                artifact_location=workflow.evidence_location,
                supporting_evidence=f"Entry node '{entry}' does not exist in workflow nodes.",
                correction="Define entry node in workflow graph.",
            )
        )
        return findings

    # Check branch validity
    branches_by_source: Dict[str, List[WorkflowBranch]] = {}
    for branch in workflow.branches:
        if branch.source_node not in nodes:
            findings.append(
                Finding(
                    finding_id=f"INVALID_BRANCH_SOURCE_{branch.branch_id}",
                    severity=Severity.BLOCKER,
                    defect_type="INVALID_BRANCH_SOURCE",
                    artifact_location=branch.evidence_location,
                    supporting_evidence=f"Branch '{branch.branch_id}' source node '{branch.source_node}' does not exist.",
                    correction="Fix branch source node reference.",
                )
            )
        if branch.target_node not in nodes:
            findings.append(
                Finding(
                    finding_id=f"INVALID_BRANCH_TARGET_{branch.branch_id}",
                    severity=Severity.BLOCKER,
                    defect_type="INVALID_BRANCH_TARGET",
                    artifact_location=branch.evidence_location,
                    supporting_evidence=f"Branch '{branch.branch_id}' target node '{branch.target_node}' does not exist.",
                    correction="Fix branch target node reference.",
                )
            )
        branches_by_source.setdefault(branch.source_node, []).append(branch)

    # Reachability from entry_node via BFS
    reachable_nodes: Set[str] = set()
    queue = [entry]
    while queue:
        curr = queue.pop(0)
        if curr in reachable_nodes:
            continue
        reachable_nodes.add(curr)
        for b in branches_by_source.get(curr, []):
            if b.target_node not in reachable_nodes:
                queue.append(b.target_node)

    # Detect unreachable nodes
    for nid, node in nodes.items():
        if nid not in reachable_nodes:
            findings.append(
                Finding(
                    finding_id=f"UNREACHABLE_NODE_{nid}",
                    severity=Severity.WARNING,
                    defect_type="UNREACHABLE_WORKFLOW_NODE",
                    artifact_location=node.evidence_location,
                    supporting_evidence=f"Workflow node '{nid}' is unreachable from entry node '{entry}'.",
                    correction="Add path to node or remove dead node.",
                )
            )

    # Detect dead-end non-terminal nodes
    for nid in reachable_nodes:
        node = nodes[nid]
        if node.type in ("decision", "action") and not node.action_route:
            out_branches = branches_by_source.get(nid, [])
            if not out_branches:
                findings.append(
                    Finding(
                        finding_id=f"DEAD_END_NODE_{nid}",
                        severity=Severity.BLOCKER,
                        defect_type="DEAD_END_WORKFLOW_NODE",
                        artifact_location=node.evidence_location,
                        supporting_evidence=f"Node '{nid}' of type '{node.type}' has no outgoing branches and no terminal action route.",
                        correction="Add outgoing branch or mark as terminal action node.",
                    )
                )

    return findings


def execute_workflow_route(workflow: WorkflowGraph, ticket: Dict[str, Any], max_steps: int = 50) -> Tuple[Optional[str], List[str]]:
    """Simulate ticket traversal through the workflow graph.

    Returns:
        Tuple of (reached_route_or_none, list_of_visited_node_ids)
    """
    nodes = workflow.nodes
    branches_by_source: Dict[str, List[WorkflowBranch]] = {}
    for b in workflow.branches:
        branches_by_source.setdefault(b.source_node, []).append(b)

    # Sort branches by priority
    for b_list in branches_by_source.values():
        b_list.sort(key=lambda x: x.priority)

    curr = workflow.entry_node
    visited = []
    steps = 0

    while steps < max_steps:
        steps += 1
        visited.append(curr)
        if curr not in nodes:
            return None, visited

        node = nodes[curr]
        if node.type == "terminal" or node.action_route:
            return node.action_route, visited

        # Decision node: check branches in priority order
        out_branches = branches_by_source.get(curr, [])
        next_node = None
        for b in out_branches:
            if b.condition is None or evaluate_condition(b.condition, ticket):
                next_node = b.target_node
                break

        if not next_node:
            # No matching branch
            return None, visited

        curr = next_node

    # Loop detected
    return None, visited
