from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.runtime.verification.semantic.agent import LLMResponse, OpenAICompatibleRunner, SemanticAgent, ToolCall
from scripts.runtime.verification.semantic.prompt import build_prompt_messages
from scripts.runtime.verification.semantic.tools import SemanticToolbox, ToolSafetyError


class MockRunner:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        return self.responses.pop(0)


def test_file_tools_are_read_only_and_repo_scoped(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    toolbox = SemanticToolbox(tmp_path)

    assert toolbox.read_file("app.py").startswith("def hello")
    assert toolbox.grep_code("hello")[0]["path"] == "app.py"

    with pytest.raises(ToolSafetyError):
        toolbox.read_file("../outside.txt")
    with pytest.raises(ToolSafetyError):
        toolbox.run_command(["touch", "new-file"])
    with pytest.raises(ToolSafetyError):
        toolbox.run_command(["curl", "https://example.com"])


def test_agent_uses_mock_runner_and_toolbox_without_network(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("VALUE = 42\n", encoding="utf-8")
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call-1", name="read_file", args={"path": "module.py"})],
                finish_reason="tool_use",
            ),
            LLMResponse(
                content=(
                    '{"judgments":[{"criterion_id":"c1","judgment":"judged_pass",'
                    '"confidence":0.9,"evidence":["module.py contains VALUE"],'
                    '"reasoning":"The file has the expected value."}],'
                    '"overall_reasoning":"Mock investigation complete.",'
                    '"risks":null,"followup_candidates":null,"budget_exhausted":false}'
                ),
                tool_calls=[],
                finish_reason="stop",
            ),
        ]
    )

    output = SemanticAgent(runner=runner, toolbox=SemanticToolbox(tmp_path)).run(
        node={"id": "n1", "acceptance": ["c1"]},
        graph={"id": "p1"},
        deterministic_result={"criteria": []},
    )

    assert runner.calls == 2
    assert output.budget_exhausted is False
    assert output.judgments[0].judgment == "judged_pass"



def test_agent_accepts_typed_submit_verdict_tool(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="verdict-1",
                        name="submit_verdict",
                        args={
                            "judgments": [
                                {
                                    "criterion_id": "c1",
                                    "judgment": "judged_pass",
                                    "confidence": 0.9,
                                    "evidence": ["module.py:1"],
                                    "reasoning": "typed verdict",
                                }
                            ],
                            "overall_reasoning": "Submitted through the typed terminal tool.",
                            "risks": None,
                            "followup_candidates": None,
                            "budget_exhausted": False,
                        },
                    )
                ],
                finish_reason="tool_use",
            )
        ]
    )

    output = SemanticAgent(runner=runner, toolbox=SemanticToolbox(tmp_path)).run(
        node={}, graph={}, deterministic_result={}
    )

    assert runner.calls == 1
    assert output.judgments[0].criterion_id == "c1"
    assert output.overall_reasoning == "Submitted through the typed terminal tool."


def test_agent_retries_malformed_submit_verdict(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="bad-verdict",
                        name="submit_verdict",
                        args={
                            "judgments": [
                                {
                                    "criterion_id": "c1",
                                    "judgment": "pass",
                                    "confidence": 1.2,
                                    "evidence": [],
                                    "reasoning": "bad enum and confidence",
                                }
                            ],
                            "overall_reasoning": "bad",
                            "risks": None,
                            "followup_candidates": None,
                            "budget_exhausted": False,
                        },
                    )
                ],
                finish_reason="tool_use",
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="good-verdict",
                        name="submit_verdict",
                        args={
                            "judgments": [
                                {
                                    "criterion_id": "c1",
                                    "judgment": "indeterminate",
                                    "confidence": 0.4,
                                    "evidence": [],
                                    "reasoning": "retry corrected the typed verdict",
                                }
                            ],
                            "overall_reasoning": "valid retry",
                            "risks": None,
                            "followup_candidates": None,
                            "budget_exhausted": False,
                        },
                    )
                ],
                finish_reason="tool_use",
            ),
        ]
    )

    output = SemanticAgent(runner=runner, toolbox=SemanticToolbox(tmp_path)).run(
        node={}, graph={}, deterministic_result={}
    )

    assert runner.calls == 2
    assert output.judgments[0].judgment == "indeterminate"


