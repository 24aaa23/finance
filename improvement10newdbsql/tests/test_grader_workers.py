"""Check grader concurrency/checkpoints without making model requests."""
from pathlib import Path
import csv
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grader


class GraderWorkerTests(unittest.TestCase):
    def test_success_only_retry_keeps_match_and_grades_recovered_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw.csv'
            output = Path(directory) / 'graded.csv'
            rows = [{'Sample Row ID': str(i), 'Question': f'Question {i}', 'Ground Truth': '[]',
                     'New Pipeline Result': '[]', 'New Status': 'PIPELINE_SUCCESS' if i < 2 else 'SCAN_ERROR',
                     'Category': 'NeoWealth'} for i in range(4)]
            grader.pd.DataFrame(rows).to_csv(source, index=False)
            with patch.object(grader, 'direct_llm_grade_row', side_effect=[
                    {'status': 'MATCH', 'reason': 'Keep', 'evidence': {}},
                    {'status': 'PARTIAL', 'reason': 'Retry', 'evidence': {}}]):
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=1)
            original_match = grader.pd.read_csv(output, dtype=str, keep_default_na=False).iloc[0].to_dict()
            rows[2].update({'New Status': 'PIPELINE_SUCCESS', 'New Pipeline Result': '[{"fixed":true}]'})
            grader.pd.DataFrame(rows).to_csv(source, index=False)
            with patch.object(grader, 'direct_llm_grade_row', return_value={
                    'status': 'MATCH', 'reason': 'Fresh', 'evidence': {}}) as requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=4,
                                              retry_nonmatch=True, only_pipeline_success=True)
            self.assertEqual({call.kwargs['question'] for call in requests.call_args_list}, {'Question 1', 'Question 2'})
            saved = grader.pd.read_csv(output, dtype=str, keep_default_na=False).to_dict(orient='records')
            self.assertEqual([row['Sample Row ID'] for row in saved], ['0', '1', '2'])
            self.assertEqual(saved[0], original_match)
            self.assertEqual([row['New Status'] for row in saved], ['MATCH'] * 3)

    def test_success_only_empty_cohort_writes_header_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw.csv'
            output = Path(directory) / 'graded.csv'
            grader.pd.DataFrame([{'Sample Row ID': 'error', 'Question': 'Failed', 'Ground Truth': '[]',
                                 'New Pipeline Result': '', 'New Status': 'FINAL_SPEC_ERROR'}]).to_csv(source, index=False)
            output.write_text('Sample Row ID,New Status\nerror,FINAL_SPEC_ERROR\n', encoding='utf-8')
            with patch.object(grader, 'direct_llm_grade_row') as requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=4,
                                              retry_nonmatch=True, only_pipeline_success=True)
            requests.assert_not_called()
            self.assertEqual(len(grader.pd.read_csv(output)), 0)
            self.assertTrue(list(Path(directory).glob('graded.csv.backup_*.csv')))

    def test_retry_nonmatch_refreshes_judgments_and_errors_but_keeps_match(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw.csv'
            output = Path(directory) / 'graded.csv'
            rows = [{'Sample Row ID': str(i), 'Question': f'Question {i}', 'Ground Truth': '[]',
                     'New Pipeline Result': '[]', 'New Status': 'SCAN_ERROR' if i == 3 else 'PIPELINE_SUCCESS',
                     'Category': 'NeoWealth'} for i in range(5)]
            grader.pd.DataFrame(rows).to_csv(source, index=False)
            def initial(**kwargs):
                index = int(kwargs['question'].split()[-1])
                if index == 4:
                    raise ValueError('Temporary malformed grader response')
                return {'status': ['MATCH', 'MISMATCH', 'PARTIAL'][index], 'reason': 'Original judgment', 'evidence': {}}
            with patch.object(grader, 'direct_llm_grade_row', side_effect=initial):
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=4)
            old_match = grader.pd.read_csv(output, dtype=str, keep_default_na=False).iloc[0].to_dict()
            before = output.read_bytes()
            rows[3].update({'New Status': 'PIPELINE_SUCCESS', 'New Pipeline Result': '[{"fixed":true}]'})
            grader.pd.DataFrame(rows).to_csv(source, index=False)
            with patch.object(grader, 'direct_llm_grade_row', return_value={
                    'status': 'MATCH', 'reason': 'Fresh judgment', 'evidence': {}}) as requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=4, retry_nonmatch=True)
            self.assertEqual({call.kwargs['question'] for call in requests.call_args_list},
                             {'Question 1', 'Question 2', 'Question 3', 'Question 4'})
            saved = grader.pd.read_csv(output, dtype=str, keep_default_na=False).to_dict(orient='records')
            self.assertEqual(saved[0], old_match)
            self.assertEqual([row['New Status'] for row in saved], ['MATCH'] * 5)
            backups = list(Path(directory).glob('graded.csv.backup_*.csv'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), before)

    def test_retry_nonmatch_leaves_unresolved_pipeline_error_ungraded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw.csv'
            output = Path(directory) / 'graded.csv'
            grader.pd.DataFrame([{'Sample Row ID': 'error', 'Question': 'Failed question', 'Ground Truth': '[]',
                                 'New Pipeline Result': 'Failed execution', 'New Status': 'FINAL_SPEC_ERROR'}]).to_csv(source, index=False)
            with patch.object(grader, 'direct_llm_grade_row') as requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=4, retry_nonmatch=True)
            requests.assert_not_called()
            self.assertEqual(grader.pd.read_csv(output).iloc[0]['New Status'], 'FINAL_SPEC_ERROR')

    def test_eight_concurrent_grades_checkpoint_in_order_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw.csv'
            output = Path(directory) / 'graded.csv'
            rows = [{'Sample Row ID': str(index), 'Question': f'Question {index}',
                     'Ground Truth': '[]', 'New Pipeline Result': '[]',
                     'New Status': 'PIPELINE_SUCCESS', 'Category': 'NeoWealth'} for index in range(8)]
            rows.append({**rows[0], 'Sample Row ID': '8', 'Question': 'Failed question',
                         'New Status': 'PIPELINE_FAILURE'})
            grader.pd.DataFrame(rows).to_csv(source, index=False)
            barrier = threading.Barrier(8)
            worker_ids, writer_ids = set(), set()
            guard = threading.Lock()
            coordinator = threading.get_ident()
            original_replace = grader.os.replace

            def mock_grade(**kwargs):
                with guard:
                    worker_ids.add(threading.get_ident())
                barrier.wait(timeout=10)
                return {'status': 'MATCH', 'reason': 'Offline judgment', 'evidence': {}}

            def record_replace(*args):
                writer_ids.add(threading.get_ident())
                original_replace(*args)

            with patch.object(grader, 'direct_llm_grade_row', side_effect=mock_grade) as requests, \
                 patch.object(grader.os, 'replace', side_effect=record_replace):
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=8)
            self.assertEqual(requests.call_count, 8)
            self.assertEqual(len(worker_ids), 8)
            self.assertEqual(writer_ids, {coordinator})
            with output.open(encoding='utf-8', newline='') as handle:
                saved = list(csv.DictReader(handle))
            self.assertEqual([row['Sample Row ID'] for row in saved], [str(index) for index in range(9)])
            self.assertEqual(saved[-1]['New Status'], 'PIPELINE_FAILURE')
            with patch.object(grader, 'direct_llm_grade_row') as resumed_requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=8)
            resumed_requests.assert_not_called()

    def test_null_group_review_retains_original_grade_and_records_adjustment(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'mc_diverse.csv'
            output = Path(directory) / 'graded.csv'
            truth = [{'segment': 'A', 'aum': 10}]
            answer = truth + [{'segment': None, 'aum': 0}]
            grader.pd.DataFrame([{'Sample Row ID': 'one', 'Question': 'Show AUM by segment.',
                                 'Ground Truth': json.dumps(truth), 'New Pipeline Result': json.dumps(answer),
                                 'New Status': 'PIPELINE_SUCCESS', 'Category': 'mc_diverse'}]).to_csv(source, index=False)
            strict = {'status': 'PARTIAL', 'reason': 'Extra unnamed group', 'evidence': {}}
            review = {'status': 'MATCH', 'reason': 'Label-only adjustment', 'evidence': {},
                      'null_policy_checks': {key: True for key in grader.NULL_REVIEW_CHECKS}}
            with patch.object(grader, 'direct_llm_grade_row', side_effect=[strict, review]) as requests:
                grader.regrade_existing_report(str(source), str(output), None, 'gpt-5-mini', workers=8)
            self.assertEqual(requests.call_count, 2)
            self.assertIsNotNone(requests.call_args.kwargs['null_review'])
            saved = grader.pd.read_csv(output, keep_default_na=False).iloc[0]
            self.assertEqual(saved['Original Grade'], 'PARTIAL')
            self.assertEqual(saved['New Status'], 'MATCH')
            self.assertEqual(saved['Null Policy Status'], 'adjusted')


if __name__ == '__main__':
    unittest.main()
