"""Shared target-model routing for the finance baseline runners.

The runners all use the OpenAI Python client's Chat Completions interface.  This
module keeps provider credentials and endpoint selection out of the prompts and
preserves the existing Bedrock/Mantle behaviour for previously evaluated models.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


def provider_for_model(model: str) -> str:
    """Return the configured provider, falling back to a model-name mapping."""
    explicit = os.getenv("TARGET_PROVIDER", "").strip().lower()
    aliases = {
        "aws": "bedrock",
        "bedrock-runtime": "bedrock",
        "google": "gemini",
    }
    if explicit:
        return aliases.get(explicit, explicit)

    normalized = str(model or "").strip().lower()
    if normalized.startswith("openai.gpt-oss"):
        return "bedrock"
    if normalized.startswith("gpt-"):
        return "openai"
    if normalized.startswith("gemini-"):
        return "gemini"
    if normalized.startswith("meta.llama"):
        return "bedrock-converse"
    return "mantle"


def make_model_client(model: str) -> OpenAI:
    """Build an OpenAI-compatible client for the selected target model."""
    provider = provider_for_model(model)
    options: dict[str, Any] = {"timeout": 180, "max_retries": 1}

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI target models.")
        options["api_key"] = key
        if os.getenv("OPENAI_BASE_URL"):
            options["base_url"] = os.environ["OPENAI_BASE_URL"]
        return OpenAI(**options)

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini target models.")
        options.update({
            "api_key": key,
            "base_url": os.getenv(
                "GEMINI_OPENAI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
        })
        return OpenAI(**options)

    if provider == "bedrock-converse":
        raise RuntimeError(
            "This Llama target requires Bedrock Converse rather than the OpenAI-compatible "
            "endpoint. Verify that the exact model is available before running it."
        )

    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if provider == "bedrock":
        key = (
            os.getenv("AWS_BEDROCK_API_KEY")
            or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
            or os.getenv("BEDROCK_API_KEY")
        )
        base_url = os.getenv("BEDROCK_BASE_URL")
        if not base_url and region:
            base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    elif provider == "mantle":
        key = (
            os.getenv("BEDROCK_MANTLE_API_KEY")
            or os.getenv("AWS_BEDROCK_API_KEY")
            or os.getenv("BEDROCK_API_KEY")
        )
        base_url = os.getenv("BEDROCK_MANTLE_BASE_URL")
        if not base_url and region:
            base_url = f"https://bedrock-mantle.{region}.api.aws/v1"
    else:
        raise RuntimeError(f"Unsupported TARGET_PROVIDER: {provider}")

    if not key:
        raise RuntimeError(f"A Bedrock API key is required for provider '{provider}'.")
    if not base_url:
        raise RuntimeError(f"BEDROCK_REGION or an explicit base URL is required for provider '{provider}'.")
    options.update({"api_key": key, "base_url": base_url})
    return OpenAI(**options)


def supports_temperature(model: str) -> bool:
    """Whether the target accepts the legacy temperature parameter used here."""
    normalized = str(model or "").strip().lower()
    return not normalized.startswith(("gpt-5", "gpt-6", "gemini-3.8"))

