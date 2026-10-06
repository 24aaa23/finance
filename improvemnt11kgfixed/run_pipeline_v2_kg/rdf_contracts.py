"""Resolve declared RDF IRIs to contract keys without guessing names or values."""
import re


def class_key(value, schema):
    if not isinstance(value, str) or value in schema:
        return value
    iri = value[1:-1] if value.startswith('<') and value.endswith('>') else value
    matches = [name for name, details in schema.items()
               if details.get('class_iri') == iri or value in details.get('source_tables', [])]
    if len(matches) == 1:
        return matches[0]
    # Display spacing/case differs from code spelling. Resolve only simple local
    # identifiers; a foreign namespace must never fall back to its local name.
    if not matches and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]*', value):
        token = re.sub(r'[^a-z0-9]', '', value.lower())
        names = [name for name in schema if re.sub(r'[^a-z0-9]', '', name.lower()) == token]
        if len(names) == 1:
            return names[0]
    return value


def field_key(value, class_name, schema):
    if not isinstance(value, str):
        return value
    details = schema.get(class_key(class_name, schema), {})
    columns = details.get('columns', [])
    names = {column.get('name') if isinstance(column, dict) else column for column in columns}
    if value in names:
        return value
    if value in {'@id', '@subject'} and details.get('subject_field'):
        return details['subject_field']
    prefix = str(class_key(class_name, schema)) + '.'
    if value.startswith(prefix) and value[len(prefix):] in names:
        return value[len(prefix):]
    iri = value[1:-1] if value.startswith('<') and value.endswith('>') else value
    matches = {column['name'] for column in columns if isinstance(column, dict) and column.get('name')
               and (column.get('predicate_iri') == iri or column.get('ontology_attribute') == value)}
    if len(matches) == 1:
        return next(iter(matches))
    return value


def normalize_decomposition(selected, schema):
    """Normalize schema references only; preserve conditions, joins and grain."""
    branches = selected.get('subquestions', [])
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        source = class_key(branch.get('source_class'), schema)
        branch['source_class'] = source
        for key in ('required_fields', 'retrieval_grain'):
            if isinstance(branch.get(key), list):
                branch[key] = [field_key(value, source, schema) for value in branch[key]]
    owners = {branch.get('id'): branch.get('source_class') for branch in branches if isinstance(branch, dict)}
    requirements = selected.get('answer_requirements', {})
    if not isinstance(requirements, dict):
        return
    for predicate in requirements.get('predicates', []):
        if isinstance(predicate, dict):
            source = class_key(predicate.get('source_class'), schema)
            predicate['source_class'] = source
            if 'field' in predicate:
                predicate['field'] = field_key(predicate['field'], source, schema)
    for join in requirements.get('joins', []):
        if not isinstance(join, dict):
            continue
        for side in ('left', 'right'):
            source = owners.get(join.get(side + '_branch'))
            for suffix in ('_on', '_field'):
                key = side + suffix
                if isinstance(join.get(key), list):
                    join[key] = [field_key(value, source, schema) for value in join[key]]
                elif isinstance(join.get(key), str):
                    join[key] = field_key(join[key], source, schema)
    if isinstance(requirements.get('source_classes'), list):
        requirements['source_classes'] = [class_key(value, schema) for value in requirements['source_classes']]


def normalize_interpretation_refs(value, schema):
    """Normalize declared owner/operand references, leaving output aliases intact."""
    refs = list(value.get('bindings', [])) if isinstance(value.get('bindings'), list) else []
    refs += value.get('group_by', []) if isinstance(value.get('group_by'), list) else []
    for metric in value.get('metrics', []) if isinstance(value.get('metrics'), list) else []:
        if isinstance(metric, dict):
            for key in ('operands', 'entity_keys'):
                refs += metric.get(key, []) if isinstance(metric.get(key), list) else []
    for condition in value.get('filters', []) if isinstance(value.get('filters'), list) else []:
        if isinstance(condition, dict):
            refs += condition.get('operands', []) if isinstance(condition.get('operands'), list) else []
    for ref in refs:
        if isinstance(ref, dict) and isinstance(ref.get('table'), str):
            ref['table'] = class_key(ref['table'], schema)
            if 'column' in ref:
                ref['column'] = field_key(ref['column'], ref['table'], schema)
