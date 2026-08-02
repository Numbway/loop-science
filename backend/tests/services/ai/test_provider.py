from types import SimpleNamespace

import pytest

from app.services.ai.code_agent import CodeAgent
from app.services.ai.provider import (
    build_model_client,
    create_text_completion,
)


def test_openai_compatible_text_completion_uses_chat_protocol() -> None:
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content='{"summary": "ok"}')
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message)]
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    text = create_text_completion(
        client=client,
        provider="openai_compatible",
        model="provider-model",
        system="system prompt",
        messages=[{"role": "user", "content": "paper"}],
        max_tokens=512,
    )

    assert text == '{"summary": "ok"}'
    assert captured["model"] == "provider-model"
    assert captured["messages"][0] == {
        "role": "system",
        "content": "system prompt",
    }


def test_anthropic_text_completion_uses_messages_protocol() -> None:
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text="part one"),
                    SimpleNamespace(type="text", text=" part two"),
                ]
            )

    text = create_text_completion(
        client=SimpleNamespace(messages=Messages()),
        provider="anthropic",
        model="claude-compatible",
        system="system prompt",
        messages=[{"role": "user", "content": "paper"}],
        max_tokens=512,
    )

    assert text == "part one part two"
    assert captured["model"] == "claude-compatible"
    assert captured["system"] == "system prompt"


def test_unknown_model_protocol_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported model protocol"):
        build_model_client(
            provider="unknown",
            api_key="not-a-real-key",
            base_url="https://models.example.edu/v1",
        )


@pytest.mark.asyncio
async def test_openai_compatible_agent_executes_function_tools(tmp_path) -> None:
    responses = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="call-1",
                                function=SimpleNamespace(
                                    name="write_file",
                                    arguments=(
                                        '{"path":"train.py",'
                                        '"content":"print(\\"ready\\")"}'
                                    ),
                                ),
                            )
                        ],
                    )
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Framework ready.",
                        tool_calls=None,
                    )
                )
            ]
        ),
    ]

    class Completions:
        def create(self, **_kwargs):
            return responses.pop(0)

    agent = CodeAgent(tmp_path)
    agent._model = "provider-model"
    agent._client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )

    result = await agent._run_openai_agent_loop("Create training code.", 3)

    assert result.success is True
    assert result.modified_files == ["train.py"]
    assert (tmp_path / "train.py").read_text(encoding="utf-8") == (
        'print("ready")'
    )
