"""Safe restricted AST inspection and evaluation for Python snippets.

Enforces:
- Restricted Python subset: no imports, no OS/network/eval/exec, no loops.
- Purely symbolic inspection and safe AST evaluation over ticket dictionaries.
- Disagreement detection between script and declared requirements/workflow.
"""

from __future__ import annotations

import ast
from typing import Any, Callable, Dict, List, Optional, Tuple, Set
from reviewer.schemas.models import (
    EvidenceLocation,
    Finding,
    LinkedPythonSnippet,
    Severity,
)
from reviewer.engine.units import normalize_numeric_value

SAFE_BUILTINS: Dict[str, Callable[..., Any]] = {
    "float": float,
    "int": int,
    "str": str,
    "bool": bool,
    "len": len,
    "min": min,
    "max": max,
}

# Permitted AST node types for restricted routing functions
PERMITTED_NODES = {
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.If,
    ast.Assign,
    ast.Store,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Dict,
    ast.Subscript,
    ast.Pass,
    ast.Expr,
    ast.Call,
    # Comparison operators
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    # Boolean operators
    ast.And,
    ast.Or,
    ast.Not,
}


class ASTSafetyValidator(ast.NodeVisitor):
    """Validates that a Python snippet conforms strictly to the restricted subset."""

    def __init__(self) -> None:
        self.violations: List[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in PERMITTED_NODES:
            self.violations.append(
                f"Disallowed AST node '{type(node).__name__}' at line {getattr(node, 'lineno', '?')}"
            )
        super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Validate that the function call is strictly in the safe whitelist
        if isinstance(node.func, ast.Name):
            if node.func.id not in SAFE_BUILTINS:
                self.violations.append(
                    f"Disallowed function call '{node.func.id}()' at line {node.lineno}"
                )
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr not in ("get", "lower", "upper", "strip"):
                self.violations.append(
                    f"Disallowed method call '.{node.func.attr}()' at line {node.lineno}"
                )
        else:
            self.violations.append(
                f"Disallowed dynamic call at line {node.lineno}"
            )
        self.generic_visit(node)


def inspect_python_snippet_safety(snippet: LinkedPythonSnippet) -> List[Finding]:
    """Check whether a Python snippet satisfies syntax and safety contracts."""
    findings: List[Finding] = []
    try:
        tree = ast.parse(snippet.code)
    except SyntaxError as e:
        findings.append(
            Finding(
                finding_id=f"SYNTAX_ERROR_{snippet.snippet_id}",
                severity=Severity.BLOCKER,
                defect_type="PYTHON_SYNTAX_ERROR",
                artifact_location=snippet.evidence_location,
                supporting_evidence=f"Syntax error in snippet '{snippet.snippet_id}': {e}",
                correction="Correct Python syntax error.",
            )
        )
        return findings

    validator = ASTSafetyValidator()
    validator.visit(tree)
    if validator.violations:
        findings.append(
            Finding(
                finding_id=f"RESTRICTED_SUBSET_VIOLATION_{snippet.snippet_id}",
                severity=Severity.BLOCKER,
                defect_type="UNSUPPORTED_PYTHON_SUBSET",
                artifact_location=snippet.evidence_location,
                supporting_evidence=(
                    f"Snippet '{snippet.snippet_id}' violates restricted Python subset: "
                    + "; ".join(validator.violations[:3])
                ),
                correction="Restrict script to approved subset (simple conditional logic, no imports/loops/exec).",
            )
        )

    # Check that the specified function exists
    func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if snippet.function_name not in func_names:
        findings.append(
            Finding(
                finding_id=f"MISSING_FUNCTION_{snippet.snippet_id}",
                severity=Severity.BLOCKER,
                defect_type="MISSING_FUNCTION_DEFINITION",
                artifact_location=snippet.evidence_location,
                supporting_evidence=f"Expected function '{snippet.function_name}' not defined in snippet '{snippet.snippet_id}'.",
                correction=f"Define function '{snippet.function_name}' in snippet.",
            )
        )

    return findings


class SafeASTInterpreter:
    """Pure, safe interpreter for evaluating restricted routing ASTs on ticket dicts.

    Does NOT execute untrusted Python code using eval/exec.
    """

    def __init__(self, func_def: ast.FunctionDef) -> None:
        self.func_def = func_def
        self.param_name = func_def.args.args[0].arg if func_def.args.args else "ticket"

    def evaluate(self, ticket: Dict[str, Any]) -> Optional[str]:
        """Execute the function body on the ticket and return the return value."""
        env = {self.param_name: ticket}
        for stmt in self.func_def.body:
            ret = self._exec_stmt(stmt, env)
            if ret is not None:
                return ret
        return None

    def _exec_stmt(self, stmt: ast.stmt, env: Dict[str, Any]) -> Optional[str]:
        if isinstance(stmt, ast.Assign):
            val = self._eval_expr(stmt.value, env)
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = val
            return None

        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                return str(self._eval_expr(stmt.value, env))
            return None

        if isinstance(stmt, ast.If):
            test_val = self._eval_expr(stmt.test, env)
            if test_val:
                for s in stmt.body:
                    ret = self._exec_stmt(s, env)
                    if ret is not None:
                        return ret
            else:
                for s in stmt.orelse:
                    ret = self._exec_stmt(s, env)
                    if ret is not None:
                        return ret

        return None

    def _eval_expr(self, expr: ast.expr, env: Dict[str, Any]) -> Any:
        if isinstance(expr, ast.Constant):
            return expr.value

        if isinstance(expr, ast.Name):
            return env.get(expr.id)

        if isinstance(expr, ast.Subscript):
            val = self._eval_expr(expr.value, env)
            idx = self._eval_expr(expr.slice, env) if hasattr(expr, "slice") else None
            if isinstance(val, dict) and idx is not None:
                return val.get(idx)
            return None

        if isinstance(expr, ast.Attribute):
            val = self._eval_expr(expr.value, env)
            if isinstance(val, dict):
                return val.get(expr.attr)
            return getattr(val, expr.attr, None)

        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute):
                obj = self._eval_expr(expr.func.value, env)
                method_name = expr.func.attr
                if method_name == "get" and isinstance(obj, dict):
                    key = self._eval_expr(expr.args[0], env) if len(expr.args) > 0 else None
                    default = self._eval_expr(expr.args[1], env) if len(expr.args) > 1 else None
                    return obj.get(key, default)
            elif isinstance(expr.func, ast.Name):
                fn_name = expr.func.id
                if fn_name in SAFE_BUILTINS:
                    args = [self._eval_expr(a, env) for a in expr.args]
                    return SAFE_BUILTINS[fn_name](*args)
            return None

        if isinstance(expr, ast.UnaryOp):
            operand = self._eval_expr(expr.operand, env)
            if isinstance(expr.op, ast.Not):
                return not bool(operand)

        if isinstance(expr, ast.BoolOp):
            if isinstance(expr.op, ast.And):
                return all(bool(self._eval_expr(v, env)) for v in expr.values)
            elif isinstance(expr.op, ast.Or):
                val = None
                for v in expr.values:
                    val = self._eval_expr(v, env)
                    if val:
                        return val
                return val

        if isinstance(expr, ast.Compare):
            left = self._eval_expr(expr.left, env)
            for op, comp in zip(expr.ops, expr.comparators):
                right = self._eval_expr(comp, env)
                if not self._eval_cmp(op, left, right):
                    return False
                left = right
            return True

        return None

    def _eval_cmp(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        if left is None or right is None:
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            return False

        try:
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Lt):
                return float(left) < float(right)
            if isinstance(op, ast.LtE):
                return float(left) <= float(right)
            if isinstance(op, ast.Gt):
                return float(left) > float(right)
            if isinstance(op, ast.GtE):
                return float(left) >= float(right)
            if isinstance(op, ast.In):
                return left in right
            if isinstance(op, ast.NotIn):
                return left not in right
        except (ValueError, TypeError):
            return False

        return False


def get_ast_interpreter(snippet: LinkedPythonSnippet) -> Optional[SafeASTInterpreter]:
    """Parse snippet and return safe interpreter for the specified function."""
    try:
        tree = ast.parse(snippet.code)
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == snippet.function_name:
            return SafeASTInterpreter(n)
    return None
