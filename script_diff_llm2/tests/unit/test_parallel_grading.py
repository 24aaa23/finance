import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from script_diff_llm.evaluation.parallel_grading import parallel_regrade,read_rows,write_rows

ROOT=Path(__file__).resolve().parents[2]


class ParallelGradingTest(unittest.TestCase):
    def test_same_grader_row_workflow_and_resume_as_sequential(self):
        loader=importlib.util.spec_from_file_location('offline_unchanged_grader',ROOT/'grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py')
        grader=importlib.util.module_from_spec(loader);loader.loader.exec_module(grader)
        rows=[]
        for i,status in enumerate(['PIPELINE_SUCCESS','DAG_NODE_ERROR','PRE_SCAN_ERROR','PIPELINE_SUCCESS','PIPELINE_SUCCESS']):
            rows.append({'Sample Row ID':str(i),'Question':str(i),'Ground Truth':'[{"group":"A","count":2}]',
                         'New Pipeline Result':'[{"group":"A","count":2},{"group":null,"count":9}]',
                         'New Status':status,'Category':'mc_diverse' if i==3 else 'ordinary'})
        def judge(**kwargs):
            q=kwargs['question']
            if q=='4':raise TimeoutError('request timed out')
            if kwargs.get('null_review'):
                return {'status':'MATCH','reason':'review','evidence':{},
                        'null_policy_checks':{k:True for k in grader.NULL_REVIEW_CHECKS}}
            return {'status':'PARTIAL' if q=='3' else 'MATCH','reason':'fixed offline result','evidence':{}}
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);raw=directory/'raw_pipeline.csv'
            sequential=directory/'sequential.csv';parallel=directory/'parallel.csv'
            write_rows(raw,rows)
            with patch.object(grader,'direct_llm_grade_row',side_effect=judge) as evaluate:
                grader.regrade_existing_report(str(raw),str(sequential),Mock(),'gpt-5-mini')
                parallel_regrade(grader,raw,parallel,Mock(),'gpt-5-mini',workers=2)
                self.assertEqual(read_rows(sequential),read_rows(parallel))
                self.assertEqual(read_rows(parallel)[3]['Direct LLM Grading Path'],'direct_llm_null_group_review')
                evaluate.reset_mock()
                parallel_regrade(grader,raw,parallel,Mock(),'gpt-5-mini',workers=2)
                self.assertEqual(evaluate.call_count,1)
                self.assertEqual(evaluate.call_args.kwargs['question'],'4')
                self.assertEqual(read_rows(sequential),read_rows(parallel))
            self.assertFalse(list(directory.glob('.parallel_grader_*')))

    def test_rejects_duplicate_inputs_and_same_output(self):
        grader=Mock();grader.grading_input_key.return_value='same'
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)/'raw.csv';out=Path(directory)/'grade.csv'
            row={'Question':'q','Ground Truth':'[]','New Pipeline Result':'[]'}
            write_rows(raw,[row,row])
            with self.assertRaises(ValueError):parallel_regrade(grader,raw,out,None,'offline')
            with self.assertRaises(ValueError):parallel_regrade(grader,raw,raw,None,'offline')


if __name__=='__main__':unittest.main()
