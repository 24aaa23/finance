"""Conservative checks of directly compared RDF literals."""
from rdflib import Literal, Variable
from rdflib.namespace import RDF, XSD
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue


def typed_projection_evidence(sparql: str) -> list[dict]:
    """Describe direct projections from mandatory typed carriers.

    Evidence augments semantic validation; it is not a blanket validation pass.
    OPTIONAL, UNION and negative patterns cannot prove a mandatory carrier.
    Projection boundaries are kept separate to avoid leaking subquery bindings.
    """
    try:
        algebra = translateQuery(parseQuery(sparql)).algebra
    except Exception:
        return []

    def mandatory(value):
        if not isinstance(value, CompValue):
            return []
        if value.name == 'BGP':
            return list(value.get('triples', []))
        if value.name == 'Join':
            return mandatory(value.get('p1')) + mandatory(value.get('p2'))
        if value.name == 'LeftJoin':
            return mandatory(value.get('p1'))
        if value.name in {'Filter', 'Extend', 'OrderBy', 'Distinct', 'Reduced', 'Slice'}:
            return mandatory(value.get('p'))
        return []

    def projects(value):
        if isinstance(value, CompValue):
            if value.name == 'Project':
                yield value
                return  # Do not present inner-query bindings as outer evidence.
            for child in value.values():
                yield from projects(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from projects(child)

    result = []
    for project in projects(algebra):
        triples = mandatory(project.get('p'))
        typed = {}
        for subject, predicate, obj in triples:
            if predicate == RDF.type:
                typed.setdefault(subject, []).append(str(obj))
        projected = set(project.get('PV', []))
        for subject, predicate, obj in triples:
            if predicate != RDF.type and isinstance(obj, Variable) and obj in projected and subject in typed:
                result.append({'projected_variable': str(obj), 'carrier': str(subject),
                               'carrier_classes': sorted(typed[subject]), 'predicate': str(predicate)})
    return result


def date_comparison_errors(sparql: str, schema: dict) -> list[str]:
    """Reject provable date/string mismatches, leaving casts and ambiguity alone.

    Variable bindings are collected within the Filter's graph scope; projection
    boundaries are not crossed. Unknown datatypes are not inferred from names.
    """
    property_types = {}
    for details in schema.values():
        for column in details.get('columns', []):
            if not isinstance(column, dict) or not column.get('uri'):
                continue
            types = details.get('literal_datatypes', {}).get(column.get('name'), [])
            property_types.setdefault(column['uri'], set()).update(types)
    try:
        algebra = translateQuery(parseQuery(sparql)).algebra
    except Exception:
        return []  # Syntax checks remain the existing validator's responsibility.
    def walk(value):
        if isinstance(value, CompValue):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from walk(child)
    def bindings(value, result):
        if not isinstance(value, CompValue) or value.name in {'Project', 'ToMultiSet'}:
            return
        if value.name == 'BGP':
            for _, predicate, obj in value.get('triples', []):
                if isinstance(obj, Variable):
                    result.setdefault(obj, set()).update(property_types.get(str(predicate), {'unknown'}))
        for child in value.values():
            if isinstance(child, CompValue):
                bindings(child, result)
    errors = []
    dates = {str(XSD.date), str(XSD.dateTime)}
    for node in walk(algebra):
        if node.name != 'Filter':
            continue
        variables = {}
        bindings(node.get('p'), variables)
        for expr in walk(node.get('expr')):
            if expr.name != 'RelationalExpression':
                continue
            left, right = expr.get('expr'), expr.get('other')
            for variable, literal in ((left, right), (right, left)):
                observed = variables.get(variable, set()) if isinstance(variable, Variable) else set()
                if len(observed) == 1 and observed <= dates and isinstance(literal, Literal):
                    expected = next(iter(observed))
                    if str(literal.datatype or '') != expected:
                        errors.append(f'Direct comparison of ?{variable} requires a literal typed <{expected}> '
                                      'or an explicit compatible cast; an untyped or differently typed literal is invalid.')
    return list(dict.fromkeys(errors))
