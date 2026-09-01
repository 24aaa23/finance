from pathlib import Path

from script_diff_llm.config.paths import config_root


def experiment_config_dir() -> Path:
    return config_root() / "experiments"


def list_experiment_configs() -> list[Path]:
    return sorted(
        path
        for path in experiment_config_dir().glob("*.yaml")
        if not path.name.startswith("_")
    )


def resolve_experiment_config(value: str) -> Path:
    raw = Path(value)
    if raw.is_absolute() and raw.exists():
        return raw.resolve()

    candidates = []
    if raw.suffix == ".yaml":
        candidates.append(experiment_config_dir() / raw.name)
    else:
        candidates.append(experiment_config_dir() / f"{raw.name}.yaml")
    candidates.append(experiment_config_dir() / raw.name)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    available = ", ".join(path.stem for path in list_experiment_configs())
    raise FileNotFoundError(
        f"Experiment config '{value}' was not found. Available experiments: {available}"
    )
