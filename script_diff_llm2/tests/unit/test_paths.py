import unittest
from pathlib import Path

from script_diff_llm.config.paths import (
    config_root,
    default_experiment_config_path,
    default_model_config_path,
    default_sql_asset_manifest,
    default_sqlite_db_path,
    legacy_gpt_oss_train_dir,
    project_root,
)
from script_diff_llm.config.experiments import list_experiment_configs, resolve_experiment_config
from script_diff_llm.config.runtime import load_runtime_config
from script_diff_llm.pipeline.gpt_oss_pipeline import (
    normalize_classification,
    pre_programmed_check_schema,
    semantic_classify_query,
    semantic_validate,
)
from script_diff_llm.pipeline.registry import build_operator_registry


class PathsTest(unittest.TestCase):
    def test_project_root_exists(self):
        self.assertTrue(project_root().exists())

    def test_legacy_experiment_dir_exists(self):
        self.assertTrue(legacy_gpt_oss_train_dir().exists())

    def test_default_sqlite_db_path_points_to_existing_db(self):
        self.assertTrue(default_sqlite_db_path().exists())

    def test_default_model_config_exists(self):
        self.assertTrue(default_model_config_path().exists())

    def test_default_experiment_config_exists(self):
        self.assertTrue(default_experiment_config_path().exists())

    def test_default_sql_asset_manifest_exists(self):
        self.assertTrue(default_sql_asset_manifest().exists())

    def test_canonical_data_asset_dirs_exist(self):
        self.assertFalse((project_root() / "kg").exists())
        self.assertFalse((project_root() / "dataset").exists())
        self.assertTrue((project_root() / "data" / "kg").exists())
        self.assertTrue((project_root() / "data" / "benchmarks").exists())

    def test_runtime_config_loads_yaml_and_sql_asset(self):
        config = load_runtime_config()
        self.assertTrue(config.model_config_path.endswith(".yaml"))
        self.assertTrue(config.experiment_config_path.endswith(".yaml"))
        self.assertTrue(config.sql_asset_file.endswith("asset.yaml"))
        self.assertTrue(config.sqlite_db_path.endswith("wealth_management_diverse.db"))
        self.assertEqual(config.model_slug, "openai.gpt-oss-120b-aman")
        self.assertEqual(config.experiment_mode, "all")
        self.assertEqual(config.experiment_split, "train")
        self.assertIn("/outputs/openai.gpt-oss-120b-aman/all/train", config.output_dir)
        self.assertTrue(config.report_file.endswith("openai_gpt_oss_120b_all_train.csv"))
        self.assertIn("/data/kg/", config.schema_file)
        self.assertIn("/data/benchmarks/", config.input_sample_file)

    def test_all_non_template_experiment_configs_load(self):
        experiments_dir = config_root() / "experiments"
        for path in sorted(experiments_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            with self.subTest(experiment=path.name):
                config = load_runtime_config(str(path))
                self.assertTrue(config.model_config_path.endswith(".yaml"))
                self.assertTrue(Path(config.model_config_path).exists())
                self.assertTrue(Path(config.sql_asset_file).exists())
                self.assertTrue(config.report_file.endswith(".csv"))

    def test_experiment_resolver_lists_and_resolves(self):
        experiments = list_experiment_configs()
        self.assertGreaterEqual(len(experiments), 3)
        resolved = resolve_experiment_config("openai_gpt_oss_120b_all_train")
        self.assertEqual(resolved, default_experiment_config_path().resolve())


class CanonicalRegistryTest(unittest.TestCase):
    @staticmethod
    def _stub(*args, **kwargs):
        return {}

    def test_canonical_registry_excludes_legacy_operators(self):
        registry = build_operator_registry(
            lightweight_index={},
            kg_metadata={},
            rdf_graph=None,
            retrieve_client=None,
            query_spec_client=None,
            sparql_generation_client=None,
            validate_client=None,
            refine_client=None,
            explain_client=None,
            rag_model="stub",
            query_spec_model="stub",
            sparql_generation_model="stub",
            validate_model="stub",
            refine_model="stub",
            explain_model="stub",
            semantic_retrieve=self._stub,
            semantic_build_query_spec=self._stub,
            semantic_generate_sparql=self._stub,
            semantic_pre_scan_validate=self._stub,
            semantic_refine=self._stub,
            pre_programmed_scan=self._stub,
            semantic_explain_results=self._stub,
            pre_programmed_math_compute=self._stub,
            pre_programmed_set_intersect=self._stub,
            pre_programmed_union=self._stub,
            pre_programmed_difference=self._stub,
        )
        self.assertNotIn("Validate", registry)
        self.assertNotIn("Classify", registry)
        self.assertNotIn("Check_Schema", registry)

    def test_legacy_operator_exports_still_exist(self):
        self.assertTrue(callable(semantic_validate))
        self.assertTrue(callable(semantic_classify_query))
        self.assertTrue(callable(normalize_classification))
        self.assertTrue(callable(pre_programmed_check_schema))


if __name__ == "__main__":
    unittest.main()
