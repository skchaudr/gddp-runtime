from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from scripts.runtime.verification.schemas import SemanticOutput
from scripts.runtime.verification.semantic.tools import TOOL_SCHEMAS, SemanticToolbox


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str


class Runner(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        ...


class AnthropicRunner:
    def __init__(self, client: Any, model: str = "claude-sonnet-4-20250514", max_tokens: int = 4096) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=messages,
            tools=tools,
        )
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", "")
            if block_type == "text":
                content_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id"),
                        name=getattr(block, "name"),
                        args=dict(getattr(block, "input", {}) or {}),
                    )
                )
        return LLMResponse(
            content="\n".join(part for part in content_parts if part),
            tool_calls=tool_calls,
            finish_reason=getattr(response, "stop_reason", ""),
        )


@dataclass
class SemanticAgent:
    runner: Runner
    toolbox: SemanticToolbox
    max_turns: int = 15
    max_tool_calls: int = 40

    def investigate(
        self,
        node: dict[str, Any],
        project: dict[str, Any],
        deterministic_result: Any,
        shape_profile: dict[str, Any] | None = None,
    ) -> SemanticOutput:
        messages = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Investigate acceptance criteria using read-only tools and return SemanticOutput JSON.",
                        "node": node,
                        "project": project,
                        "deterministic_result": self._jsonable(deterministic_result),
                        "shape_profile": shape_profile,
                    },
                    default=str,
                ),
            }
        ]
        remaining_tool_calls = self.max_tool_calls

        for _ in range(self.max_turns):
            response = self.runner.chat(messages, tools=TOOL_SCHEMAS)
            if response.tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                for call in response.tool_calls:
                    if remaining_tool_calls <= 0:
                        return self._budget_exhausted(messages)
                    tool_result = self.toolbox.execute(call.name, call.args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(tool_result, default=str),
                        }
                    )
                    remaining_tool_calls -= 1
                continue

            if response.finish_reason in {"stop", "end_turn", ""}:
                return SemanticOutput.model_validate_json(response.content)

            messages.append({"role": "assistant", "content": response.content})

        return self._budget_exhausted(messages)

    def _budget_exhausted(self, messages: list[dict[str, Any]]) -> SemanticOutput:
        return SemanticOutput(
            judgments=[],
            overall_reasoning=f"Semantic investigation budget exhausted after {len(messages)} messages.",
            risks="Investigation ended before a complete semantic judgment.",
            followup_candidates=None,
            budget_exhausted=True,
        )

    def _jsonable(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return value.__dict__
        return value
