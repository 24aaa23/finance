import os

from openai import OpenAI as LLMClient


def _first_env_value(names: list[str]) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def supports_temperature(model: str) -> bool:
    return not str(model or "").lower().startswith("gpt-5")


def build_model_client(
    *,
    provider: str,
    api_key_envs: list[str],
    base_url_env: str,
    region_envs: list[str],
) -> LLMClient:
    api_key = _first_env_value(api_key_envs)
    if not api_key:
        raise RuntimeError(
            f"One of {api_key_envs} is required for provider {provider}."
        )

    region = _first_env_value(region_envs)
    base_url = os.getenv(base_url_env)
    if not base_url:
        if not region:
            raise RuntimeError(
                f"One of {region_envs} is required for provider {provider} when {base_url_env} is unset."
            )
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url)


def build_gpt_oss_client() -> LLMClient:
    return build_model_client(
        provider="aws-bedrock-openai-compatible",
        api_key_envs=[
            "AWS_BEDROCK_API_KEY",
            "AWS_Bedrock_API_gpt_oss_120b",
            "BEDROCK_API_KEY",
        ],
        base_url_env="BEDROCK_BASE_URL",
        region_envs=["BEDROCK_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"],
    )


def build_openai_sparql_client() -> LLMClient:
    return build_gpt_oss_client()


def build_openai_planner_client() -> LLMClient:
    return build_gpt_oss_client()
