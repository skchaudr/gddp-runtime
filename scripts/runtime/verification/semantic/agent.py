from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Protocol

from scripts.runtime.verification.schemas import SemanticOutput
from scripts.runtime.verification.semantic.prompt import build_prompt_messages
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


class OpenAICompatibleRunner:
    """Minimal stdlib runner for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 4096,
        timeout_seconds: int = 120,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": self._messages_for_chat_completions(messages),
            "tools": [self._tool_for_chat_completions(tool) for tool in tools],
            "tool_choice": "auto",
            "max_tokens": self.max_tokens,
            "temperature": 0,
        }
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"semantic provider HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"semantic provider request failed: {exc.reason}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"semantic provider returned no choices: {data}")
        choice = choices[0]
        message = choice.get("message") or {}
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
            finish_reason=choice.get("finish_reason") or "",
        )

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _messages_for_chat_completions(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted = []
        for message in messages:
            role = message.get("role")
            if role == "assistant":
                converted_message = {"role": "assistant", "content": message.get("content") or ""}
                if message.get("tool_calls"):
                    converted_message["tool_calls"] = message["tool_calls"]
                converted.append(converted_message)
                continue
            if role == "tool":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id"),
                        "name": message.get("name"),
                        "content": message.get("content") or "",
                    }
                )
                continue
            converted.append({"role": role, "content": message.get("content") or ""})
        return converted

    def _tool_for_chat_completions(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }

    def _parse_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        parsed = []
        for index, call in enumerate(tool_calls):
            function = call.get("function") or {}
            raw_args = function.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"semantic provider returned malformed tool arguments: {raw_args}") from exc
            parsed.append(
                ToolCall(
                    id=call.get("id") or f"tool-call-{index}",
                    name=function.get("name") or "",
                    args=args if isinstance(args, dict) else {},
                )
            )
        return parsed


@dataclass
class SemanticAgent:
    runner: Runner
    toolbox: SemanticToolbox
    max_turns: int = 15
    max_tool_calls: int = 40
    max_tokens: int = 24_000
    max_validation_retries: int = 2

    def run(
        self,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        shape_profile: dict[str, Any] | None = None,
    ) -> SemanticOutput:
        messages = build_prompt_messages(
            node=node,
            graph=graph,
            deterministic_result=self._jsonable(deterministic_result),
            shape_profile=shape_profile,
        )
        remaining_tool_calls = self.max_tool_calls
        remaining_tokens = self.max_tokens - self._estimate_message_tokens(messages)
        validation_retries = 0
        finalization_requested = False
        if remaining_tokens <= 0:
            return self._budget_exhausted(messages, reason="initial prompt exceeds token budget")

        for turn_index in range(self.max_turns):
            if self._near_limits(
                turn_index=turn_index,
                remaining_tokens=remaining_tokens,
                remaining_tool_calls=remaining_tool_calls,
            ) and not finalization_requested:
                messages.append(self._finalization_prompt())
                remaining_tokens -= self._estimate_text_tokens(messages[-1]["content"])
                finalization_requested = True
                if remaining_tokens <= 0:
                    return self._budget_exhausted(messages, reason="finalization prompt exhausted token budget")

            response = self.runner.chat(messages, tools=TOOL_SCHEMAS)
            remaining_tokens -= self._estimate_text_tokens(response.content)
            if remaining_tokens <= 0:
                return self._budget_exhausted(messages, reason="model response exhausted token budget")

            if response.tool_calls:
                messages.append(self._assistant_tool_call_message(response))
                for call in response.tool_calls:
                    if call.name == "submit_verdict":
                        submitted = self._validate_submitted_verdict(call.args)
                        if isinstance(submitted, SemanticOutput):
                            return submitted
                        if validation_retries >= self.max_validation_retries:
                            return self._budget_exhausted(
                                messages,
                                reason=f"submit_verdict validation failed after retry: {submitted}",
                            )
                        messages.append(self._validation_error_message(call, submitted))
                        validation_retries += 1
                        continue

                    if remaining_tool_calls <= 0:
                        return self._budget_exhausted(messages, reason="tool call budget exhausted")
                    tool_result = self._execute_tool_safely(call)
                    tool_content = json.dumps(tool_result, default=str)
                    remaining_tokens -= self._estimate_text_tokens(tool_content)
                    if remaining_tokens <= 0:
                        return self._budget_exhausted(messages, reason="tool result exhausted token budget")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": tool_content,
                        }
                    )
                    remaining_tool_calls -= 1
                continue

            if response.finish_reason in {"stop", "end_turn", ""}:
                parsed = self._parse_semantic_output(response.content)
                if isinstance(parsed, SemanticOutput):
                    return parsed
                if validation_retries >= self.max_validation_retries:
                    return self._budget_exhausted(
                        messages,
                        reason=f"terminal SemanticOutput validation failed after retry: {parsed}",
                    )
                messages.append(self._terminal_validation_retry_message(parsed))
                validation_retries += 1
                continue

            messages.append({"role": "assistant", "content": response.content})

        return self._budget_exhausted(messages, reason="turn budget exhausted")

    def investigate(
        self,
        node: dict[str, Any],
        project: dict[str, Any],
        deterministic_result: Any,
        shape_profile: dict[str, Any] | None = None,
    ) -> SemanticOutput:
        return self.run(
            node=node,
            graph=project,
            deterministic_result=deterministic_result,
            shape_profile=shape_profile,
        )

    def _assistant_tool_call_message(self, response: LLMResponse) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.args)},
                }
                for call in response.tool_calls
            ],
        }

    def _parse_semantic_output(self, content: str) -> SemanticOutput | str:
        try:
            return SemanticOutput.model_validate_json(content)
        except Exception as exc:
            return str(exc)

    def _validate_submitted_verdict(self, args: dict[str, Any]) -> SemanticOutput | str:
        try:
            return SemanticOutput.model_validate(args)
        except Exception as exc:
            return str(exc)

    def _validation_error_message(self, call: ToolCall, error: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": json.dumps(
                {
                    "ok": False,
                    "error": (
                        "submit_verdict arguments failed SemanticOutput validation. "
                        "Retry submit_verdict with a complete typed payload."
                    ),
                    "detail": error,
                }
            ),
        }

    def _terminal_validation_retry_message(self, error: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": (
                "Your terminal response failed SemanticOutput validation. "
                "Retry now by calling submit_verdict with a complete typed payload. "
                f"Validation error: {error}"
            ),
        }

    def _finalization_prompt(self) -> dict[str, Any]:
        return {
            "role": "user",
            "content": (
                "You are near the semantic investigation limit. Stop tool use and call "
                "submit_verdict now using only the evidence already gathered. Mark "
                "uncertain criteria indeterminate."
            ),
        }

    def _near_limits(
        self,
        *,
        turn_index: int,
        remaining_tokens: int,
        remaining_tool_calls: int,
    ) -> bool:
        return (
            turn_index >= self.max_turns - 1
            or remaining_tool_calls <= 0
            or remaining_tokens <= 1_000
        )

    def _execute_tool_safely(self, call: ToolCall) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.toolbox.execute(call.name, call.args)}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "tool": call.name}

    def _budget_exhausted(self, messages: list[dict[str, Any]], reason: str) -> SemanticOutput:
        return SemanticOutput(
            judgments=[],
            overall_reasoning=f"Semantic investigation stopped gracefully: {reason}.",
            risks=f"Partial result only. The loop stopped after {len(messages)} messages.",
            followup_candidates=None,
            budget_exhausted=True,
        )

    def _jsonable(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "__dict__"):
            return value.__dict__
        return value

    def _estimate_message_tokens(self, messages: list[dict[str, Any]]) -> int:
        return sum(self._estimate_text_tokens(json.dumps(message, default=str)) for message in messages)

    def _estimate_text_tokens(self, text: str) -> int:
        # Conservative local estimate: enough to enforce a hard budget without provider tokenization.
        return max(1, (len(text) + 3) // 4)
