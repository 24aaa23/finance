from pathlib import Path


def project_root() -> Path:
    """Return the repository root from the installed/in-tree package location."""
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return project_root() / "data"


def config_root() -> Path:
    return project_root() / "configs"


def legacy_gpt_oss_train_dir() -> Path:
    return project_root() / "historical_models" / "openai.gpt-oss-120b-aman" / "all" / "train"


def default_model_config_path() -> Path:
    return config_root() / "models" / "openai_gpt_oss_120b.yaml"


def default_experiment_config_path() -> Path:
    return config_root() / "experiments" / "openai_gpt_oss_120b_all_train.yaml"


def default_sql_asset_dir() -> Path:
    return data_root() / "sql" / "wealth_management_diverse"


def default_sql_asset_manifest() -> Path:
    return default_sql_asset_dir() / "asset.yaml"


def default_sqlite_db_path() -> Path:
    return legacy_gpt_oss_train_dir() / "wealth_management_diverse.db"


def default_output_dir() -> Path:
    return project_root() / "outputs" / "openai.gpt-oss-120b-aman" / "all" / "train"
