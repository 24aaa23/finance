import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from script_diff_llm.config.paths import (
    default_experiment_config_path,
    default_output_dir,
    default_sql_asset_manifest,
    default_sqlite_db_path,
    legacy_gpt_oss_train_dir,
    project_root,
)


def load_local_env_file() -> None:
    script_dir = Path(__file__).resolve().parent
    legacy_dir = legacy_gpt_oss_train_dir()
    root_dir = project_root()
    env_candidates = [
        legacy_dir / ".env",
        legacy_dir.parent / ".env",
        root_dir / ".env",
        root_dir / "env" / ".env",
        script_dir / ".env",
        script_dir.parent / ".env",
    ]
    env_file = next((path for path in env_candidates if path.exists()), None)
    if env_file is None:
        return
    with env_file.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if value and value[0] in {'"', "'"}:
                quote = value[0]
                end_quote = value.find(quote, 1)
                if end_quote != -1:
                    value = value[1:end_quote]
                else:
                    value = value.strip(quote)
            else:
                value = value.split("#", 1)[0].strip()
            os.environ.setdefault(key.strip(), value)


def _load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}, got {type(data).__name__}.")
    return data


def _resolve_repo_path(root_dir: Path, value: str | None) -> str:
    if not value:
        return ""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    return str(candidate.resolve())