def test_agent_forces_finalization_on_last_turn(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="final-verdict",
                        name="submit_verdict",
                        args={
                            "judgments": [
                                {
                                    "criterion_id": "c1",
                                    "judgment": "indeterminate",
                                    "confidence": 0.3,
                                    "evidence": [],
                                    "reasoning": "forced finalization near limit",
                                }
                            ],
                            "overall_reasoning": "finalized near limit",
                            "risks": None,
                            "followup_candidates": None,
                            "budget_exhausted": False,
                        },
                    )
                ],
                finish_reason="tool_use",
            )
        ]
    )

    output = SemanticAgent(
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        max_turns=1,
    ).run(node={}, graph={}, deterministic_result={})

    assert runner.calls == 1
    assert output.overall_reasoning == "finalized near limit"


def test_agent_returns_budget_exhausted_when_tool_budget_is_spent(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call-1", name="list_directory", args={"path": "."})],
                finish_reason="tool_use",
            )
        ]
    )

    output = SemanticAgent(
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        max_tool_calls=0,
    ).run(node={}, graph={}, deterministic_result={})

    assert output.budget_exhausted is True
    assert output.judgments == []


def test_agent_returns_partial_result_when_token_budget_is_spent(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="x" * 200,
                tool_calls=[],
                finish_reason="stop",
            )
        ]
    )

    output = SemanticAgent(
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        max_tokens=120,
    ).run(node={"id": "n1"}, graph={"id": "p1"}, deterministic_result={"criteria": []})

    assert output.budget_exhausted is True
    assert output.judgments == []


def test_prompt_builder_renders_node_graph_and_deterministic_context() -> None:
    messages = build_prompt_messages(
        node={"id": "node-a", "acceptance": ["criterion"]},
        graph={"project_id": "project-a", "execution_policy": "human merge"},
        deterministic_result={"criteria_mismatches": [{"criterion_id": "criterion"}]},
    )

    rendered = "\n".join(message["content"] for message in messages)
    assert "node-a" in rendered
    assert "project-a" in rendered
    assert "criteria_mismatches" in rendered


def test_openai_compatible_runner_converts_tools_and_tool_messages() -> None:
    runner = OpenAICompatibleRunner(api_key="key", base_url="https://example.test/v1", model="model")

    tool = runner._tool_for_chat_completions(
        {
            "name": "read_file",
            "description": "Read a file.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    )
    messages = runner._messages_for_chat_completions(
        [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "call-1", "type": "function"}]},
            {"role": "tool", "tool_call_id": "call-1", "name": "read_file", "content": "ok"},
        ]
    )

    assert runner._endpoint() == "https://example.test/v1/chat/completions"
    assert tool["type"] == "function"
    assert tool["function"]["parameters"]["properties"]["path"]["type"] == "string"
    assert messages[0]["tool_calls"][0]["id"] == "call-1"
    assert messages[1]["role"] == "tool"


def test_openai_compatible_runner_parses_tool_calls() -> None:
    runner = OpenAICompatibleRunner(api_key="key", base_url="https://example.test/v1/chat/completions", model="model")

    calls = runner._parse_tool_calls(
        [
            {
                "id": "call-1",
                "function": {"name": "read_file", "arguments": '{"path":"module.py"}'},
            }
        ]
    )

    assert runner._endpoint() == "https://example.test/v1/chat/completions"
    assert calls == [ToolCall(id="call-1", name="read_file", args={"path": "module.py"})]


def test_toolbox_reads_configured_yaml_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    node_yaml = config / "node.yaml"
    project_yaml = config / "project.yaml"
    node_yaml.write_text("node_id: n1\n", encoding="utf-8")
    project_yaml.write_text("project_id: p1\n", encoding="utf-8")

    toolbox = SemanticToolbox(repo, node_yaml_path=node_yaml, project_yaml_path=project_yaml)

    assert "node_id: n1" in toolbox.read_node_yaml()
    assert "project_id: p1" in toolbox.read_project_yaml()
    with pytest.raises(ToolSafetyError):
        toolbox.read_file(str(node_yaml))
