"""Follow declared field copies and joins without inspecting execution rows."""
import ast
from .spec_contracts import flatten_identifiers


def copied_column(expression):
    try:
        node = ast.parse(expression, mode='eval').body
    except (TypeError, ValueError, SyntaxError):
        return None
    if isinstance(node, ast.Name):
        return node.id
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'column' and len(node.args) == 1 and not node.keywords
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def field_origins(spec, branches=()):
    """Return per-dataset raw origins; calculated fields retain their own identity."""
    schemas = spec.get('dataset_schemas', {})
    steps = spec.get('execution_steps', [])
    owners = {}
    for branch in branches:
        sources = {r.get('class') for r in branch.get('retrieval_specs', []) if isinstance(r, dict)}
        if len(sources) == 1:
            owners[str(branch['id'])] = next(iter(sources))
    generated = {s['id'] for s in steps}
    origins = {name: {field: frozenset({(owners.get(name), field)}) for field in fields}
               for name, fields in schemas.items() if name not in generated}
    for step in steps:
        inputs = step.get('inputs', [])
        left = dict(origins.get(inputs[0], {})) if inputs else {}
        op = step.get('operator')
        if op == 'Integrate':
            from .relational import join_column_maps
            keys = flatten_identifiers(step.get('join_key'))
            lkeys = flatten_identifiers(step.get('left_on')) or keys
            rkeys = flatten_identifiers(step.get('right_on')) or keys
            for name in inputs[1:]:
                right = origins.get(name, {})
                lmap, rmap, _ = join_column_maps(list(left), list(right), lkeys, rkeys,
                                               step.get('suffixes', ['', '_right']))
                merged = {lmap[field]: value for field, value in left.items()}
                merged.update({rmap[field]: value for field, value in right.items()
                               if rmap[field] not in merged})
                # Equality is guaranteed only for surviving inner-join rows.
                if step.get('join_type') == 'inner':
                    for lkey, rkey in zip(lkeys, rkeys):
                        value = left.get(lkey, frozenset()) | right.get(rkey, frozenset())
                        merged[lmap[lkey]] = merged[rmap[rkey]] = value
                left = merged
        elif op == 'Math_Compute':
            field = copied_column(step.get('expression'))
            target = step.get('output_column')
            calculated = frozenset({('@calculated:' + step['id'], target)})
            left[target] = left.get(field, calculated) if field else calculated
        elif op in {'Bucket', 'Date_Extract'}:
            target = step.get('output_column')
            left[target] = frozenset({('@calculated:' + step['id'], target)})
        elif op == 'Filter_Aggregate' and step.get('operation') not in {'filter', 'where', 'distinct'}:
            target = step.get('output_column')
            left[target] = frozenset({('@calculated:' + step['id'], target)})
        elif op in {'Set_Union', 'Union', 'Combine_Scalars'}:
            left = {}
            for name in inputs:
                for field, value in origins.get(name, {}).items():
                    left[field] = left.get(field, frozenset()) | value
        origins[step['id']] = {field: left.get(field, frozenset({(None, field)}))
                               for field in schemas.get(step['id'], [])}
    return origins


def shared_join_keys(spec):
    """Track keys the executor coalesces under one name, not row equalities."""
    schemas = spec.get('dataset_schemas', {})
    known = {}
    for step in spec.get('execution_steps', []):
        inputs = step.get('inputs', [])
        left = dict(known.get(inputs[0], {})) if inputs else {}
        if step.get('operator') == 'Integrate':
            from .relational import join_column_maps
            keys = flatten_identifiers(step.get('join_key'))
            lkeys = flatten_identifiers(step.get('left_on')) or keys
            rkeys = flatten_identifiers(step.get('right_on')) or keys
            fields = schemas.get(inputs[0], []) if inputs else []
            suffixes = step.get('suffixes', ['', '_right'])
            for name in inputs[1:]:
                right_fields = schemas.get(name, [])
                lmap, rmap, combined = join_column_maps(fields, right_fields, lkeys, rkeys, suffixes)
                merged = {lmap[field]: shadows for field, shadows in left.items() if field in lmap}
                merged.update({rmap[field]: shadows for field, shadows in known.get(name, {}).items() if field in rmap})
                for a, b in zip(lkeys, rkeys):
                    if a == b and a in fields and b in right_fields and suffixes[1]:
                        merged[lmap[a]] = frozenset({a + suffixes[1]})
                left, fields = merged, combined
        target = step.get('output_column')
        if target:
            if step.get('operator') == 'Math_Compute':
                source = copied_column(step.get('expression'))
                inherited = left.get(source)
                left.pop(target, None)
                if inherited:
                    left[target] = inherited
            else:
                left.pop(target, None)
        known[step['id']] = {field: shadows for field, shadows in left.items()
                              if field in schemas.get(step['id'], [])}
    return known


def normalize_coalesced_key_expression(expression, fields, merged_keys):
    """Repair only a redundant coalesce of an explicitly shared join key.

    An absent independent column stays an error. Existing suffixed columns are
    never replaced, and field access outside this exact coalesce stays strict.
    """
    try:
        tree = ast.parse(expression, mode='eval')
    except (ValueError, TypeError, SyntaxError):
        return expression
    changed = False
    class Repair(ast.NodeTransformer):
        def visit_Call(self, node):
            nonlocal changed
            node = self.generic_visit(node)
            if not (isinstance(node.func, ast.Name) and node.func.id == 'coalesce'
                    and len(node.args) == 2 and not node.keywords):
                return node
            names = [copied_column(ast.unparse(arg)) for arg in node.args]
            for index in (0, 1):
                base, shadow = names[index], names[1 - index]
                if base in fields and shadow not in fields and shadow in merged_keys.get(base, frozenset()):
                    changed = True
                    return node.args[index]
            return node
    tree = Repair().visit(tree)
    return ast.unparse(tree) if changed else expression
