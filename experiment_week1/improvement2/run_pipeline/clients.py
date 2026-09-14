"""LLM client builders."""

from .common import LLMClient, ROLE_PROMPTS, os


def supports_temperature(model: str) -> bool:
    return not str(model or "").lower().startswith("gpt-5")


def build_llm_messages(role_key: str, prompt: str) -> list[dict[str, str]]:
    system_prompt = ROLE_PROMPTS.get(role_key, ROLE_PROMPTS["semantic"])
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]


def build_gpt_oss_client():
    """Build the Bedrock OpenAI-compatible client for all GPT-OSS 120B calls."""
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "AWS_BEDROCK_API_KEY is required for the GPT-OSS 120B Bedrock endpoint."
        )

    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError(
                "BEDROCK_REGION is required for the GPT-OSS 120B Bedrock endpoint "
                "(for example: BEDROCK_REGION=us-east-1)."
            )
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"

    return LLMClient(api_key=api_key, base_url=base_url)


def build_openai_sparql_client():
    return build_gpt_oss_client()


def build_openai_planner_client():
    return build_gpt_oss_client()
