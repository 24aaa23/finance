"""Validate the computation contract against runtime schema, never answers."""
import re
from typing import Any


_REQUIREMENT_GLUE = {
    'a', 'an', 'the', 'of', 'for', 'to', 'from', 'by', 'with', 'and', 'or',
    'is', 'are', 'was', 'were', 'be', 'that', 'which', 'who', 'what', 'how',
    'return', 'select', 'retrieve', 'show', 'list', 'find', 'compute',
    'filter', 'filtered', 'group', 'grouped', 'output', 'field', 'column',
    'value', 'values', 'equals', 'equal', 'given', 'specific', 'each',
    'join', 'joined', 'projection', 'predicate', 'aggregation', 'aggregate',
    'record', 'entity', 'metric', 'measure', 'data', 'source', 'table',
}


def _requirement_terms(value: str) -> set[str]:
    return {term[:-1] if term.endswith('s') and len(term) > 3 else term
            for term in re.findall(r'[a-z0-9]+', value.casefold())}


def column_names(details: dict) -> set[str]:
    if not isinstance(details, dict):
        return set()
    return (set(details.get('column_names', [])) | {
        item.get('name') if isinstance(item, dict) else item
        for item in details.get('columns', [])
    }) - {None}


def split_contract_errors(errors: list[str]) -> tuple[list[str], list[str]]:
    """Keep provenance omissions visible without blocking a grounded plan."""
    warnings = []
    blocking = []
    for error in errors:
        if error.startswith(('Requirement introduces unsupported terms:',
                             'Invalid requirement implementation:',
                             'Requirement has no implementation:')) or error == 'Every subquery needs a requirement ledger.' or re.fullmatch(
            r'(?:filters|group_by|measures)\.\d+ has no quoted requirement\.', error
        ):
            warnings.append(error)
        else:
            blocking.append(error)
    return blocking, warnings


