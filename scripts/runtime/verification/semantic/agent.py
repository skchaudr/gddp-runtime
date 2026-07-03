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
    max_tool_result_chars: int = 50_000

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
        initial_tokens = self._estimate_message_tokens(messages)
        remaining_tool_calls = self.max_tool_calls
        remaining_tokens = self.max_tokens - initial_tokens
        validation_retries = 0
        finalization_requested = False
        budget_trace = self._new_budget_trace(
            initial_tokens=initial_tokens,
            remaining_tokens=remaining_tokens,
            remaining_tool_calls=remaining_tool_calls,
        )
        if remaining_tokens <= 0:
            return self._budget_exhausted(
                messages,
                reason="initial prompt exceeds token budget",
                budget_trace=budget_trace,
                remaining_tokens=remaining_tokens,
                remaining_tool_calls=remaining_tool_calls,
            )

        for turn_index in range(self.max_turns):
            if self._near_limits(
                turn_index=turn_index,
                remaining_tokens=remaining_tokens,
                remaining_tool_calls=remaining_tool_calls,
            ) and not finalization_requested:
                messages.append(self._finalization_prompt())
                prompt_tokens = self._estimate_text_tokens(messages[-1]["content"])
                remaining_tokens -= prompt_tokens
                self._trace_event(
                    budget_trace,
                    "finalization_prompt",
                    turn=turn_index,
                    estimated_tokens=prompt_tokens,
                    remaining_tokens=remaining_tokens,
                    remaining_tool_calls=remaining_tool_calls,
                )
                finalization_requested = True
                if remaining_tokens <= 0:
                    return self._budget_exhausted(
                        messages,
                        reason="finalization prompt exhausted token budget",
                        budget_trace=budget_trace,
                        remaining_tokens=remaining_tokens,
                        remaining_tool_calls=remaining_tool_calls,
                    )

            response = self.runner.chat(messages, tools=self._tools_for_turn(finalization_requested))
            response_tokens = self._estimate_text_tokens(response.content)
            remaining_tokens -= response_tokens
            self._trace_event(
                budget_trace,
                "model_response",
                turn=turn_index,
                estimated_tokens=response_tokens,
                tool_calls=len(response.tool_calls),
                finish_reason=response.finish_reason,
                remaining_tokens=remaining_tokens,
                remaining_tool_calls=remaining_tool_calls,
            )
            if remaining_tokens <= 0:
                return self._budget_exhausted(
                    messages,
                    reason="model response exhausted token budget",
                    budget_trace=budget_trace,
                    remaining_tokens=remaining_tokens,
                    remaining_tool_calls=remaining_tool_calls,
                )

            if response.tool_calls:
                messages.append(self._assistant_tool_call_message(response))
                for call in response.tool_calls:
                    if call.name == "submit_verdict":
                        submitted = self._validate_submitted_verdict(call.args)
                        if isinstance(submitted, SemanticOutput):
                            return self._with_budget_trace(
                                submitted,
                                budget_trace,
                                reason="submit_verdict accepted",
                                remaining_tokens=remaining_tokens,
                                remaining_tool_calls=remaining_tool_calls,
                                message_count=len(messages),
                            )
                        if validation_retries >= self.max_validation_retries:
                            return self._budget_exhausted(
                                messages,
                                reason=f"submit_verdict validation failed after retry: {submitted}",
                                budget_trace=budget_trace,
                                remaining_tokens=remaining_tokens,
                                remaining_tool_calls=remaining_tool_calls,
                            )
                        messages.append(self._validation_error_message(call, submitted))
                        validation_retries += 1
                        continue

                    if remaining_tool_calls <= 0:
                        return self._budget_exhausted(
                            messages,
                            reason="tool call budget exhausted",
                            budget_trace=budget_trace,
                            remaining_tokens=remaining_tokens,
                            remaining_tool_calls=remaining_tool_calls,
                        )
                    tool_result = self._execute_tool_safely(call)
                    tool_content, tool_truncated, original_tool_chars = self._bounded_tool_content(tool_result)
                    tool_tokens = self._estimate_text_tokens(tool_content)
                    remaining_tokens -= tool_tokens
                    self._trace_event(
                        budget_trace,
                        "tool_result",
                        turn=turn_index,
                        tool=call.name,
                        estimated_tokens=tool_tokens,
                        truncated=tool_truncated,
                        original_chars=original_tool_chars,
                        ok=bool(tool_result.get("ok")),
                        remaining_tokens=remaining_tokens,
                        remaining_tool_calls=remaining_tool_calls - 1,
                    )
                    if remaining_tokens <= 0:
                        return self._budget_exhausted(
                            messages,
                            reason="tool result exhausted token budget",
                            budget_trace=budget_trace,
                            remaining_tokens=remaining_tokens,
                            remaining_tool_calls=remaining_tool_calls,
                        )
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
                    return self._with_budget_trace(
                        parsed,
                        budget_trace,
                        reason="terminal SemanticOutput accepted",
                        remaining_tokens=remaining_tokens,
                        remaining_tool_calls=remaining_tool_calls,
                        message_count=len(messages),
                    )
                if validation_retries >= self.max_validation_retries:
                    return self._budget_exhausted(
                        messages,
                        reason=f"terminal SemanticOutput validation failed after retry: {parsed}",
                        budget_trace=budget_trace,
                        remaining_tokens=remaining_tokens,
                        remaining_tool_calls=remaining_tool_calls,
                    )
                messages.append(self._terminal_validation_retry_message(parsed))
                validation_retries += 1
                continue

            messages.append({"role": "assistant", "content": response.content})

        return self._budget_exhausted(
            messages,
            reason="turn budget exhausted",
            budget_trace=budget_trace,
            remaining_tokens=remaining_tokens,
            remaining_tool_calls=remaining_tool_calls,
        )

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

    def _tools_for_turn(self, finalization_requested: bool) -> list[dict[str, Any]]:
        if not finalization_requested:
            return TOOL_SCHEMAS
        return [tool for tool in TOOL_SCHEMAS if tool.get("name") == "submit_verdict"]

    def _execute_tool_safely(self, call: ToolCall) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.toolbox.execute(call.name, call.args)}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "tool": call.name}

    def _new_budget_trace(
        self,
        *,
        initial_tokens: int,
        remaining_tokens: int,
        remaining_tool_calls: int,
    ) -> dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
            "max_tool_result_chars": self.max_tool_result_chars,
            "initial_estimated_tokens": initial_tokens,
            "initial_remaining_tokens": remaining_tokens,
            "initial_remaining_tool_calls": remaining_tool_calls,
            "events": [],
        }

    def _trace_event(self, trace: dict[str, Any], event: str, **fields: Any) -> None:
        trace["events"].append({"event": event, **fields})

    def _bounded_tool_content(self, tool_result: dict[str, Any]) -> tuple[str, bool, int]:
        content = json.dumps(tool_result, default=str)
        if len(content) <= self.max_tool_result_chars:
            return content, False, len(content)
        bounded = {
            "ok": tool_result.get("ok", False),
            "truncated": True,
            "original_chars": len(content),
            "max_chars": self.max_tool_result_chars,
            "content": content[: self.max_tool_result_chars],
        }
        return json.dumps(bounded, default=str), True, len(content)

    def _with_budget_trace(
        self,
        output: SemanticOutput,
        budget_trace: dict[str, Any],
        *,
        reason: str,
        remaining_tokens: int,
        remaining_tool_calls: int,
        message_count: int,
    ) -> SemanticOutput:
        trace = dict(budget_trace)
        trace["events"] = list(budget_trace.get("events", []))
        trace.update(
            {
                "final_reason": reason,
                "final_remaining_tokens": remaining_tokens,
                "final_remaining_tool_calls": remaining_tool_calls,
                "message_count": message_count,
            }
        )
        return output.model_copy(update={"budget_trace": trace})

    def _budget_exhausted(
        self,
        messages: list[dict[str, Any]],
        reason: str,
        *,
        budget_trace: dict[str, Any],
        remaining_tokens: int,
        remaining_tool_calls: int,
    ) -> SemanticOutput:
        trace = dict(budget_trace)
        trace["events"] = list(budget_trace.get("events", []))
        trace.update(
            {
                "final_reason": reason,
                "final_remaining_tokens": remaining_tokens,
                "final_remaining_tool_calls": remaining_tool_calls,
                "message_count": len(messages),
            }
        )
        return SemanticOutput(
            judgments=[],
            overall_reasoning=f"Semantic investigation stopped gracefully: {reason}.",
            risks=f"Partial result only. The loop stopped after {len(messages)} messages.",
            followup_candidates=None,
            budget_exhausted=True,
            budget_trace=trace,
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
