import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from rdflib import Graph

from script_diff_llm.backends.sql import _deterministic_projection_sql, _deterministic_single_source_aggregate_sql, semantic_generate_sql
from script_diff_llm.pipeline.dag.planner import build_subquery_dag
from script_diff_llm.pipeline.dag.executor import AOPExecutor
from script_diff_llm.pipeline.domain_context import validate_entries, relevant_domain_entries, save_domain_context_state, context_schema_evidence
from script_diff_llm.pipeline.specification import semantic_build_query_spec
from script_diff_llm.pipeline.semantic_contract import validate_semantic_result
from tests.unit.test_portable_contracts import SCHEMA, QUESTION, spec
from tests.unit.test_domain_context import client_for, entry


class ReliabilityV6Test(unittest.TestCase):
    def test_intermediate_count_validates_local_scope_not_root_entity_list(self):
        plan={'query_type':'aggregation','entity_key':'customer','output_schema':['n'],
              'measures':[{'field':'id','output_name':'n','final_operation':'COUNT'}]}
        executor=AOPExecutor({'Query_Spec':lambda _: {'query_spec':plan}},Graph())
        generate={'sql':'SELECT COUNT(id) AS n FROM charges'}
        scan={'status':'success','data':[{'n':2}],'row_count':1}
        with patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_generate_sql',return_value=generate) as model_generate, \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_pre_scan_validate_sql',return_value={'pre_scan_validation':{'is_valid':True}}), \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.pre_programmed_scan_sql',return_value=scan):
            result=executor._run_sql_subquery('A','Count charges','List customers and their charges',{}, {})
        self.assertEqual(result['status'],'success')
        self.assertTrue(result['trace']['validation_is_valid'])
        self.assertEqual(model_generate.call_count,1)

    def test_one_level_aggregate_preserves_null_groups_and_record_weighting(self):
        schema={'charges':{'column_names':['customer','region','amount']}}
        plan={'query_type':'aggregation','base_entity':'charges','required_classes':['charges'],
              'group_by':[{'source_class':'charges','field':'region','output_name':'region'}],
              'measures':[{'source_class':'charges','field':'amount','output_name':'mean','final_operation':'AVG'},
                          {'source_class':'charges','field':'customer','output_name':'customers','final_operation':'COUNT','requires_distinct':True}],
              'output_schema':['region','mean','customers']}
        sql=_deterministic_single_source_aggregate_sql({'query_spec':plan,'sql_schema':schema})
        c=sqlite3.connect(':memory:');c.execute('CREATE TABLE charges(customer TEXT,region TEXT,amount REAL)')
        c.executemany('INSERT INTO charges VALUES(?,?,?)',[('a',None,5),('b','west',10),('b','west',20),('c','west',90)])
        self.assertEqual(c.execute(sql).fetchall(),[(None,5.0,1),('west',40.0,2)])
        c.close()
        plan['grain']={'pre_aggregate_by':['customer']}
        self.assertIsNone(_deterministic_single_source_aggregate_sql({'query_spec':plan,'sql_schema':schema}))

    def test_physical_identity_alias_is_valid_but_aggregate_is_not_identity(self):
        plan={'query_type':'point_lookup','entity_key':'id','output_schema':['selected_ids'],
              'measures':[{'field':'id','output_name':'selected_ids'}], 'filters':[], 'group_by':[]}
        self.assertTrue(validate_semantic_result('List customers',plan,[{'selected_ids':'C1'}])['is_valid'])
        self.assertFalse(validate_semantic_result('List customers',plan,[{'selected_ids':'C1'},{'selected_ids':'C1'}])['is_valid'])
        plan['measures'][0]['final_operation']='COUNT'
        self.assertFalse(validate_semantic_result('List customers',plan,[{'selected_ids':2}])['is_valid'])

    def test_sql_verb_single_node_executes_original_scope_without_fake_bindings(self):
        node={'id':'N1','operator':'JOIN','backend':'SQL','description':'partial rewrite',
              'outputs':[{'name':'arbitrary_ids','type':'int[]'}],'inputs':[]}
        dag=build_subquery_dag('List customers with overdue invoices', [node])
        self.assertEqual(dag.nodes['N1']['operator'],'Subquery')
        self.assertEqual(dag.nodes['N1']['description'],'List customers with overdue invoices')
        self.assertEqual(dag.nodes['N1']['outputs'],[])
        self.assertEqual(node['operator'],'JOIN')

    def test_invalid_binding_or_operator_falls_back_to_full_question(self):
        for source,operator in [('A.code, A.label','Subquery'),('A.placeholder','Subquery'),('A.code','Aggregate')]:
            nodes=[{'id':'A','operator':'Subquery','backend':'SQL','outputs':[{'name':'code'}]},
                   {'id':'B','operator':operator,'backend':'SQL','inputs':[{'name':'codes','source':source}]}]
            dag=build_subquery_dag('Count customers with overdue invoices',nodes)
            self.assertEqual(list(dag),['Q1'])
            self.assertEqual(dag.nodes['Q1']['backend'],'SQL')

    def test_valid_multinode_bindings_remain_dynamic(self):
        dag=build_subquery_dag('List matching customers',[
            {'id':'A','operator':'Subquery','backend':'SQL','outputs':[{'name':'code'}]},
            {'id':'B','operator':'Subquery','backend':'KG','inputs':[{'name':'codes','source':'A.code'}],
             'outputs':[{'name':'unused'}]}])
        self.assertEqual(list(dag.edges),[('A','B')])
        self.assertEqual(dag.nodes['A']['outputs'],[{'name':'code'}])
        self.assertEqual(dag.nodes['B']['outputs'],[])

    def test_single_source_compiler_executes_literal_predicates_without_model(self):
        schema={'invoices':{'column_names':['id','label','amount']}}
        plan={'query_type':'point_lookup','base_entity':'invoices','required_classes':['invoices'],
              'filters':[{'source_class':'invoices','field':'label','operator':'=','value':"O'Brien"}],
              'measures':[{'source_class':'invoices','field':'amount','output_name':'charge'}],
              'output_schema':['id','charge']}
        inputs={'query_spec':plan,'sql_schema':schema}
        client=Mock()
        result=semantic_generate_sql(inputs,client,'offline')
        client.chat.completions.create.assert_not_called()
        c=sqlite3.connect(':memory:')
        c.execute('CREATE TABLE invoices(id TEXT,label TEXT,amount REAL)')
        c.executemany('INSERT INTO invoices VALUES(?,?,?)',[('x',"O'Brien",12.5),('y','Other',99)])
        self.assertEqual(c.execute(result['sql']).fetchall(),[('x',12.5)])
        c.close()
        for change in [{'bound_inputs':{'ids':['x']}},{'query_spec':{**plan,'group_by':[{'field':'label'}]}},
                       {'query_spec':{**plan,'required_classes':['invoices','another_table']}},
                       {'query_spec':{**plan,'predicate_tree':{'op':'OR'}}}]:
            self.assertIsNone(_deterministic_projection_sql({**inputs,**change}))

    def test_context_terms_normalization_preserves_policy_gate(self):
        candidate=entry();candidate['terms']='charge, charges'
        docs={'domain_intro':{'text':candidate['quote'],'evaluation_scoped':False}}
        reviewed=validate_entries([candidate],docs,{'sql':SCHEMA,'kg':{}})[0]
        self.assertEqual(reviewed['terms'],['charge','charges'])
        self.assertEqual(reviewed['kind'],'definition')
        self.assertEqual(reviewed['errors'],[])
        self.assertEqual(relevant_domain_entries({'entries':[reviewed]},'average charges','sql',SCHEMA),[reviewed])

    def test_observed_domains_are_in_cache_identity_without_record_samples(self):
        schemas={'sql':{'records':{'column_names':['id','kind'],'primary_keys':['id'],
            'sample_rows':[{'id':'private-record'}],
            'columns':[{'name':'kind','allowed_values':['B','A'],'allowed_values_complete':True}]}}}
        evidence=context_schema_evidence(schemas)
        self.assertEqual(evidence['sql']['records']['observed_text_domains'],{'kind':['A','B']})
        self.assertNotIn('private-record',json.dumps(evidence))
        changed=copy.deepcopy(schemas)
        changed['sql']['records']['columns'][0]['allowed_values']=['C']
        self.assertNotEqual(evidence,context_schema_evidence(changed))

    def test_null_predicates_and_entity_identity_projection(self):
        schema={'records':{'column_names':['id','kind']}}
        plan={'query_type':'point_lookup','base_entity':'records','entity_key':'id',
              'filters':[{'field':'kind','operator':'=','value':None}],
              'output_schema':['id'],'measures':[]}
        sql=_deterministic_projection_sql({'query_spec':plan,'sql_schema':schema})
        self.assertIn('IS NULL',sql)
        self.assertIn('SELECT DISTINCT',sql)
        c=sqlite3.connect(':memory:');c.execute('CREATE TABLE records(id TEXT,kind TEXT)')
        c.executemany('INSERT INTO records VALUES(?,?)',[('x',None),('x',None),('y','A')])
        self.assertEqual(c.execute(sql).fetchall(),[('x',)])
        c.close()
        plan['filters'][0].update(operator='not_in',value=[None])
        self.assertIsNone(_deterministic_projection_sql({'query_spec':plan,'sql_schema':schema}))

    def test_context_missing_retrieval_source_is_grounded_and_visible(self):
        candidate=entry();candidate.update(active=True,errors=[],evidence_hash='reviewed')
        schema={**SCHEMA,'other':{'column_names':['id']}}
        client=client_for(spec())
        result=semantic_build_query_spec({'query':QUESTION,'root_query':QUESTION,'schema_kind':'sql',
            'global_schema':schema,'schema_details':{'other':schema['other']},'retrieved_tables':['other'],
            'domain_context':{'fingerprint':'snapshot','entries':[candidate]}},client,'offline',
            parse_json_fn=lambda raw,*_:json.loads(raw),normalize_for_compare_fn=str.lower,log_call_fn=lambda *_:None)
        self.assertTrue(result['query_spec']['domain_context_trace']['available_rules'])
        self.assertIn('charges',client.chat.completions.create.call_args.kwargs['messages'][0]['content'])
        with tempfile.TemporaryDirectory() as directory:
            save_domain_context_state(directory,None,'offline')
            self.assertFalse(json.loads(Path(directory,'domain_context_state.json').read_text())['active'])


if __name__=='__main__':unittest.main()
