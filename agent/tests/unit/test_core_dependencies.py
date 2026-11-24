from __future__ import annotations

import importlib.metadata
import socket
import sys
from collections.abc import Iterator
from typing import TypedDict

import pytest


@pytest.fixture(autouse=True)
def _offline_sdk_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dependency compatibility tests must remain offline")

    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    yield


def test_required_versions_and_python_support() -> None:
    assert sys.version_info[:2] == (3, 12)
    assert {
        package: importlib.metadata.version(package)
        for package in (
            "langchain",
            "langchain-core",
            "langgraph",
            "langgraph-checkpoint-redis",
            "pydantic",
            "pytest",
            "redis",
        )
    } == {
        "langchain": "1.5.2",
        "langchain-core": "1.8.4",
        "langgraph": "1.2.24",
        "langgraph-checkpoint-redis": "0.6.0",
        "pydantic": "2.14.4",
        "pytest": "8.0.0",
        "redis": "8.1.0",
    }


def test_state_graph_wrapper_does_not_leak_private_child_state() -> None:
    from langgraph.graph import END, START, StateGraph

    class ChildState(TypedDict):
        private_value: int

    child_builder = StateGraph(ChildState)
    child_builder.add_node(
        "increment", lambda state: {"private_value": state["private_value"] + 1}
    )
    child_builder.add_edge(START, "increment")
    child_builder.add_edge("increment", END)
    child = child_builder.compile()

    class ParentState(TypedDict):
        input: int
        output: int

    def run_child(state: ParentState) -> dict[str, int]:
        result = child.invoke({"private_value": state["input"]})
        return {"output": result["private_value"]}

    parent_builder = StateGraph(ParentState)
    parent_builder.add_node("child_wrapper", run_child)
    parent_builder.add_edge(START, "child_wrapper")
    parent_builder.add_edge("child_wrapper", END)

    result = parent_builder.compile().invoke({"input": 4})

    assert result == {"input": 4, "output": 5}
    assert "private_value" not in result


def test_messages_round_trip_tool_ids_and_provider_signature() -> None:
    from langchain_core.messages import (
        AIMessage,
        ToolMessage,
        messages_from_dict,
        messages_to_dict,
    )

    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup",
                    "args": {"query": "offline"},
                    "id": "call-123",
                    "type": "tool_call",
                }
            ],
            additional_kwargs={"provider_signature": "opaque-signature"},
        ),
        ToolMessage(content="result", tool_call_id="call-123"),
    ]

    restored = messages_from_dict(messages_to_dict(messages))

    assert restored[0].tool_calls[0]["id"] == "call-123"
    assert restored[0].additional_kwargs["provider_signature"] == "opaque-signature"
    assert restored[1].tool_call_id == "call-123"


def test_structured_tool_uses_strict_forbid_extra_schema() -> None:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, ConfigDict, ValidationError

    class AddArguments(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        left: int
        right: int

    def add(left: int, right: int) -> int:
        return left + right

    tool = StructuredTool.from_function(
        func=add,
        name="add",
        description="Add two integers.",
        args_schema=AddArguments,
    )

    assert tool.invoke({"left": 2, "right": 3}) == 5
    with pytest.raises(ValidationError):
        tool.invoke({"left": "2", "right": 3})
    with pytest.raises(ValidationError):
        tool.invoke({"left": 2, "right": 3, "unexpected": 4})


def test_redis_saver_matches_checkpoint_base_without_connecting() -> None:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.checkpoint.redis import RedisSaver

    assert issubclass(RedisSaver, BaseCheckpointSaver)
    assert callable(RedisSaver.from_conn_string)


def test_selected_model_initializer_is_importable_without_a_provider() -> None:
    from langchain.chat_models import init_chat_model

    assert callable(init_chat_model)