def validate_query_spec(spec: Any, schema: dict, question: str = '') -> list[str]:
    if not isinstance(spec, dict) or not spec:
        return ['Query_Spec is empty or not an object.']
    errors = list(spec.get('contract_errors') or [])
    unresolved = spec.get('unresolved_requirements') or []
    if unresolved:
        errors.append(f'Unresolved requirements: {unresolved}')
    if spec.get('measure_recovery_failed'):
        errors.append('Analytic plan has no measures after recovery.')
    required = spec.get('required_classes', [])
    if not isinstance(required, list):
        return errors + ['required_classes must be a list.']
    for source in required:
        if not isinstance(source, str) or source not in schema:
            errors.append(f'Unknown source: {source}')
    base = spec.get('base_entity')
    if base and (not isinstance(base, str) or base not in schema):
        errors.append(f'Unknown base_entity: {base}')
        base = None
    names = set()
    aliases = {item.get('output_name') for key in ('group_by', 'measures')
               for item in (spec.get(key) if isinstance(spec.get(key), list) else [])
               if isinstance(item, dict) and isinstance(item.get('output_name'), str)}
    for key in ('group_by', 'measures', 'filters'):
        items = spec.get(key, [])
        if not isinstance(items, list):
            errors.append(f'{key} must be a list.')
            continue
        for index, item in enumerate(items):
            path = f'{key}.{index}'
            if not isinstance(item, dict):
                errors.append(f'{path} must be an object.')
                continue
            source = item.get('source_class') or base
            field = item.get('field')
            if not isinstance(source, str) or (field is not None and not isinstance(field, str)):
                errors.append(f'{path}: source_class and field must be names.')
                continue
            operands = item.get('formula_fields') or []
            if not isinstance(operands, list) or not all(isinstance(x, str) for x in operands):
                errors.append(f'{path}: formula_fields must be a list of names.')
                operands = []
            if source == 'derived' or item.get('operand_kind') == 'aliases':
                if key == 'filters':
                    if field not in aliases:
                        errors.append(f'{path}: unknown derived alias {field!r}.')
                elif not item.get('formula'):
                    errors.append(f'{path}: derived measure needs an expression.')
                for operand in operands:
                    if operand not in aliases or operand == item.get('output_name'):
                        errors.append(f'{path}: unknown or self-referencing formula operand {operand!r}.')
            else:
                if source not in schema:
                    errors.append(f'{path}: unknown source {source!r}.')
                elif field and field != '*' and field not in column_names(schema[source]):
                    errors.append(f'{path}: field {field!r} is not in {source!r}.')
                for operand in operands:
                    if source in schema and operand not in column_names(schema[source]):
                        errors.append(f'{path}: unknown formula operand {operand!r}.')
            if key == 'measures':
                if item.get('operand_kind', 'aliases' if source == 'derived' else 'physical') not in {'physical', 'aliases'}:
                    errors.append(f'{path}: operand_kind must be physical or aliases.')
                population = item.get('population_filters', [])
                if not isinstance(population, list):
                    errors.append(f'{path}: population_filters must be a list.')
                elif population:
                    scoped = {'base_entity': source, 'filters': population,
                              'output_schema': list(column_names(schema.get(source, {})))[:1]}
                    for error in split_contract_errors(validate_query_spec(scoped, schema))[0]:
                        errors.append(f'{path}.population_filters: {error}')
                aggregate = item.get('aggregate_filters', [])
                if not isinstance(aggregate, list):
                    errors.append(f'{path}: aggregate_filters must be a list.')
                else:
                    for j, predicate in enumerate(aggregate):
                        if not isinstance(predicate, dict) or predicate.get('field') != item.get('output_name'):
                            errors.append(f'{path}.aggregate_filters.{j}: predicate must reference the owning measure alias.')
                            continue
                        if predicate.get('stage') not in {'entity', 'final_group'}:
                            errors.append(f'{path}.aggregate_filters.{j}: explicit entity or final_group stage is required.')
                        if predicate.get('scope', 'population') not in {'population', 'metric'}:
                            errors.append(f'{path}.aggregate_filters.{j}: invalid predicate scope.')
                        if str(predicate.get('operator', '')).lower() not in {'=', '!=', '<>', '>', '>=', '<', '<=', 'between', 'in', 'not_in', 'is_null', 'is_not_null'}:
                            errors.append(f'{path}.aggregate_filters.{j}: unsupported operator.')
                        if predicate.get('operator') not in {'is_null', 'is_not_null'} and 'value' not in predicate:
                            errors.append(f'{path}.aggregate_filters.{j}: missing value.')
                for op in ('per_entity_operation', 'final_operation'):
                    operation = item.get(op)
                    if operation and str(operation).upper() not in {'SUM', 'AVG', 'COUNT', 'COUNT_DISTINCT', 'MIN', 'MAX'}:
                        errors.append(f'{path}: unsupported {op} {operation!r}.')
                if not field and not item.get('formula') and not any(
                    str(item.get(op, '')).upper() == 'COUNT' for op in ('per_entity_operation', 'final_operation')
                ):
                    errors.append(f'{path}: measure needs a field or formula.')
            if key == 'filters':
                if item.get('value_type') == 'field':
                    other_field = item.get('value')
                    if not isinstance(other_field, str) or other_field not in column_names(schema.get(source, {})):
                        errors.append(f'{path}: unknown comparison field {other_field!r}.')
                if not field:
                    errors.append(f'{path}: filter needs a field.')
                operator = str(item.get('operator') or '').lower()
                if operator not in {'=', '!=', '<>', '>', '>=', '<', '<=', 'contains', 'not_contains', 'between', 'in', 'not_in', 'is_null', 'is_not_null'}:
                    errors.append(f'{path}: unsupported operator {operator!r}.')
                if operator not in {'is_null', 'is_not_null'} and 'value' not in item:
                    errors.append(f'{path}: filter is missing a value.')
            if key in ('group_by', 'measures'):
                name = item.get('output_name')
                if not isinstance(name, str) or not name:
                    errors.append(f'{path}: output_name is required.')
                elif name in names:
                    errors.append(f'Duplicate output alias: {name}')
                else:
                    names.add(name)
    dependencies = {item.get('output_name'): set(x for x in (item.get('formula_fields') or []) if isinstance(x, str)) & aliases
                    for item in (spec.get('measures') if isinstance(spec.get('measures'), list) else [])
                    if isinstance(item, dict) and isinstance(item.get('output_name'), str)
                    and isinstance(item.get('formula_fields') or [], list)
                    and (item.get('source_class') == 'derived' or item.get('operand_kind') == 'aliases')}
    visited, active = set(), set()
    def cyclic(name):
        if name in active:
            return True
        if name in visited:
            return False
        active.add(name)
        if any(cyclic(operand) for operand in dependencies.get(name, set())):
            return True
        active.remove(name)
        visited.add(name)
        return False
    if any(cyclic(name) for name in dependencies):
        errors.append('Derived measure dependencies contain a cycle.')
    output = spec.get('output_schema')
    if not isinstance(output, list) or not output or not all(isinstance(x, str) and x for x in output):
        errors.append('output_schema must contain named output columns.')
    elif len(output) != len(set(output)):
        errors.append('output_schema contains duplicate column names.')
    else:
        physical = set().union(*(column_names(details) for details in schema.values()))
        for name in output:
            if name not in names and name not in physical:
                errors.append(f'Unknown output column: {name}')
    # Measures can be internal operands or ranking keys. output_schema declares
    # the final projection; it need not expose every intermediate calculation.
    ranking = spec.get('ranking') or {}
    if not isinstance(ranking, dict):
        errors.append('ranking must be an object.')
    elif ranking.get('required'):
        if ranking.get('direction') not in {'asc', 'desc', 'ASC', 'DESC'}:
            errors.append('Ranking direction must be asc or desc.')
        if ranking.get('metric') not in names:
            errors.append('Ranking metric must be a planned output alias.')
        limit = ranking.get('limit')
        if limit is not None and (type(limit) is not int or limit <= 0):
            errors.append('Ranking limit must be a positive integer or null.')
    requirements = spec.get('requirements', [])
    if not isinstance(requirements, list):
        errors.append('requirements must be a list.')
    elif question and not requirements:
        errors.append('Every subquery needs a requirement ledger.')
    else:
        implemented_items = set()
        schema_terms = set()
        for source, details in schema.items():
            schema_terms |= _requirement_terms(str(source))
            for column in column_names(details):
                schema_terms |= _requirement_terms(str(column))
        allowed_terms = _requirement_terms(question) | schema_terms | _REQUIREMENT_GLUE
        for requirement in requirements:
            if not isinstance(requirement, dict):
                errors.append('Each requirement must be an object.')
                continue
            text = requirement.get('text')
            if not isinstance(text, str) or not text.strip():
                errors.append('Requirement text is missing.')
                continue
            unsupported_terms = _requirement_terms(text) - allowed_terms
            if unsupported_terms:
                errors.append(f'Requirement introduces unsupported terms: {sorted(unsupported_terms)}')
            references = requirement.get('implemented_by')
            if not isinstance(references, list) or not references:
                errors.append(f'Requirement has no implementation: {text}')
                continue
            for reference in references:
                value = spec
                try:
                    for part in str(reference).split('.'):
                        value = value[int(part)] if isinstance(value, list) else value[part]
                    if value is None or value == [] or value == {}:
                        raise ValueError('Empty implementation')
                except (KeyError, TypeError, ValueError, IndexError):
                    errors.append(f'Invalid requirement implementation: {reference}')
                    continue
                parts = str(reference).split('.')
                if len(parts) >= 2 and parts[0] in {'filters', 'group_by', 'measures'} and parts[1].isdigit():
                    implemented_items.add((parts[0], int(parts[1])))
                if str(reference).startswith('filters.') and isinstance(value, dict):
                    literal = value.get('value')
                    if isinstance(literal, str) and literal.casefold() not in text.casefold():
                        errors.append(f'Filter value {literal!r} is not supported by its quoted requirement {text!r}.')
        for key in ('filters', 'group_by', 'measures'):
            items = spec.get(key)
            if isinstance(items, list):
                for index in range(len(items)):
                    if (key, index) not in implemented_items:
                        if key == 'measures' and spec.get('query_type') == 'point_lookup':
                            item = items[index]
                            if isinstance(item, dict) and not item.get('formula') and not item.get('per_entity_operation') and not item.get('final_operation'):
                                field_terms = _requirement_terms(str(item.get('field') or ''))
                                if field_terms and field_terms <= _requirement_terms(question):
                                    continue
                        errors.append(f'{key}.{index} has no quoted requirement.')
    return list(dict.fromkeys(errors))
