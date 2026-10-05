"""Offline checks for model isolation, resume guards and raw-only execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import grade_only

import run_raw
from script_diff_llm.config.runtime import load_runtime_config


class AblationSetupTest(unittest.TestCase):
    def test_pilot_window_and_prepare_only_keep_fixed_dataset(self):
        args=run_raw.parse_args(['gemma_3_27b_it','with_context','--limit','25','--offset','10',
                                 '--prepare-context-only','--save-every','5'])
        env,_,_=run_raw.build_environment(args,{})
        self.assertEqual(env['TEST_QUERY_LIMIT'],'25')
        self.assertEqual(env['TEST_QUERY_OFFSET'],'10')
        self.assertEqual(env['DOMAIN_CONTEXT_PREPARE_ONLY'],'1')
        self.assertEqual(env['REPORT_SAVE_EVERY'],'5')
        self.assertEqual(env['INPUT_SAMPLE_FILE'],str(run_raw.SOURCES['INPUT_SAMPLE_FILE']))
    def test_all_eight_configs_route_every_llm_stage_to_selected_model(self):
        for model, (expected, _, _) in run_raw.MODELS.items():
            for condition in run_raw.CONDITIONS:
                with self.subTest(model=model, condition=condition):
                    args = run_raw.parse_args([model, condition])
                    env, output, config_path = run_raw.build_environment(args, {'DOMAIN_CONTEXT_REQUIRED': '1', 'DOMAIN_INTRO_FILE': 'wrong', 'SQLITE_DB_PATH': 'wrong'})
                    with patch.dict(os.environ, env, clear=True):
                        config = load_runtime_config(str(config_path))
                    for name in ('primary_model', 'local_model', 'rag_model', 'planner_model',
                                 'query_spec_model', 'refine_model', 'validate_model', 'explain_model', 'sparql_generation_model'):
                        self.assertEqual(getattr(config, name), expected)
                    self.assertEqual(config.llm_grader_model, 'gpt-5-mini')
                    self.assertEqual(config.test_query_limit, 1000)
                    self.assertEqual(config.sqlite_db_path, str(run_raw.SOURCES['SQLITE_DB_PATH']))
                    self.assertEqual(config.input_sample_file, str(run_raw.SOURCES['INPUT_SAMPLE_FILE']))
                    self.assertEqual(config.report_file, str(output / 'raw_pipeline.csv'))
                    if condition == 'without_context':
                        self.assertEqual(env['DOMAIN_CONTEXT_REQUIRED'], '')
                        self.assertEqual(env['DOMAIN_INTRO_FILE'], '')
                    else:
                        self.assertEqual(env['DOMAIN_CONTEXT_REQUIRED'], '1')

    def test_resume_guard_rejects_changed_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = {'signature': 'first'}
            run_raw.check_resume(output, manifest)
            (output / 'run_manifest.json').write_text(json.dumps(manifest))
            (output / 'raw_pipeline.csv').write_text('saved rows')
            run_raw.check_resume(output, manifest)
            with self.assertRaises(ValueError):
                run_raw.check_resume(output, {'signature': 'other'})

    def test_manifest_excludes_credentials_and_tracks_endpoint(self):
        args = run_raw.parse_args(['gpt_oss_120b', 'without_context'])
        env, _, config = run_raw.build_environment(args, {'ABLATION_API_KEY': 'TEST_SECRET_DO_NOT_RECORD'})
        manifest = run_raw.manifest_for(args, env, config)
        self.assertNotIn('TEST_SECRET_DO_NOT_RECORD', json.dumps(manifest))
        altered = copy.deepcopy(env)
        altered['ABLATION_BASE_URL'] = 'https://other.example/v1'
        self.assertNotEqual(manifest['signature'], run_raw.manifest_for(args, altered, config)['signature'])

    def test_manual_grader_forces_mini_after_loading_existing_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / 'runs/gpt_oss_120b/without_context/run_01'
            output.mkdir(parents=True)
            (output / 'raw_pipeline.csv').write_text('placeholder,offline fixture')
            grader = SimpleNamespace(LLM_GRADER_MODEL='gpt-5.6-terra', OUTPUT_DIR='wrong',
                                     RAW_REPORT_FILE='wrong', REPORT_FILE='wrong',
                                     APILogger=Mock(return_value=Mock()),
                                     build_openai_grader_client=Mock(return_value='offline-client'),
                                     regrade_existing_report=Mock())
            loader = Mock()
            fake_spec = SimpleNamespace(loader=loader)
            with patch.object(grade_only, 'BASE', base), patch.object(grade_only.importlib.util, 'spec_from_file_location', return_value=fake_spec), patch.object(grade_only.importlib.util, 'module_from_spec', return_value=grader):
                self.assertEqual(grade_only.main(['gpt_oss_120b', 'without_context']), 0)
            self.assertEqual(grader.LLM_GRADER_MODEL, 'gpt-5-mini')
            grader.regrade_existing_report.assert_called_once_with(
                str(output / 'raw_pipeline.csv'), str(output / 'graded_pipeline_gpt_5_mini.csv'),
                'offline-client', 'gpt-5-mini')
            grader.api_logger.save.assert_called_once()

    def test_context_budget_changes_are_tracked_for_resume(self):
        args = run_raw.parse_args(['kimi_k2_thinking', 'with_context'])
        env, _, config = run_raw.build_environment(args, {})
        manifest = run_raw.manifest_for(args, env, config)
        self.assertEqual(manifest['configuration']['context_token_budgets'],
                         {'initial': 16384, 'retry': 32768})
        changed = dict(env, DOMAIN_CONTEXT_MAX_TOKENS='24000')
        self.assertNotEqual(manifest['signature'], run_raw.manifest_for(args, changed, config)['signature'])

    def test_endpoint_override_and_fixed_dataset(self):
        args = run_raw.parse_args(['gemma_3_27b_it', 'without_context', '--base-url', 'https://example.test/v1', '--model-id', 'custom-gemma'])
        env, _, _ = run_raw.build_environment(args, {'INPUT_SAMPLE_FILE': '/other-dataset', 'ABLATION_RAW_MODEL': 'wrong'})
        self.assertEqual(env['ABLATION_BASE_URL'], 'https://example.test/v1')
        self.assertEqual(env['ABLATION_RAW_MODEL'], 'custom-gemma')
        self.assertEqual(env['INPUT_SAMPLE_FILE'], str(run_raw.SOURCES['INPUT_SAMPLE_FILE']))

    def test_dry_run_never_launches_pipeline_or_grader(self):
        with patch.object(run_raw, 'execute_raw') as execute:
            with patch.object(run_raw, 'load_local_env_file'), patch.object(run_raw, 'check_resume'):
                self.assertEqual(run_raw.main(['deepseek_v3_2', 'without_context', '--dry-run']), 0)
        execute.assert_not_called()

    def test_raw_main_launches_only_raw_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            args = run_raw.parse_args(['gpt_oss_120b', 'without_context'])
            env, _, experiment = run_raw.build_environment(args, {})
            output = Path(directory)
            with patch.object(run_raw, 'load_local_env_file'), patch.object(run_raw, 'build_environment', return_value=(env, output, experiment)):
                with patch.object(run_raw, 'execute_raw', return_value=0) as execute:
                    self.assertEqual(run_raw.main(['gpt_oss_120b', 'without_context']), 0)
            command = execute.call_args.args[0]
            self.assertIn('run_pipeline.py', command[2])
            self.assertFalse(any('grade_' in arg for arg in command))


if __name__ == '__main__':
    unittest.main()
