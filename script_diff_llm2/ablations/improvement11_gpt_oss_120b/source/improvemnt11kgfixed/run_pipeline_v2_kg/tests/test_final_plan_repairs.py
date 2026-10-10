import json
import unittest

from support import load, FakeClient, registry


def contract(**updates):
    value = {'bindings': [], 'metrics': [], 'filters': [], 'group_by': [],
             'required_projection': ['id'], 'order_by': [], 'limit': None,
             'population': 'all', 'null_policy': 'unspecified', 'ambiguities': []}
    value.update(updates)
    return value


def metric(output, table, field, outer='none', inner='none', keys=()):
    return {'output': output, 'definition': 'Declared calculation',
            'operands': [{'table': table, 'column': field}], 'inner_aggregation': inner,
            'outer_aggregation': outer, 'entity_keys': list(keys), 'units': 'unspecified', 'rule_ids': []}


class FinalPlanRepairs(unittest.TestCase):
    def build(self, plan, fields, value, schema=None, branches=None, **extra):
        branches = branches or [{'id': 'raw', 'fields': fields, 'retrieval_specs': [{'class': 'Items'}]}]
        client = FakeClient(plan)
        result = load('llm_operators.final_spec').semantic_build_final_spec(
            {'query': 'Return declared results', 'processed_datasets': branches, 'global_schema': schema or {},
             'answer_requirements': {'query_understanding': value}, **extra}, client)['final_spec']
        return result, client

    def execute(self, spec, rows, fields):
        data, log = load('execution').execute_spec(spec, {'raw': rows}, registry(), dataset_schemas={'raw': fields})
        self.assertEqual(load('execution').execution_errors(log), [])
        return data

    def test_sql_projection_alias_executes_exact_copy_with_nulls_and_empty_input(self):
        spec, _ = self.build({'projection': ['label AS name']}, ['label'], contract(required_projection=['name']))
        self.assertEqual(spec['contract_errors'], [])
        self.assertEqual(self.execute(spec, [{'label': None}, {'label': 'x'}], ['label']), [{'name': None}, {'name': 'x'}])
        self.assertEqual(self.execute(spec, [], ['label']), [])

    def test_distinct_raw_metric_gets_only_documented_alias(self):
        schema = {'Items': {'columns': [{'name': 'itemId', 'ontology_attribute': 'item_id', 'predicate_iri': 'urn:item-id'}]}}
        plan = {'final_steps': [{'operator': 'Distinct', 'distinct_on': ['itemId']}], 'projection': ['itemId']}
        value = contract(required_projection=['item_id'], metrics=[metric('item_id', 'Items', 'itemId', 'distinct')])
        spec, _ = self.build(plan, ['itemId'], value, schema)
        self.assertEqual(spec['contract_errors'], [])
        self.assertEqual(self.execute(spec, [{'itemId': 'a'}, {'itemId': 'a'}], ['itemId']), [{'item_id': 'a'}])
        value['metrics'][0]['inner_aggregation'] = 'avg'
        invalid, _ = self.build(plan, ['itemId'], value, schema)
        self.assertTrue(invalid['contract_errors'])

    def test_required_raw_output_is_retained_before_projection(self):
        plan = {'final_steps': [{'operator': 'Distinct', 'distinct_on': ['id', 'name']}], 'projection': ['name']}
        value = contract(required_projection=['id', 'name'])
        spec, _ = self.build(plan, ['id', 'name'], value)
        self.assertEqual(spec['contract_errors'], [])
        self.assertEqual(self.execute(spec, [{'id': 1, 'name': 'same'}, {'id': 2, 'name': 'same'}], ['id', 'name']),
                         [{'name': 'same', 'id': 1}, {'name': 'same', 'id': 2}])

    def test_count_contract_preserves_null_and_duplicate_semantics(self):
        fields = ['id', 'kind']
        rows = [{'id': 1, 'kind': 'a'}, {'id': 1, 'kind': 'a'}, {'id': None, 'kind': 'a'}]
        for expected, count in [('count', 2), ('count_distinct', 1), ('count_rows', 3)]:
            value = contract(required_projection=['n'], group_by=[{'table': 'Items', 'column': 'kind'}],
                             metrics=[metric('n', 'Items', 'id', expected)])
            wrong = 'count_rows' if expected != 'count_rows' else 'count_distinct'
            plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'group_by': ['kind'],
                    'aggregations': [{'operation': wrong, 'input_column': '*', 'output_column': 'n'}]}], 'projection': ['n']}
            # count_distinct(*) is malformed; provide its real operand.
            if wrong == 'count_distinct':
                plan['final_steps'][0]['aggregations'][0]['input_column'] = 'id'
            spec, _ = self.build(plan, fields, value)
            self.assertEqual(spec['contract_errors'], [])
            self.assertEqual(self.execute(spec, rows, fields), [{'n': count}])

    def test_sort_copy_aliases_preserve_direction_ties_and_null_order(self):
        fields = ['id', 'value']
        value = contract(required_projection=['answer'], order_by=[{'column': 'answer', 'direction': 'DESC'}], limit=2)
        plan = {'final_steps': [{'operator': 'Order_By', 'order_by': [{'column': 'value', 'direction': 'DESC'}], 'limit': 2},
                               {'operator': 'Math_Compute', 'expression': "column('value')", 'output_column': 'answer'}], 'projection': ['answer']}
        spec, _ = self.build(plan, fields, value)
        self.assertEqual(spec['contract_errors'], [])
        plan['final_steps'][0]['order_by'][0]['direction'] = 'ASC'
        self.assertTrue(self.build(plan, fields, value)[0]['contract_errors'])
        plan['final_steps'][0]['order_by'][0] = {'column': 'value', 'direction': 'DESC', 'nulls': 'first'}
        self.assertTrue(self.build(plan, fields, value)[0]['contract_errors'])
        plan['final_steps'][1]['expression'] = '-value'
        self.assertTrue(self.build(plan, fields, value)[0]['contract_errors'])

    def test_overwriting_sorted_value_is_not_a_copy_alias(self):
        value = contract(required_projection=['value'], order_by=[{'column': 'value', 'direction': 'DESC'}])
        plan = {'final_steps': [
            {'operator': 'Order_By', 'order_by': [{'column': 'value', 'direction': 'DESC'}]},
            {'operator': 'Math_Compute', 'expression': '-value', 'output_column': 'value'}], 'projection': ['value']}
        self.assertTrue(self.build(plan, ['value'], value)[0]['contract_errors'])

    def test_group_copy_alias_is_equivalent_but_changed_grain_is_rejected(self):
        fields = ['kind', 'amount']
        value = contract(required_projection=['total'], group_by=[{'table': 'Items', 'column': 'kind'}],
                         metrics=[metric('total', 'Items', 'amount', 'sum')])
        plan = {'final_steps': [{'operator': 'Math_Compute', 'expression': "column('kind')", 'output_column': 'category'},
              {'operator': 'Filter_Aggregate', 'group_by': ['category'], 'operation': 'sum', 'input_column': 'amount', 'output_column': 'total'}], 'projection': ['total']}
        self.assertEqual(self.build(plan, fields, value)[0]['contract_errors'], [])
        plan['final_steps'][1]['group_by'] = ['amount']
        self.assertTrue(self.build(plan, fields, value)[0]['contract_errors'])

    def test_string_join_keys_follow_declared_inner_equality(self):
        branches = [{'id': 'facts', 'fields': ['fk', 'amount'], 'retrieval_specs': [{'class': 'Facts'}]},
                    {'id': 'owners', 'fields': ['id'], 'retrieval_specs': [{'class': 'Owners'}]}]
        value = contract(required_projection=['total'], group_by=[{'table': 'Owners', 'column': 'id'}],
                         metrics=[metric('total', 'Facts', 'amount', 'sum')])
        plan = {'final_steps': [
            {'operator': 'Integrate', 'inputs': ['facts', 'owners'], 'left_on': 'fk', 'right_on': 'id', 'join_type': 'inner'},
            {'operator': 'Filter_Aggregate', 'group_by': 'fk', 'operation': 'sum', 'input_column': 'amount', 'output_column': 'total'}],
            'projection': ['total']}
        self.assertEqual(self.build(plan, [], value, branches=branches)[0]['contract_errors'], [])
        plan['final_steps'][0]['join_type'] = 'left'
        self.assertTrue(self.build(plan, [], value, branches=branches)[0]['contract_errors'])

    def test_derived_group_uses_declared_metric_and_retains_raw_operand(self):
        value = contract(required_projection=['band', 'n'], group_by=[{'table': 'Items', 'column': 'value'}],
                         metrics=[metric('band', 'Items', 'value')])
        repaired = load('query_understanding')._repair_model_interpretation(value, 'Group by band', {}, {'rules': []})
        self.assertEqual(repaired['group_by'], [{'table': 'Items', 'column': 'band'}])
        self.assertIn(('Items', 'value'), load('query_understanding').required_fields(repaired))
        self.assertEqual(value['group_by'][0]['column'], 'value')

    def test_final_derived_group_wins_over_raw_metric_operand_keys(self):
        value = contract(required_projection=['mean'], group_by=[{'table': 'Items', 'column': 'band'}], metrics=[
            metric('band', 'Items', 'value'),
            metric('mean', 'Items', 'amount', inner='avg', keys=[{'table': 'Items', 'column': 'value'}])])
        plan = {'final_steps': [
            {'operator': 'Math_Compute', 'expression': "where(value < 10, 'low', 'high')", 'output_column': 'band'},
            {'operator': 'Filter_Aggregate', 'group_by': ['band'], 'operation': 'avg', 'input_column': 'amount', 'output_column': 'mean'}],
            'projection': ['band', 'mean']}
        self.assertEqual(self.build(plan, ['value', 'amount'], value)[0]['contract_errors'], [])
        plan['final_steps'][1]['group_by'] = ['value']
        self.assertTrue(self.build(plan, ['value', 'amount'], value)[0]['contract_errors'])

    def test_conditional_sum_and_wrong_average_are_not_silently_rewritten(self):
        value = contract(required_projection=['n'], metrics=[metric('n', 'Items', 'value', 'count')])
        plan = {'final_steps': [{'operator': 'Math_Compute', 'expression': 'where(value < 0, 1, 0)', 'output_column': 'flag'},
              {'operator': 'Filter_Aggregate', 'operation': 'sum', 'input_column': 'flag', 'output_column': 'n'}], 'projection': ['n']}
        spec, client = self.build(plan, ['value'], value, previous_final_spec=plan)
        self.assertTrue(any('outer aggregation count' in e for e in spec['contract_errors']))
        self.assertIn('Metric n must preserve outer aggregation count', client.calls[0]['messages'][0]['content'])
        self.assertEqual(spec['final_steps'][1]['operation'], 'sum')

    def test_repeated_metric_name_checks_final_aggregate_not_inner_summary(self):
        value = contract(required_projection=['total'], group_by=[{'table': 'Items', 'column': 'kind'}],
                         metrics=[metric('total', 'Items', 'amount', 'sum')])
        plan = {'final_steps': [
            {'operator': 'Filter_Aggregate', 'group_by': ['id', 'kind'], 'operation': 'sum', 'input_column': 'amount', 'output_column': 'total'},
            {'operator': 'Math_Compute', 'expression': "column('kind')", 'output_column': 'category'},
            {'operator': 'Filter_Aggregate', 'group_by': ['category'], 'operation': 'sum', 'input_column': 'total', 'output_column': 'total'}], 'projection': ['total']}
        spec, _ = self.build(plan, ['id', 'kind', 'amount'], value)
        self.assertEqual(spec['contract_errors'], [])

    def test_local_class_spelling_normalization_is_unique_and_namespace_safe(self):
        resolve = load('rdf_contracts').class_key
        schema = {'CashFlow': {'class_iri': 'urn:our:CashFlow'}}
        self.assertEqual(resolve('Cash Flow', schema), 'CashFlow')
        self.assertEqual(resolve('cash_flow', schema), 'CashFlow')
        self.assertEqual(resolve('urn:foreign:CashFlow', schema), 'urn:foreign:CashFlow')
        self.assertEqual(resolve('Cash-Flow', {**schema, 'Cash_Flow': {}}), 'Cash-Flow')

    def test_count_without_selected_operand_is_row_count(self):
        value = contract(metrics=[{**metric('n', 'Items', 'id', 'count'), 'operands': []}])
        repaired = load('query_understanding')._repair_model_interpretation(value, 'Count records', {}, {'rules': []})
        self.assertEqual(repaired['metrics'][0]['outer_aggregation'], 'count_rows')
        self.assertEqual(value['metrics'][0]['outer_aggregation'], 'count')

    def test_numeric_band_cannot_be_interpreted_as_raw_numeric_group(self):
        value = contract(bindings=[{'phrase': 'value band', 'table': 'Items', 'column': 'value', 'rule_ids': []}],
                         group_by=[{'table': 'Items', 'column': 'value'}])
        schema = {'Items': {'columns': [{'name': 'value', 'rdf_datatypes': ['http://www.w3.org/2001/XMLSchema#decimal']}]}}
        with self.assertRaisesRegex(ValueError, 'calculated grouping metric'):
            load('query_understanding').validate_interpretation(value, 'Group by value band', schema, {'rules': []})

    def test_categorical_comparison_requires_explicit_grouping(self):
        value = contract(required_projection=['band', 'n'], metrics=[
            {**metric('band', 'Items', 'value'), 'units': 'categorical'}, metric('n', 'Items', 'id', 'count')])
        with self.assertRaisesRegex(ValueError, 'explicit final grouping'):
            load('query_understanding').validate_interpretation(value, 'Counts per band',
                {'Items': {'columns': [{'name': 'value'}, {'name': 'id'}]}}, {'rules': []})

    def test_competing_scan_equalities_fail_early_without_turning_and_into_or(self):
        predicates = [{'id': name, 'source_class': 'Items', 'field': 'kind', 'operator': '=', 'value': name,
                       'stage': 'scan', 'branch_ids': ['q']} for name in ('a', 'b')]
        payload = {'selected_decomposition': {'subquestions': [{'id': 'q', 'source_class': 'Items'}],
                                             'answer_requirements': {'predicates': predicates}}}
        selected = load('llm_operators.decompose')._cleanup_decomposition(payload, 'Compare amounts by kind', ['Items'])['selected_decomposition']
        self.assertTrue(any('competing scan equalities' in e for e in selected['contract_errors']))
        self.assertEqual([p['value'] for p in selected['answer_requirements']['predicates']], ['a', 'b'])
        feedback = load('prompt_boundary').feedback_for_prompt({'errors': selected['contract_errors'] + ['secret-row-value']})
        self.assertIn('predicate_scope_guidance', json.loads(feedback))
        self.assertNotIn('secret-row-value', feedback)


if __name__ == '__main__':
    unittest.main()
