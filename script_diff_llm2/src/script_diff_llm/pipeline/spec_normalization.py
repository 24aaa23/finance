"""Lossless syntax repairs supported by the plan and runtime schema.

This module has no question-family rules, metric definitions or answer access.
Ambiguous ownership and aggregation stages are deliberately left for repair.
"""
from script_diff_llm.pipeline.contracts import column_names


def normalize_plan_syntax(plan: dict, schema: dict) -> None:
    """Normalize a private plan copy in place and record every inference."""
    repairs = plan.setdefault('structural_repairs', [])
    if not isinstance(repairs, list):
        repairs = plan['structural_repairs'] = []

    def change(item, key, value, path, evidence):
        old = item.get(key)
        if old == value:
            return
        item[key] = value
        record = {'path': f'{path}.{key}', 'from': old, 'to': value, 'evidence': evidence}
        if record not in repairs:
            repairs.append(record)

    declared = {s for s in plan.get('required_classes', []) if isinstance(s, str) and s in schema}
    base = plan.get('base_entity')
    if isinstance(base, str) and base in schema:
        declared.add(base)
    declared.update(i['source_class'] for key in ('group_by', 'filters', 'measures')
                    for i in plan.get(key, []) if isinstance(i, dict)
                    and isinstance(i.get('source_class'), str) and i['source_class'] in schema)
    aliases = {i.get('output_name') for key in ('group_by', 'measures')
               for i in plan.get(key, []) if isinstance(i, dict) and isinstance(i.get('output_name'), str)}

    def physical_owner(item):
        operands = item.get('formula_fields') or []
        if not isinstance(operands, list) or not all(isinstance(f, str) for f in operands):
            return None
        fields = set(operands)
        if item.get('field') and item['field'] != '*':
            if not isinstance(item['field'], str):
                return None
            fields.add(item['field'])
        if not fields or not all(isinstance(f, str) for f in fields):
            return None
        candidates = {s for s in schema if fields <= column_names(schema[s])}
        if len(candidates) > 1 and declared:
            candidates &= declared
        return next(iter(candidates)) if len(candidates) == 1 else None

    # Sharing a foreign key alone cannot establish a logical base's owner.
    # Use the plan's explicit key projection or distinct key count instead.
    if isinstance(base, str) and base not in schema and base != 'derived' and plan.get('entity_key'):
        entity_key = plan['entity_key']
        owners = set()
        for key in ('group_by', 'measures'):
            for item in plan.get(key, []):
                if not isinstance(item, dict) or item.get('field') != entity_key:
                    continue
                source = item.get('source_class')
                projection = not any(item.get(k) for k in ('formula', 'per_entity_operation', 'final_operation'))
                distinct_count = item.get('requires_distinct') and any(
                    str(item.get(k, '')).upper() in {'COUNT', 'COUNT_DISTINCT'}
                    for k in ('per_entity_operation', 'final_operation'))
                if isinstance(source, str) and source in schema and entity_key in column_names(schema[source]) and (projection or distinct_count):
                    owners.add(source)
        if len(owners) == 1:
            owner = next(iter(owners))
            change(plan, 'base_entity', owner, 'plan', 'unique explicit owner of projected or distinctly counted entity key')
            if base in plan.get('required_classes', []):
                change(plan, 'required_classes', [owner if s == base else s for s in plan['required_classes']],
                       'plan', 'logical base bound by explicit entity-key ownership')
            for key in ('group_by', 'filters', 'measures'):
                for index, item in enumerate(plan.get(key, [])):
                    if isinstance(item, dict) and item.get('source_class') == base:
                        change(item, 'source_class', owner, f'{key}.{index}', 'same explicitly bound logical base')
            base = owner
            declared.add(owner)

    # Resolve other logical source labels using every referenced physical field.
    # No fuzzy name matching or domain-specific dictionary is involved.
    logical = {}
    for key in ('group_by', 'filters', 'measures'):
        for index, item in enumerate(plan.get(key, [])):
            if not isinstance(item, dict):
                continue
            source = item.get('source_class')
            if isinstance(source, str) and source not in schema and source not in {'physical', 'derived'}:
                logical.setdefault(source, []).append((f'{key}.{index}', item))
    for label, entries in logical.items():
        fields = []
        valid = True
        for _, item in entries:
            operands = item.get('formula_fields') or []
            if not isinstance(operands, list) or not all(isinstance(f, str) for f in operands):
                valid = False
                break
            fields.extend(operands)
            if item.get('field') and item.get('field') != '*':
                fields.append(item['field'])
        owner = physical_owner({'formula_fields': fields}) if valid else None
        if not owner:
            continue
        for path, item in entries:
            change(item, 'source_class', owner, path, 'every reference to logical source resolves to one physical owner')
        if label == base:
            change(plan, 'base_entity', owner, 'plan', 'logical source has unique physical ownership')
            base = owner
        if label in plan.get('required_classes', []):
            change(plan, 'required_classes', [owner if s == label else s for s in plan['required_classes']],
                   'plan', 'all references to logical source resolved')

    for key in ('group_by', 'filters', 'measures'):
        for index, item in enumerate(plan.get(key, [])):
            if not isinstance(item, dict):
                continue
            path = f'{key}.{index}'
            source = item.get('source_class') or base
            # "physical" is an operand category, never a source-name alias.
            # Do not choose the base table when another declared owner fits.
            if source == 'physical' and 'physical' not in schema:
                owner = physical_owner(item)
                if owner:
                    change(item, 'source_class', owner, path, 'unique declared source containing every physical operand')
                    source = owner
            if key != 'measures':
                continue
            operands = item.get('formula_fields') or []
            field = item.get('field')
            # A DISTINCT count of the explicitly declared entity key has a
            # defined identity owner even when joined fact sources share it.
            # Do not apply this to ordinary row counts or arbitrary fields.
            distinct_identity = (item.get('requires_distinct') or any(
                str(item.get(k, '')).upper() == 'COUNT_DISTINCT' for k in ('per_entity_operation', 'final_operation')))
            count = any(str(item.get(k, '')).upper() in {'COUNT', 'COUNT_DISTINCT'}
                        for k in ('per_entity_operation', 'final_operation'))
            entity_key = plan.get('entity_key')
            if (source in ('physical', 'derived') and source not in schema and not item.get('formula')
                    and distinct_identity and count and field in (None, '*', entity_key)
                    and isinstance(base, str) and base in schema and isinstance(entity_key, str)
                    and entity_key in column_names(schema[base])):
                change(item, 'source_class', base, path, 'distinct count of explicitly declared base entity identity')
                change(item, 'field', entity_key, path, 'declared entity key supplies distinct-count operand')
                source, field = base, entity_key
            # A field aggregate marked "derived" is still a physical aggregate
            # if it has no expression and its field is not a planned alias.
            physical_expression = (item.get('formula') and isinstance(operands, list)
                                   and operands and all(isinstance(f, str) and f not in aliases for f in operands))
            if source == 'derived' and ((not item.get('formula') and isinstance(field, str) and field not in aliases)
                                        or physical_expression):
                owner = physical_owner(item)
                if owner:
                    change(item, 'source_class', owner, path, 'operands have a unique physical owner and do not reference planned aliases')
                    source = owner
                    if physical_expression:
                        change(item, 'formula_stage', 'row', path, 'expression operands are physical columns, not aggregate aliases')
            expected = None
            if not isinstance(operands, list) or not all(isinstance(f, str) for f in operands):
                operands = []  # Original malformed value is retained for validation.
            if (isinstance(source, str) and source in schema and item.get('formula')
                    and operands and all(f in aliases and f != item.get('output_name') for f in operands)
                    and not any(f in column_names(schema[source]) for f in operands)
                    and item.get('formula_stage') == 'final_group'):
                change(item, 'source_class', 'derived', path, 'final-group expression references only independently planned aliases')
                source = 'derived'
                expected = 'aliases'
            if isinstance(source, str) and source in schema:
                physical = column_names(schema[source])
                if (not field or field == '*' or (isinstance(field, str) and field in physical)) and all(f in physical for f in operands):
                    expected = 'physical'
            elif source == 'derived' and item.get('formula') and operands and all(f in aliases for f in operands):
                expected = 'aliases'
            if expected:
                change(item, 'operand_kind', expected, path, 'operand names resolve against the declared source or planned aliases')
            aggregate = item.get('aggregate_filters', [])
            if not isinstance(aggregate, list):
                continue
            stages = []
            if item.get('per_entity_operation'):
                stages.append('entity')
            if item.get('final_operation') or (source == 'derived' and item.get('formula_stage') == 'final_group'):
                stages.append('final_group')
            for j, predicate in enumerate(aggregate):
                if not isinstance(predicate, dict):
                    continue
                pred_path = f'{path}.aggregate_filters.{j}'
                alias = item.get('output_name')
                alternate = predicate.get('output_name')
                # Conflicting explicit names are not silently overwritten.
                if alias and not predicate.get('field') and alternate in (None, alias):
                    change(predicate, 'field', alias, pred_path, 'predicate nested under its owning measure')
                if not predicate.get('stage') and len(stages) == 1:
                    change(predicate, 'stage', stages[0], pred_path, 'exactly one declared aggregation stage')
    # Remove a reserved token only after every occurrence was resolved. Unknown
    # real sources and ambiguously placed physical operands still block execution.
    unresolved_physical = base == 'physical' or any(
        isinstance(i, dict) and i.get('source_class') == 'physical'
        for key in ('group_by', 'filters', 'measures') for i in plan.get(key, []))
    if 'physical' not in schema and not unresolved_physical and 'physical' in plan.get('required_classes', []):
        change(plan, 'required_classes', [s for s in plan['required_classes'] if s != 'physical'],
               'plan', 'all physical operand placeholders resolved to runtime sources')

    # The same plain projection may be emitted once as a grouping key and once
    # as a non-aggregate measure. Keep the grouping key, preserving all ledger
    # references and later measure indices. Conflicting computations still fail.
    retained, references = [], {}
    for index, measure in enumerate(plan.get('measures', [])):
        target = None
        if isinstance(measure, dict) and not any(measure.get(k) for k in (
                'formula', 'formula_fields', 'per_entity_operation', 'final_operation',
                'population_filters', 'aggregate_filters', 'unit')):
            matches = [j for j, group in enumerate(plan.get('group_by', []))
                       if isinstance(group, dict) and not group.get('formula') and not group.get('bucket_strategy')
                       and all(group.get(k) == measure.get(k) for k in ('source_class', 'field', 'output_name'))
                       and isinstance(group.get('source_class'), str) and group['source_class'] in schema
                       and isinstance(group.get('field'), str) and group['field'] in column_names(schema[group['source_class']])]
            if len(matches) == 1:
                target = f'group_by.{matches[0]}'
        if target:
            references[f'measures.{index}'] = target
            record = {'path': f'measures.{index}', 'from': measure, 'to': target,
                      'evidence': 'identical physical projection already declared as a grouping key'}
            if record not in repairs:
                repairs.append(record)
        else:
            references[f'measures.{index}'] = f'measures.{len(retained)}'
            retained.append(measure)
    plan['measures'] = retained
    requirements = plan.get('requirements', [])
    for requirement in requirements if isinstance(requirements, list) else []:
        if not isinstance(requirement, dict) or not isinstance(requirement.get('implemented_by'), list):
            continue
        updated = []
        for reference in requirement['implemented_by']:
            parts = str(reference).split('.')
            prefix = '.'.join(parts[:2])
            updated.append('.'.join([references[prefix], *parts[2:]]) if prefix in references else reference)
        requirement['implemented_by'] = updated
