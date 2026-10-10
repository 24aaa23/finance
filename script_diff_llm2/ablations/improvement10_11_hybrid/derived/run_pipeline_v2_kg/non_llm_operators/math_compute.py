"""Deterministic arithmetic, with a small, explicitly interpreted expression language."""

import ast
import math
import re
from typing import Any, Dict

import pandas as pd
from ..expression_syntax import normalize_expression


def _find_column(df: pd.DataFrame, name: Any, strict: bool = False) -> Any:
    if not isinstance(name, str) or not name:
        return None
    if name in df.columns:
        return name
    if not strict:
        canonical = re.sub(r"[^a-z0-9]+", "", name.lower())
        matches = [c for c in df.columns if re.sub(r"[^a-z0-9]+", "", str(c).lower()) == canonical]
        if len(matches) == 1:
            return matches[0]
    return None


def _numeric(series: pd.Series) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    if (series.notna() & converted.isna()).any():
        raise ValueError(f"Non-numeric value in arithmetic column: {series.name}")
    return converted


def _records(df: pd.DataFrame) -> list:
    cleaned = df.mask(df.isin([float("inf"), -float("inf")]))
    return cleaned.astype(object).where(pd.notna(cleaned), None).to_dict("records")


def expression_columns(expression: str) -> set[str]:
    """Validate syntax and report exact field dependencies without executing code."""
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
        raise ValueError("Expression must be a nonempty string of at most 4096 characters.")
    expression = normalize_expression(expression)
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 256:
        raise ValueError("Expression is too complex.")
    fields = set()

    def visit(node, depth=0):
        if depth > 40:
            raise ValueError("Expression is too deeply nested.")
        if isinstance(node, ast.Expression):
            visit(node.body, depth + 1)
        elif isinstance(node, ast.Name):
            if node.id != "null":
                fields.add(node.id)
        elif isinstance(node, ast.Constant):
            if node.value is not None and not isinstance(node.value, (str, bool, int, float)):
                raise ValueError("Only scalar literals are permitted.")
            if isinstance(node.value, (int, float)) and not math.isfinite(node.value):
                raise ValueError("Numeric literals must be finite.")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
            visit(node.left, depth + 1)
            visit(node.right, depth + 1)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            visit(node.operand, depth + 1)
        elif isinstance(node, ast.Compare) and all(isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in node.ops):
            if any((isinstance(part, ast.Name) and part.id == "null") or
                   (isinstance(part, ast.Constant) and part.value is None) for part in [node.left, *node.comparators]):
                raise ValueError("Comparisons to null are not presence tests. Use is_null/is_not_null, or direct arithmetic which already propagates nulls.")
            visit(node.left, depth + 1)
            for other in node.comparators:
                visit(other, depth + 1)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for child in node.values:
                visit(child, depth + 1)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            visit(node.operand, depth + 1)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            arities = {"abs": (1, 1), "round": (1, 2), "coalesce": (2, 20), "nullif": (2, 2), "column": (1, 1), "where": (3, 3),
                       "is_null": (1, 1), "is_not_null": (1, 1)}
            if name not in arities or not arities[name][0] <= len(node.args) <= arities[name][1]:
                raise ValueError(f"Unsupported function or argument count: {name}")
            if name == "column":
                arg = node.args[0]
                if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str) or not arg.value:
                    raise ValueError("column() requires one literal field name.")
                fields.add(arg.value)
            else:
                for arg in node.args:
                    visit(arg, depth + 1)
        else:
            raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")

    visit(tree)
    return fields


def _evaluate_expression(expression: str, df: pd.DataFrame, strict: bool) -> pd.Series:
    expression = normalize_expression(expression)
    columns = {}
    for field in expression_columns(expression):
        resolved = _find_column(df, field, strict)
        if resolved is None:
            raise ValueError(f"Expression column does not exist: {field}")
        # A field reference can copy a label, identifier, date or number. Only
        # arithmetic operators should require numeric values.
        columns[field] = df[resolved]

    def series(value):
        return value if isinstance(value, pd.Series) else pd.Series(value, index=df.index, dtype=object)

    def numeric(value):
        return _numeric(series(value))

    def boolean(value):
        values = series(value)
        if any(not isinstance(item, (bool, type(pd.NA))) for item in values.dropna().tolist()):
            raise ValueError("Conditional expressions require boolean comparisons.")
        return values.astype("boolean")

    def calculate(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return None if node.id == "null" else columns[node.id]
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return ~boolean(calculate(node.operand))
            value = numeric(calculate(node.operand))
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BoolOp):
            values = [boolean(calculate(child)) for child in node.values]
            result = values[0]
            for value in values[1:]:
                result = result & value if isinstance(node.op, ast.And) else result | value
            return result
        if isinstance(node, ast.Compare):
            left = calculate(node.left)
            result = pd.Series(True, index=df.index, dtype="boolean")
            for op, other in zip(node.ops, node.comparators):
                right = calculate(other)
                a, b = series(left), series(right)
                if pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b) or any(
                        isinstance(value, (int, float)) and not isinstance(value, bool) for value in (left, right)):
                    a, b = numeric(left), numeric(right)
                method = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le", ast.Gt: "gt", ast.GtE: "ge"}[type(op)]
                result &= getattr(a, method)(b).astype("boolean").mask(a.isna() | b.isna(), pd.NA)
                left = right
            return result
        if isinstance(node, ast.BinOp):
            left, right = numeric(calculate(node.left)), numeric(calculate(node.right))
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right.mask(right.eq(0))
            if isinstance(node.op, ast.Mod):
                return left % right.mask(right.eq(0))
            if isinstance(node.op, ast.Pow):
                if right.abs().gt(1000).any():
                    raise ValueError("Exponent magnitude must not exceed 1000.")
                return left.astype(float).pow(right)
        if isinstance(node, ast.Call):
            name = node.func.id
            if name == "column":
                return columns[node.args[0].value]
            args = [calculate(arg) for arg in node.args]
            if name == "abs":
                return numeric(args[0]).abs()
            if name == "round":
                digits = args[1] if len(args) == 2 else 0
                if not isinstance(digits, (int, float)) or int(digits) != digits or not -15 <= digits <= 15:
                    raise ValueError("round precision must be an integer literal between -15 and 15.")
                return numeric(args[0]).round(int(digits))
            if name == "coalesce":
                result = series(args[0]).astype(object)
                for arg in args[1:]:
                    result = result.where(result.notna(), series(arg))
                return result
            if name == "nullif":
                return series(args[0]).mask(series(args[0]).eq(series(args[1])))
            if name == "where":
                return series(args[1]).astype(object).where(boolean(args[0]).fillna(False), series(args[2]))
            if name in {"is_null", "is_not_null"}:
                return series(args[0]).isna() if name == "is_null" else series(args[0]).notna()
        raise ValueError("Unsupported expression.")

    result = series(calculate(ast.parse(expression, mode="eval").body))
    return result.mask(result.isin([float("inf"), -float("inf")]))


