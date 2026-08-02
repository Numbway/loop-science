"""Small protocol adapter for reusable model configurations."""

from __future__ import annotations

from typing import Any

ANTHROPIC_PROVIDER = "anthropic"
OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
SUPPORTED_PROVIDERS = {
    ANTHROPIC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
}


def build_model_client(
    *,
    provider: str,
    api_key: str,
    base_url: str,
) -> Any:
    """Create a provider client without leaking credentials into public config."""
    if provider == OPENAI_COMPATIBLE_PROVIDER:
        from openai import OpenAI

        return OpenAI(api_key=api_key, base_url=base_url)
    if provider == ANTHROPIC_PROVIDER:
        from anthropic import Anthropic

        return Anthropic(api_key=api_key, base_url=base_url)
    raise ValueError(f"Unsupported model protocol: {provider}")


def create_text_completion(
    *,
    client: Any,
    provider: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> str:
    """Return text from Anthropic Messages or OpenAI-compatible Chat Completions."""
    if provider == OPENAI_COMPATIBLE_PROVIDER:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                *messages,
            ],
        )
        return str(response.choices[0].message.content or "")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return "".join(
        block.text
        for block in response.content
        if getattr(block, "type", "") == "text"
    )