def _clean_env_path(value: str | None) -> str:
    """Strip shell-style quotes/comments from path environment variables."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text[0] in {'"', "'"}:
        quote = text[0]
        end_quote = text.find(quote, 1)
        if end_quote > 0:
            return text[1:end_quote].strip()
    return text.split("#", 1)[0].strip().strip('"\'')


def _normalize_legacy_repo_path(root_dir: Path, value: str) -> str:
    if not value:
        return value
    normalized = os.path.abspath(value)
    old_prefix = os.path.abspath(str(root_dir / "openai.gpt-oss-120b-aman"))
    if normalized.startswith(old_prefix):
        replacement = os.path.abspath(str(root_dir / "historical_models" / "openai.gpt-oss-120b-aman"))
        candidate = normalized.replace(old_prefix, replacement, 1)
        if os.path.exists(candidate):
            return candidate
    old_repo_prefix = os.path.abspath(
        str(root_dir.parent.parent / "script_diff_llm" / "openai.gpt-oss-120b-aman")
    )
    if normalized.startswith(old_repo_prefix):
        replacement = os.path.abspath(str(root_dir / "historical_models" / "openai.gpt-oss-120b-aman"))
        candidate = normalized.replace(old_repo_prefix, replacement, 1)
        if os.path.exists(candidate):
            return candidate
    return normalized


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError(f"Expected string or list for env config, got {type(value).__name__}.")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug or "default"


def _stage_model(model_data: dict[str, Any], stage_name: str, default_model: str) -> str:
    stage_models = model_data.get("stage_models", {})
    if isinstance(stage_models, dict):
        value = str(stage_models.get(stage_name) or "").strip()
        if value:
            return value
    return default_model


@dataclass(frozen=True)
class RuntimeConfig:
    script_dir: str
    script_diff_root: str
    script_base_dir: str
    experiment_name: str
    experiment_slug: str
    experiment_mode: str
    experiment_split: str
    experiment_config_path: str
    model_name: str
    model_slug: str
    model_config_path: str
    model_provider: str
    model_env: str
    api_key_envs: list[str]
    base_url_env: str
    region_envs: list[str]
    primary_model: str
    gpt_oss_model: str
    local_model: str
    rag_model: str
    planner_model: str
    query_spec_model: str
    refine_model: str
    validate_model: str
    explain_model: str
    sparql_generation_model: str
    llm_grader_model: str
    deterministic_explain: bool
    pipeline_version: str
    test_query_limit: int
    test_query_offset: int
    test_max_workers: int
    benchmark_start_delay_seconds: float
    report_save_every: int
    sparql_scan_timeout_seconds: float
    fuseki_endpoint: str
    fuseki_scan_timeout_seconds: float
    fuseki_metadata_timeout_seconds: float
    sparql_scan_max_retries: int
    pre_scan_validate_max_retries: int
    post_scan_validate_max_retries: int
    scan_refine_max_retries: int
    sparql_scan_process_start_method: str
    base_dir: str
    output_dir: str
    schema_file: str
    instance_file: str
    input_sample_file: str
    input_sample_sheet: str
    sql_asset_file: str
    sql_asset_name: str
    sql_asset_description: str
    sql_schema_notes_file: str
    default_sqlite_db_path: str
    sqlite_db_path: str
    report_file: str
    alias_map_file: str


def load_runtime_config(experiment_config_path: str | None = None) -> RuntimeConfig:
    os.environ.setdefault("QUERY_SHUFFLE_SEED", "4043113952")

    root_dir = project_root()
    experiment_path = Path(
        experiment_config_path
        or os.getenv("EXPERIMENT_CONFIG", str(default_experiment_config_path()))
    )
    if not experiment_path.is_absolute():
        experiment_path = root_dir / experiment_path
    experiment_path = experiment_path.resolve()
    experiment_data = _load_yaml_file(experiment_path)

    model_config_value = experiment_data.get("model_config")
    if not model_config_value:
        raise ValueError(f"Experiment config {experiment_path} is missing model_config.")
    model_path = Path(str(model_config_value))
    if not model_path.is_absolute():
        model_path = root_dir / model_path
    model_path = model_path.resolve()
    model_data = _load_yaml_file(model_path)

    sql_asset_path = Path(
        str(experiment_data.get("sql_asset_file") or default_sql_asset_manifest())
    )
    if not sql_asset_path.is_absolute():
        sql_asset_path = root_dir / sql_asset_path
    sql_asset_path = sql_asset_path.resolve()
    sql_asset_data = _load_yaml_file(sql_asset_path)

    default_model_id = str(model_data.get("default_model") or "").strip()
    if not default_model_id:
        raise ValueError(f"Model config {model_path} is missing default_model.")
    model_env = str(model_data.get("model_env") or "BEDROCK_GPT_OSS_MODEL").strip()
    primary_model = os.getenv(model_env, default_model_id)
    model_name = str(model_data.get("name") or model_path.stem)
    model_slug = str(model_data.get("slug") or _slugify(model_name))
    experiment_name = str(experiment_data.get("name") or experiment_path.stem)
    experiment_slug = str(experiment_data.get("slug") or _slugify(experiment_name))
    experiment_mode = str(experiment_data.get("mode") or "all")
    experiment_split = str(experiment_data.get("split") or "train")

    default_output_dir_value = experiment_data.get("output_dir") or str(
        root_dir / "outputs" / model_slug / experiment_mode / experiment_split
    )
    output_dir = os.getenv("PIPELINE_OUTPUT_DIR", _resolve_repo_path(root_dir, str(default_output_dir_value)))
    default_db_path = _resolve_repo_path(root_dir, str(sql_asset_data.get("database_path") or default_sqlite_db_path()))
    sqlite_db_path = _clean_env_path(os.getenv(
        "SQLITE_DB_PATH",
        _resolve_repo_path(root_dir, str(experiment_data.get("sqlite_db_path") or default_db_path)),
    ))
    if sqlite_db_path == "/path/to/your/actual/wealth_management.db" and os.path.exists(default_db_path):
        sqlite_db_path = default_db_path
    if not os.path.isabs(sqlite_db_path):
        sqlite_db_path = os.path.join(str(root_dir), sqlite_db_path)
    sqlite_db_path = _normalize_legacy_repo_path(root_dir, sqlite_db_path)

    report_basename = str(
        experiment_data.get("report_basename")
        or f"{experiment_slug}.csv"
    )
    report_default = experiment_data.get("report_file") or os.path.join(output_dir, report_basename)

    return RuntimeConfig(
        script_dir=str(root_dir),
        script_diff_root=str(root_dir),
        script_base_dir=str(root_dir),
        experiment_name=experiment_name,
        experiment_slug=experiment_slug,
        experiment_mode=experiment_mode,
        experiment_split=experiment_split,
        experiment_config_path=str(experiment_path),
        model_name=model_name,
        model_slug=model_slug,
        model_config_path=str(model_path),
        model_provider=str(model_data.get("provider") or "aws-bedrock-openai-compatible"),
        model_env=model_env,
        api_key_envs=_as_list(model_data.get("api_key_env")),
        base_url_env=str(model_data.get("base_url_env") or "BEDROCK_BASE_URL"),
        region_envs=_as_list(model_data.get("region_env")),
        primary_model=primary_model,
        gpt_oss_model=primary_model,
        local_model=_stage_model(model_data, "local", primary_model),
        rag_model=_stage_model(model_data, "rag", primary_model),
        planner_model=_stage_model(model_data, "planner", primary_model),
        query_spec_model=_stage_model(model_data, "query_spec", primary_model),
        refine_model=_stage_model(model_data, "refine", primary_model),
        validate_model=_stage_model(model_data, "validate", primary_model),
        explain_model=_stage_model(model_data, "explain", primary_model),
        sparql_generation_model=_stage_model(model_data, "sparql_generation", primary_model),
        llm_grader_model=_stage_model(model_data, "llm_grader", primary_model),
        deterministic_explain=os.getenv("DETERMINISTIC_EXPLAIN", "1").strip().lower() not in {"0", "false", "no"},
        pipeline_version=os.getenv(
            "GPT_OSS_LLM_GRADER_PIPELINE_VERSION",
            str(experiment_data.get("pipeline_version") or "aop-gpt-oss-120b-schema-datatype-fix-v15-grading9-1-full300"),
        ),
        test_query_limit=int(os.getenv("TEST_QUERY_LIMIT", str(experiment_data.get("test_query_limit") or 300))),
        test_query_offset=int(os.getenv("TEST_QUERY_OFFSET", str(experiment_data.get("test_query_offset") or 0))),
        test_max_workers=int(os.getenv("TEST_MAX_WORKERS", str(experiment_data.get("test_max_workers") or 1))),
        benchmark_start_delay_seconds=max(0.0, float(os.getenv("BENCHMARK_START_DELAY_SECONDS", str(experiment_data.get("benchmark_start_delay_seconds") or 0)))),
        report_save_every=max(1, int(os.getenv("REPORT_SAVE_EVERY", str(experiment_data.get("report_save_every") or 1)))),
        sparql_scan_timeout_seconds=max(0.0, float(os.getenv("SPARQL_SCAN_TIMEOUT_SECONDS", str(experiment_data.get("sparql_scan_timeout_seconds") or 60)))),
        fuseki_endpoint=os.getenv("FUSEKI_ENDPOINT", str(experiment_data.get("fuseki_endpoint") or "http://127.0.0.1:3030/wealth/query")),
        fuseki_scan_timeout_seconds=max(0.0, float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", str(experiment_data.get("fuseki_scan_timeout_seconds") or 60)))),
        fuseki_metadata_timeout_seconds=max(0.0, float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", str(experiment_data.get("fuseki_metadata_timeout_seconds") or 60)))),
        sparql_scan_max_retries=max(1, int(os.getenv("SPARQL_SCAN_MAX_RETRIES", str(experiment_data.get("sparql_scan_max_retries") or 3)))),
        pre_scan_validate_max_retries=max(1, int(os.getenv("PRE_SCAN_VALIDATE_MAX_RETRIES", str(experiment_data.get("pre_scan_validate_max_retries") or 3)))),
        post_scan_validate_max_retries=max(1, int(os.getenv("POST_SCAN_VALIDATE_MAX_RETRIES", str(experiment_data.get("post_scan_validate_max_retries") or 3)))),
        scan_refine_max_retries=max(1, int(os.getenv("SCAN_REFINE_MAX_RETRIES", str(experiment_data.get("scan_refine_max_retries") or experiment_data.get("sparql_scan_max_retries") or 3)))),
        sparql_scan_process_start_method=os.getenv("SPARQL_SCAN_PROCESS_START_METHOD", str(experiment_data.get("sparql_scan_process_start_method") or "spawn")),
        base_dir=os.getenv("BASE_DIR", str(root_dir)),
        output_dir=output_dir,
        schema_file=os.getenv("SCHEMA_FILE", _resolve_repo_path(root_dir, str(experiment_data.get("kg_schema_file") or root_dir / "data" / "kg" / "wealth_management_diverse_schema.ttl"))),
        instance_file=os.getenv("INSTANCE_FILE", _resolve_repo_path(root_dir, str(experiment_data.get("kg_instance_file") or root_dir / "data" / "kg" / "wealth_management_diverse_kg.ttl"))),
        input_sample_file=os.getenv("INPUT_SAMPLE_FILE", _resolve_repo_path(root_dir, str(experiment_data.get("input_sample_file") or root_dir / "data" / "benchmarks" / "verification_results_v2_sql_correct_train_300.xlsx"))),
        input_sample_sheet=os.getenv("INPUT_SAMPLE_SHEET", str(experiment_data.get("input_sample_sheet") or "")).strip(),
        sql_asset_file=str(sql_asset_path),
        sql_asset_name=str(sql_asset_data.get("name") or sql_asset_path.parent.name),
        sql_asset_description=str(sql_asset_data.get("description") or ""),
        sql_schema_notes_file=_resolve_repo_path(root_dir, str(sql_asset_data.get("schema_notes_file") or "")),
        default_sqlite_db_path=default_db_path,
        sqlite_db_path=sqlite_db_path,
        report_file=os.getenv("REPORT_FILE", _resolve_repo_path(root_dir, str(report_default))),
        alias_map_file=os.getenv("RDF_ALIAS_MAP_FILE", _resolve_repo_path(root_dir, str(experiment_data.get("rdf_alias_map_file") or root_dir / "data" / "kg" / "rdf_id_alias_map.json"))),
    )
