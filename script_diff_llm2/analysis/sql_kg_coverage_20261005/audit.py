"""Read-only SQL/RDF representation audit. No benchmark answers or model calls."""
import argparse
import csv
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import unquote
import urllib.request

import rdflib

ROOT = Path(__file__).resolve().parents[2]
WM = rdflib.Namespace('https://wealth.example.org/ontology/')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def equivalent(sql_value, rdf_value):
    if isinstance(sql_value, (int, float)):
        try:
            left, right = Decimal(str(sql_value)), Decimal(str(rdf_value))
            return left == right
        except InvalidOperation:
            return False
    return str(sql_value) == str(rdf_value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, default=ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db')
    parser.add_argument('--kg', type=Path, default=ROOT / 'data/kg/wealth_management_diverse_kg.ttl')
    parser.add_argument('--schema', type=Path, default=ROOT / 'data/kg/wealth_management_diverse_schema.ttl')
    parser.add_argument('--export-summary', type=Path, default=ROOT / 'data/kg/wealth_management_diverse_kg_summary.json')
    parser.add_argument('--alias-map', type=Path, default=ROOT / 'data/kg/rdf_id_alias_map.json')
    parser.add_argument('--fuseki-endpoint', default='http://127.0.0.1:3030/wealth/query')
    args = parser.parse_args()
    export = json.loads(args.export_summary.read_text())
    schema = rdflib.Graph().parse(args.schema)
    print('Parsing local RDF export...', flush=True)
    graph = rdflib.Graph().parse(args.kg)
    print(f'Parsed {len(graph):,} triples; comparing physical rows and cells...', flush=True)
    properties = defaultdict(list)
    # sourceColumn provenance is in the merged export as well as any supplied
    # schema. Do not silently skip a class when schema-only annotations lack it.
    for source_graph in (schema, graph):
        for subject, _, column in source_graph.triples((None, WM.sourceColumn, None)):
            if subject not in properties[str(column)]:
                properties[str(column)].append(subject)
    subjects_by_table = defaultdict(set)
    for subject, _, table in graph.triples((None, WM.sourceTable, None)):
        subjects_by_table[str(table)].add(subject)
    connection = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    result = {'inputs': {name: {'path': str(path.resolve()), 'sha256': digest(path)}
                         for name, path in [('database', args.database), ('kg', args.kg), ('schema', args.schema), ('export_summary', args.export_summary), ('alias_map', args.alias_map)]},
              'graph_triples': len(graph), 'export_reported_triples': export.get('merged_triples'),
              'export_original_database_path': export['data'].get('db_path'),
              'tables': [], 'live_fuseki': {}, 'method': 'Complete keyed row and cell comparison; exact text and Decimal(str(value)) numeric comparison. NULL is expected to be absent in RDF. Mappings use export provenance and sourceColumn annotations.'}
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    investor_lookup = {}
    alias_map = json.loads(args.alias_map.read_text())
    resolved_alias_ids = {str(entry['resolved_id']) for entry in alias_map.values()
                          if isinstance(entry, dict) and entry.get('resolved_id') and not entry.get('ambiguous')}
    result['alias_map'] = {'normalized_keys': len(alias_map),
                           'ambiguous_entries': sum(bool(entry.get('ambiguous')) for entry in alias_map.values() if isinstance(entry, dict)),
                           'distinct_resolved_ids': len(resolved_alias_ids)}
    inverse_edges = {entry['to']: WM[entry['edge']] for entry in export['data'].get('inferred_edges', [])
                     if entry.get('from') == 'Investor' and entry.get('via') == 'investor_id'}
    for subject in graph.subjects(rdflib.RDF.type, WM.Investor):
        for key in graph.objects(subject, WM.investorId):
            investor_lookup[str(key)] = subject
    for table in tables:
        meta = export['data']['tables'].get(table)
        if not meta:
            result['tables'].append({'table': table, 'mapping_missing': True})
            continue
        primary_key = meta['pk']
        quoted = '"' + table.replace('"', '""') + '"'
        rows = [dict(row) for row in connection.execute('SELECT * FROM ' + quoted)]
        info = connection.execute('PRAGMA table_info(' + quoted + ')').fetchall()
        indexed = defaultdict(list)
        missing_rdf_key = []
        for subject in subjects_by_table[table]:
            values = [value for predicate in properties[primary_key] for value in graph.objects(subject, predicate)]
            if len(values) != 1:
                missing_rdf_key.append(str(subject))
            for value in values:
                indexed[str(value)].append(subject)
        sql_keys = Counter(str(row[primary_key]) for row in rows)
        table_result = {'table': table, 'class': meta['class'], 'key_column': primary_key,
                        'sql_rows': len(rows), 'rdf_source_subjects': len(subjects_by_table[table]),
                        'rdf_class_subjects': len(set(graph.subjects(rdflib.RDF.type, WM[meta['class']]))),
                        'sql_declared_primary_keys': [row['name'] for row in info if row['pk']],
                        'sql_declared_foreign_keys': len(connection.execute('PRAGMA foreign_key_list(' + quoted + ')').fetchall()),
                        'sql_null_keys': sum(row[primary_key] is None for row in rows),
                        'sql_duplicate_keys': {key: count for key, count in sql_keys.items() if count > 1},
                        'rdf_duplicate_keys': {key: len(value) for key, value in indexed.items() if len(value) > 1},
                        'rdf_missing_or_multivalued_key': missing_rdf_key[:20],
                        'missing_sql_keys_in_rdf': sorted(set(sql_keys) - set(indexed)),
                        'extra_rdf_keys': sorted(set(indexed) - set(sql_keys)),
                        'uri_namespaces': Counter(), 'uri_suffix_equals_sql_key': 0,
                        'missing_class_type': 0, 'fields': [], 'row_link_predicates': Counter(),
                        'investor_reference_checked_rows': 0, 'investor_reference_missing_or_wrong_rows': 0,
                        'inverse_investor_edge': str(inverse_edges.get(meta['class'], '')),
                        'inverse_investor_edge_missing_rows': 0,
                        'sql_keys_with_resolved_alias_entry': sum(key in resolved_alias_ids for key in sql_keys),
                        'examples': []}
        field_stats = {}
        for item in info:
            column = item['name']
            field_stats[column] = {'column': column, 'sql_type': item['type'],
                                   'rdf_predicates': [str(p) for p in properties[column]],
                                   'nonnull_cells': 0, 'null_cells': 0, 'matched_cells': 0,
                                   'missing_values': 0, 'unequal_values': 0,
                                   'unexpected_values_for_null': 0, 'multivalued_cells': 0,
                                   'rdf_datatypes': Counter()}
        for row in rows:
            key = str(row[primary_key])
            candidates = indexed.get(key, [])
            if len(candidates) != 1:
                continue
            subject = candidates[0]
            uri = str(subject)
            namespace, suffix = uri.rsplit('/', 1)
            table_result['uri_namespaces'][namespace + '/'] += 1
            table_result['uri_suffix_equals_sql_key'] += int(unquote(suffix) == key)
            table_result['missing_class_type'] += int((subject, rdflib.RDF.type, WM[meta['class']]) not in graph)
            for column, stats in field_stats.items():
                value = row[column]
                values = [obj for predicate in properties[column] for obj in graph.objects(subject, predicate)]
                stats['multivalued_cells'] += int(len(values) > 1)
                stats['rdf_datatypes'].update(str(obj.datatype or 'plain') for obj in values if isinstance(obj, rdflib.Literal))
                if value is None:
                    stats['null_cells'] += 1
                    stats['unexpected_values_for_null'] += int(bool(values))
                else:
                    stats['nonnull_cells'] += 1
                    if len(values) == 1 and equivalent(value, values[0]):
                        stats['matched_cells'] += 1
                    else:
                        stats['missing_values' if not values else 'unequal_values'] += 1
                        if len(table_result['examples']) < 20:
                            table_result['examples'].append({'key': key, 'column': column, 'sql': value, 'rdf': [str(v) for v in values]})
            if 'investor_id' in row and table != 'ATOM_ENTITY_INVESTOR_PROFILE_001':
                table_result['investor_reference_checked_rows'] += 1
                target = investor_lookup.get(str(row['investor_id']))
                links = [predicate for predicate, obj in graph.predicate_objects(subject)
                         if isinstance(obj, rdflib.URIRef) and (obj, rdflib.RDF.type, WM.Investor) in graph]
                table_result['row_link_predicates'].update(str(p) for p in links)
                actual = [obj for predicate, obj in graph.predicate_objects(subject)
                          if isinstance(obj, rdflib.URIRef) and (obj, rdflib.RDF.type, WM.Investor) in graph]
                if target is None or not actual or any(obj != target for obj in actual):
                    table_result['investor_reference_missing_or_wrong_rows'] += 1
                inverse = inverse_edges.get(meta['class'])
                if inverse and (target, inverse, subject) not in graph:
                    table_result['inverse_investor_edge_missing_rows'] += 1
        table_result['fields'] = list(field_stats.values())
        table_result['fully_checked_sql_rows'] = sum(
            len(indexed.get(str(row[primary_key]), [])) == 1 for row in rows)
        result['tables'].append(table_result)
        print(f"{table}: SQL={len(rows)}, RDF={len(subjects_by_table[table])}, unequal={sum(f['unequal_values'] for f in field_stats.values())}, missing={sum(f['missing_values'] for f in field_stats.values())}", flush=True)
    connection.close()
    result['audit_complete'] = all(
        not table.get('mapping_missing') and table['fully_checked_sql_rows'] == table['sql_rows']
        and all(field['rdf_predicates'] for field in table['fields'])
        for table in result['tables'])
    counts = Counter(str(cls) for _, _, cls in graph.triples((None, rdflib.RDF.type, None)))
    result['rdf_type_counts'] = dict(counts)
    result['extra_instance_classes'] = {cls: count for cls, count in counts.items()
                                       if cls.startswith(str(WM)) and cls not in {str(WM[t['class']]) for t in result['tables'] if 'class' in t}}
    # Read-only aggregate verification; no changes to the active Fuseki dataset.
    try:
        query = 'SELECT ?class (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?class } GROUP BY ?class'
        request = urllib.request.Request(args.fuseki_endpoint, data=query.encode(),
                                         headers={'Content-Type': 'application/sparql-query', 'Accept': 'application/sparql-results+json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        live = {row['class']['value']: int(row['n']['value']) for row in payload['results']['bindings']}
        result['live_fuseki'] = {'endpoint': args.fuseki_endpoint, 'class_counts': live,
                                 'all_class_counts_equal_local_export': live == dict(counts),
                                 'qualification': 'Class-count equality is not a full live-data equality proof. Cell audit uses the local TTL export.'}
    except Exception as error:
        result['live_fuseki'] = {'endpoint': args.fuseki_endpoint, 'error': str(error)}
    output = Path(__file__).with_name('coverage.json')
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    with output.with_name('field_mapping.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['sql_table', 'sql_column', 'sql_type', 'rdf_class',
            'rdf_predicates', 'rdf_datatypes', 'nonnull_values_verified', 'nulls_verified_absent'])
        writer.writeheader()
        for table in result['tables']:
            for field in table.get('fields', []):
                writer.writerow({'sql_table': table['table'], 'sql_column': field['column'],
                    'sql_type': field['sql_type'], 'rdf_class': table['class'],
                    'rdf_predicates': ' | '.join(field['rdf_predicates']),
                    'rdf_datatypes': ' | '.join(field['rdf_datatypes']),
                    'nonnull_values_verified': field['matched_cells'],
                    'nulls_verified_absent': field['null_cells'] - field['unexpected_values_for_null']})
    with output.with_name('identity_mapping.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['sql_table', 'sql_key', 'rdf_class',
            'rdf_key_predicate', 'rdf_namespace', 'records_verified', 'alias_map_covered_records',
            'investor_link_predicate', 'inverse_investor_link_predicate', 'investor_links_verified'])
        writer.writeheader()
        for table in result['tables']:
            if table.get('mapping_missing'):
                continue
            key_field = next(field for field in table['fields'] if field['column'] == table['key_column'])
            writer.writerow({'sql_table': table['table'], 'sql_key': table['key_column'],
                'rdf_class': table['class'], 'rdf_key_predicate': ' | '.join(key_field['rdf_predicates']),
                'rdf_namespace': ' | '.join(table['uri_namespaces']),
                'records_verified': table['fully_checked_sql_rows'],
                'alias_map_covered_records': table['sql_keys_with_resolved_alias_entry'],
                'investor_link_predicate': ' | '.join(table['row_link_predicates']),
                'inverse_investor_link_predicate': table['inverse_investor_edge'],
                'investor_links_verified': table['investor_reference_checked_rows'] - table['investor_reference_missing_or_wrong_rows']})
    print('Saved', output, flush=True)


if __name__ == '__main__':
    main()
