"""Local DuckDB binding and isolated four-worker execution without API calls."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import csv
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import duckdb
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'run_pipeline_v3_sql _'))
from _bootstrap import bootstrap
bootstrap()
from run_pipeline_v3_sql.duckdb_backend import run_sql
from run_pipeline_v3_sql.raw_sql import render_raw_sql
from run_pipeline_v3_sql.raw_query import render_raw_query
from run_pipeline_v3_sql.sql_metadata import load_yaml_metadata
from run_pipeline_v3_sql.performance import RunTiming
import run_pipeline


class ModelPresetTests(unittest.TestCase):
    def test_deepseek_uses_local_aws_credentials_and_its_own_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            credential_file = root / '.env'
            original = ('AWS_Bedrock_API_gpt_oss_120b=offline-key\nBEDROCK_REGION=us-east-1\n'
                        'BEDROCK_GPT_OSS_MODEL=openai.gpt-oss-120b-1:0\n')
            credential_file.write_text(original, encoding='utf-8')
            with patch.object(run_pipeline, 'ROOT', root), patch.dict(os.environ, {
                    'AWS_BEDROCK_API_KEY': 'stale-inherited-key',
                    'BEDROCK_BASE_URL': 'https://unrelated.invalid/v1'}):
                configured = run_pipeline.environment('deepseek-v3.1')
            self.assertEqual(configured['AWS_BEDROCK_API_KEY'], 'offline-key')
            self.assertEqual(configured['BEDROCK_GPT_OSS_MODEL'], 'deepseek.v3-v1:0')
            self.assertEqual(configured['BEDROCK_BASE_URL'],
                             'https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1')
            self.assertEqual(configured['DOMAIN_MAX_OUTPUT_TOKENS'], '8192')
            self.assertEqual(Path(configured['KNOWLEDGE_CACHE_DIR']),
                             root / '.runtime/knowledge_neowealth_deepseek_v3_1')
            self.assertEqual(credential_file.read_text(encoding='utf-8'), original)

    def test_deepseek_launch_preserves_inputs_and_four_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(run_pipeline, 'ROOT', root), \
                 patch.object(run_pipeline, 'environment', return_value={
                     'BEDROCK_GPT_OSS_MODEL': 'deepseek.v3-v1:0',
                     'KNOWLEDGE_CACHE_DIR': str(root / '.runtime/knowledge_neowealth_deepseek_v3_1')}), \
                 patch.object(run_pipeline, 'prepare_questions', return_value=757) as prepare, \
                 patch.object(run_pipeline.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as child:
                self.assertEqual(run_pipeline.main(['--workers', '4', '--model', 'deepseek-v3.1']), 0)
            prepare.assert_called_once_with(root / 'outputs/deepseek_v3_1/input_questions.jsonl')
            command = child.call_args.args[0]
            for flag, value in {'--workers': '4', '--env-file': str(root / '.env'),
                                '--db': str(root / 'newdb/neowealth.duckdb'),
                                '--yaml-dir': str(root / 'newdb/primitves_updated_final'),
                                '--domain-intro': str(root / 'newdb/01_domain_and_business_rules.md'),
                                '--business-rules': str(root / 'newdb/ALL_RULES_COMPILED/01_domain_and_business_rules.md'),
                                '--output': str(root / 'outputs/deepseek_v3_1/raw_pipeline.csv')}.items():
                self.assertEqual(command[command.index(flag) + 1], value)

    def test_existing_command_keeps_env_model_and_full_run_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / '.env').write_text('BEDROCK_GPT_OSS_MODEL=openai.gpt-oss-120b-1:0\n', encoding='utf-8')
            with patch.object(run_pipeline, 'ROOT', root):
                configured = run_pipeline.environment()
                with patch.object(run_pipeline, 'prepare_questions', return_value=757) as prepare, \
                     patch.object(run_pipeline.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                    run_pipeline.main(['--workers', '4'])
            prepare.assert_called_once_with(root / 'outputs/full_run/input_questions.jsonl')
            self.assertEqual(configured['BEDROCK_GPT_OSS_MODEL'], 'openai.gpt-oss-120b-1:0')
            self.assertEqual(Path(configured['KNOWLEDGE_CACHE_DIR']), root / '.runtime/knowledge_neowealth')


class NeoWealthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = self.root / 'test.duckdb'
        with duckdb.connect(str(self.db)) as connection:
            connection.execute('CREATE TABLE accounts(id INTEGER, name VARCHAR, amount DECIMAL(12,2), paid_at DATE)')
            connection.execute("INSERT INTO accounts VALUES (1,'Alice',12.50,'2026-01-01'),(2,NULL,NULL,NULL)")
        self.schema = {'TABLE_ACCOUNTS': {'backend': 'duckdb', 'sql_table': 'accounts',
            'columns': [{'name': name, 'datatype': kind} for name, kind in
                        [('id','numeric'),('name','categorical_string'),('amount','numeric'),('paid_at','categorical_string')]]}}

    def tearDown(self):
        self.temporary.cleanup()

    def test_document_identity_maps_to_physical_duckdb_table(self):
        query = render_raw_query({'class':'TABLE_ACCOUNTS','fields':['id','amount','paid_at'],'filters':[]},self.schema)
        self.assertIn('FROM "accounts"',query)
        result=run_sql(query,self.db)
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(result['data'][0],{'id':1,'amount':12.5,'paid_at':'2026-01-01'})
        self.assertEqual(result['data'][1],{'id':2,'amount':None,'paid_at':None})

    def test_duckdb_session_uses_documented_case_and_null_policies(self):
        result=run_sql("SELECT id FROM accounts WHERE name='alice'",self.db)
        self.assertEqual(result['data'],[{'id':1}])
        self.assertEqual(run_sql('SELECT name FROM accounts ORDER BY name DESC',self.db)['data'][0],{'name':None})

    def test_duckdb_denies_writes_multiple_statements_and_external_files(self):
        for query in ['DELETE FROM accounts','SELECT 1; SELECT 2',"SELECT * FROM read_csv('/missing.csv')","ATTACH '/missing.duckdb'"]:
            self.assertEqual(run_sql(query,self.db)['status'],'error',query)
        self.assertEqual(run_sql('SELECT count(*) AS n FROM accounts',self.db)['data'],[{'n':2}])

    def test_all_supplied_yaml_columns_compile_against_actual_database(self):
        schema=load_yaml_metadata(ROOT/'newdb/primitves_updated_final',backend='duckdb')
        self.assertEqual(len(schema),21)
        self.assertEqual(sum(len(d['columns']) for d in schema.values()),313)
        for table,details in schema.items():
            sql=render_raw_sql({'class':table,'fields':[c['name'] for c in details['columns']],'filters':[]},schema)
            result=run_sql(sql,ROOT/'newdb/neowealth.duckdb',check=True)
            self.assertEqual(result['status'],'success',(table,result))

    def test_manifest_preserves_all_questions_and_six_full_gold_answers(self):
        destination=self.root/'questions.jsonl'
        self.assertEqual(run_pipeline.prepare_questions(destination),757)
        rows=[json.loads(line) for line in destination.read_text(encoding='utf-8').splitlines()]
        by_id={row['Sample Row ID']:row for row in rows}
        self.assertEqual(len(json.loads(by_id['T3_187']['Ground Truth'])),7860)
        self.assertEqual(len(json.loads(by_id['T3_133']['Ground Truth'])),3030)
        self.assertEqual(sum(json.loads(row['Ground Truth'])==[] for row in rows),21)
        self.assertNotIn('gold_sql',rows[0])

    def test_four_questions_have_distinct_planners_executors_and_sessions(self):
        self._verify_four_worker_execution()

    def test_retry_failure_and_pending_questions_preserves_successful_row(self):
        self._verify_four_worker_execution(retry=True)

    def test_retry_graded_failures_keeps_match_and_replaces_other_results(self):
        self._verify_four_worker_execution(retry=True, graded=True)

    def _verify_four_worker_execution(self, retry=False, graded=False):
        module=importlib.import_module('run_pipeline_v3_sql.main')
        raw=self.root/'questions.jsonl'
        raw.write_text(''.join(json.dumps({'Sample Row ID':str(i),'Question':f'Question {i}','Ground Truth':'[]'})+'\n' for i in range(5 if retry else 4)),encoding='utf-8')
        output=self.root/'raw.csv'
        if retry:
            saved = [{'Sample Row ID': str(i), 'Question': f'Question {i}', 'Ground Truth': '[]',
                      'New Status': 'PIPELINE_SUCCESS' if i == 0 or (graded and i != 3) else 'FINAL_SPEC_ERROR',
                      'New Pipeline Result': 'kept successful answer' if i == 0 else 'old failure'} for i in range(5 if graded else 2)]
            with output.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(saved[0]))
                writer.writeheader()
                writer.writerows(saved)
            if graded:
                grade_path = self.root / 'graded.csv'
                with grade_path.open('w', encoding='utf-8', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(saved[0]))
                    writer.writeheader()
                    writer.writerows([{**row, 'New Status': status} for row, status in zip(saved,
                        ['MATCH', 'MISMATCH', 'PARTIAL', 'FINAL_SPEC_ERROR', 'MISMATCH'])])

        def prepare_retry(report, manifest, selected_ids, companions):
            return {**manifest, 'mixed_results': True, 'retry_history': [{
                'backup_directory': str(self.root / 'offline-backup'),
                'selected_ids': list(selected_ids), 'completed_ids': []}]}
        barrier=threading.Barrier(4)
        owners=[]
        class Planner:
            def __init__(self,*args,**kwargs): owners.append(('planner',self))
            def plan_optimal_dag_from_decomposition(self,*args): return nx.DiGraph([('scan','final')])
        class Executor:
            def __init__(self,*args,**kwargs): owners.append(('executor',self))
            def execute_dag(self,*args,**kwargs):
                return {'final_answer':'[]','trace':{'final_output_produced':True,'final_operator_data':[],
                    'scan_status':'success','operator_sequence':['Scan','Final_Spec']}}
        class Session:
            def __init__(self,*args,**kwargs): owners.append(('session',self));self.log=[]
            def run(self,stage,operator,inputs): return operator(inputs)
        def retrieve(*args): barrier.wait(timeout=5);return {'retrieved_tables':['TABLE_ACCOUNTS']}
        def compile_pack(*args,**kwargs):
            kwargs['diagnostics']['cache_hit']=True
            return {'rules':[]},'offline'
        logger=SimpleNamespace(save=lambda:None,log_call=lambda *args:None)
        with patch.multiple(module,REPORT_FILE=str(output),SQLITE_DB_PATH=str(self.db),TEST_MAX_WORKERS=4,
                            TEST_QUERY_LIMIT=0,TEST_QUERY_OFFSET=0,api_logger=logger,
                            AdvancedAOPPlanner=Planner,AOPExecutor=Executor,ConsultationSession=Session,
                            semantic_retrieve=retrieve,semantic_decompose_question=lambda *args:{'selected_decomposition':{}},
                            understand_query=lambda *args,**kwargs:{},build_gpt_oss_client=lambda:object(),
                            load_yaml_metadata=lambda *args,**kwargs:self.schema,load_documents=lambda *args:[],
                            compile_knowledge=compile_pack), \
             patch.object(module, 'prepare_in_place_retry', side_effect=prepare_retry), \
             patch('run_pipeline_v3_sql.runtime_guard.wait_for_memory'), \
             patch.dict('os.environ',{'INPUT_QUERY_FILE':str(raw),'RETRY_ERRORS_IN_PLACE':'1' if retry else '0',
                                     'RETRY_INCLUDE_PENDING':'1' if retry else '0','QUERY_DELAY_SECONDS':'0',
                                     'RETRY_GRADED_REPORT':str(grade_path) if graded else '',
                                     'RETRY_QUERY_SPEC_ERRORS_ONLY':'0','QUERY_SHUFFLE_SEED':''}):
            module._main(RunTiming())
        with output.open(encoding='utf-8-sig',newline='') as handle: rows=list(csv.DictReader(handle))
        self.assertEqual(len(rows),5 if retry else 4)
        self.assertEqual({row['New Status'] for row in rows},{'PIPELINE_SUCCESS'})
        if retry:
            self.assertEqual(next(row for row in rows if row['Sample Row ID'] == '0')['New Pipeline Result'],
                             'kept successful answer')
        for kind in ('planner','executor','session'):
            self.assertEqual(len({id(owner) for name,owner in owners if name==kind}),4,kind)


if __name__=='__main__':
    unittest.main()