def pre_programmed_math_compute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Apply an expression per row, or a declared scalar aggregate.

    Expressions support + - * / % **, unary signs, abs, round, coalesce, nullif,
    and column('exact field'). References and coalesce preserve scalar types;
    arithmetic requires numeric operands. No Python evaluation or attribute access occurs.
    Division by zero and arithmetic on null inputs produce null, not infinity.
    """
    try:
        df = pd.DataFrame(inputs.get("data", []))
        schema = inputs.get("input_schema") or []
        if df.empty and schema:
            df = pd.DataFrame(columns=schema)
        strict = bool(inputs.get("strict_spec"))
        operation = str(inputs.get("operation") or "").lower()
        expression = inputs.get("expression")
        output = inputs.get("output_column") or "computed_value"
        if not isinstance(output, str) or not output:
            raise ValueError("output_column must be a nonempty string.")
        if expression is not None:
            expression_columns(expression)
            if not df.empty or len(df.columns):
                df[output] = _evaluate_expression(expression, df, strict)
            rows = _records(df)
            return {"data": rows, "computed_result": rows, "row_count": len(rows)}

        raw_target = inputs.get("target_column") or inputs.get("column") or inputs.get("input_column") or inputs.get("target_columns")
        if operation in {"sum", "avg", "average", "mean", "count", "count_distinct", "nunique", "min", "max"}:
            if inputs.get("group_by"):
                raise ValueError("Grouped aggregates require Filter_Aggregate; Math_Compute scalar aggregates do not group rows.")
            targets = raw_target if isinstance(raw_target, list) else [raw_target]
            row = {}
            for target in targets:
                name = output if len(targets) == 1 else f"{operation}_{target}"
                if operation == "count" and target in (None, "*"):
                    if inputs.get("distinct"):
                        raise ValueError("Distinct count requires a target column.")
                    row[name] = len(df)
                    continue
                if not isinstance(target, str) or not target or target == "*":
                    raise ValueError(f"A target column is required for {operation}.")
                col = _find_column(df, target, strict)
                if col is None and (not df.empty or len(df.columns)):
                    raise ValueError(f"Declared target column does not exist: {target}")
                values = df[col] if col is not None else pd.Series([], dtype=float)
                if operation in {"count", "count_distinct", "nunique"}:
                    distinct = operation != "count" or bool(inputs.get("distinct"))
                    value = values.nunique(dropna=True) if distinct else values.count()
                else:
                    values = _numeric(values)
                    if operation == "sum":
                        value = values.sum(min_count=1)
                    else:
                        value = getattr(values, {"avg": "mean", "average": "mean"}.get(operation, operation))()
                row[name] = None if pd.isna(value) else value.item() if hasattr(value, "item") else value
            return {"data": [row], "computed_result": row, "row_count": 1}

        templates = {
            "add": "L + R", "addition": "L + R", "multiply": "L * R", "product": "L * R",
            "difference": "L - R", "subtract": "L - R", "absolute_gap": "abs(L - R)",
            "ratio": "L / R", "divide": "L / R", "percentage": "(L / R) * 100",
            "percentage_diff": "((R - L) / L) * 100", "percentage_change": "((R - L) / L) * 100",
        }
        if operation not in templates:
            raise ValueError(f"Unsupported mathematical operation: {operation or '<missing>'}")
        left_name = inputs.get("left_column") or inputs.get("base_col")
        right_name = inputs.get("right_column") or raw_target
        if not isinstance(left_name, str) or not isinstance(right_name, str):
            raise ValueError("Arithmetic requires left_column and right_column, or an expression.")
        if not df.empty or len(df.columns):
            left, right = _find_column(df, left_name, strict), _find_column(df, right_name, strict)
            if left is None or right is None:
                raise ValueError(f"Columns {left_name} and/or {right_name} not found in data.")
            operands = pd.DataFrame({"L": df[left], "R": df[right]})
            df[output] = _evaluate_expression(templates[operation], operands, True)
        rows = _records(df)
        return {"data": rows, "computed_result": rows, "row_count": len(rows)}
    except Exception as exc:
        return {"data": [], "computed_result": None, "row_count": 0, "error": str(exc), "code": "MATH_COMPUTE_ERROR"}
