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
        self.tool_names_by_call: list[list[str]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        self.tool_names_by_call.append([tool["name"] for tool in tools])
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


def test_python_is_an_allowed_evidence_tool_but_network_and_writes_stay_blocked(tmp_path: Path) -> None:
    toolbox = SemanticToolbox(tmp_path)

    toolbox._assert_safe_command(["python", "-m", "pytest", "-q"])
    toolbox._assert_safe_command(["python3", "-m", "pytest"])
    toolbox._assert_safe_command(["pytest"])
    toolbox._assert_safe_command(["python", "script.py"])

    with pytest.raises(ToolSafetyError):
        toolbox._assert_safe_command(["python", "-m", "pip", "install", "requests"])
    with pytest.raises(ToolSafetyError):
        toolbox._assert_safe_command(["rm", "-rf", "src"])


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
        node={"id": "n1", "acceptance_criteria": ["c1"]},
        graph={"id": "p1"},
        deterministic_result={"criteria": []},
    )

    assert runner.calls == 2
    assert output.budget_exhausted is False
    assert output.judgments[0].judgment == "judged_pass"
    assert output.budget_trace is not None
    assert output.budget_trace["final_reason"] == "terminal SemanticOutput accepted"



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
    assert runner.tool_names_by_call == [["submit_verdict"]]


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
    assert output.budget_trace is not None
    assert output.budget_trace["final_reason"] == "tool call budget exhausted"
    assert output.budget_trace["message_count"] >= 2


def test_agent_returns_partial_result_when_token_budget_is_spent(tmp_path: Path) -> None:
    runner = MockRunner(
        [
            LLMResponse(
                content="x" * 6000,
                tool_calls=[],
                finish_reason="stop",
            )
        ]
    )

    output = SemanticAgent(
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        max_tokens=1200,
    ).run(node={"id": "n1"}, graph={"id": "p1"}, deterministic_result={"criteria": []})

    assert output.budget_exhausted is True
    assert output.judgments == []
    assert output.budget_trace is not None
    assert output.budget_trace["final_reason"] == "model response exhausted token budget"


def test_agent_caps_large_tool_results(tmp_path: Path) -> None:
    (tmp_path / "huge.txt").write_text("x" * 10_000, encoding="utf-8")
    runner = MockRunner(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call-1", name="read_file", args={"path": "huge.txt"})],
                finish_reason="tool_use",
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="verdict-1",
                        name="submit_verdict",
                        args={
                            "judgments": [],
                            "overall_reasoning": "bounded result accepted",
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

    output = SemanticAgent(
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        max_tool_result_chars=1000,
    ).run(node={}, graph={}, deterministic_result={})

    assert output.budget_trace is not None
    tool_events = [event for event in output.budget_trace["events"] if event["event"] == "tool_result"]
    assert tool_events[0]["truncated"] is True
    assert tool_events[0]["original_chars"] > 1000


def test_prompt_builder_renders_node_graph_and_deterministic_context() -> None:
    messages = build_prompt_messages(
        node={"id": "node-a", "acceptance_criteria": ["criterion"]},
        graph={"project_id": "project-a", "execution_policy": "human merge"},
        deterministic_result={"criteria_mismatches": [{"criterion_id": "criterion"}]},
    )

    rendered = "\n".join(message["content"] for message in messages)
    assert "node-a" in rendered
    assert "project-a" in rendered
    assert "criteria_mismatches" in rendered


def test_prompt_builder_graph_zone_is_byte_stable_shared_prefix() -> None:
    """Two different nodes over the same graph must share a byte-identical
    cached prefix (system + framing + graph), with node/deterministic content
    only in the volatile tail. Prefix caching discounts byte-identical prefixes;
    if the volatile zone slips ahead of the graph zone the shared prefix is
    busted for every evaluation of the frontier."""
    graph = {"project_id": "proj-1", "execution_policy": "human merge", "nodes": ["n1", "n2"]}

    def _user(node_id: str, det: dict) -> str:
        msgs = build_prompt_messages(
            node={"id": node_id, "acceptance_criteria": ["c"]},
            graph=graph,
            deterministic_result=det,
        )
        return next(m["content"] for m in msgs if m["role"] == "user")

    user_a = _user("node-a", {"criteria_mismatches": [{"criterion_id": "c1"}]})
    user_b = _user("node-b", {"criteria_mismatches": [{"criterion_id": "c2"}]})

    # The graph zone text is identical and precedes any node-specific text.
    graph_marker = "graph: "
    prefix_a = user_a[: user_a.index(graph_marker) + len(graph_marker)]
    prefix_b = user_b[: user_b.index(graph_marker) + len(graph_marker)]
    assert prefix_a == prefix_b

    # graph zone renders before node zone (stable before volatile).
    assert user_a.index("graph: ") < user_a.index("node: ")
    assert user_a.index("node: ") < user_a.index("deterministic_result: ")
    # A retry of the SAME node with different deterministic_result keeps the
    # graph+node prefix byte-identical (only the volatile tail changes).
    user_a2 = _user("node-a", {"criteria_mismatches": [{"criterion_id": "c1-retry"}]})
    stable_through_node = user_a[: user_a.index("deterministic_result: ")]
    stable_through_node_2 = user_a2[: user_a2.index("deterministic_result: ")]
    assert stable_through_node == stable_through_node_2


def test_prompt_builder_stable_and_volatile_extras_land_in_correct_zone() -> None:
    """stable_prefix_extra joins the cached prefix; volatile_tail_extra lands
    after the volatile zones, never between graph and node."""
    messages = build_prompt_messages(
        node={"id": "n1"},
        graph={"project_id": "p1"},
        deterministic_result={"ok": True},
        stable_prefix_extra="canonical_pointers: {\"readme\":\"R\"}\n",
        volatile_tail_extra="\nneighbor_pointers: {\"neighbor:x\":\"X\"}",
    )
    user = next(m["content"] for m in messages if m["role"] == "user")
    assert user.index("canonical_pointers:") < user.index("graph: ")
    assert user.index("graph: ") < user.index("node: ")
    assert user.index("shape_profile: ") < user.index("neighbor_pointers:")


def test_prompt_builder_attempt_variance_is_tail_only() -> None:
    """Two evaluations of the SAME node with different deterministic_result
    share the protocol+project+node prefix byte-for-byte; only the attempt
    tail changes. This is the evaluator analogue of the executor retry test."""
    from scripts.prompt_topology import common_prefix_tokens, token_estimate

    graph = {"project_id": "p1", "nodes": ["n1"]}
    node = {"id": "n1", "acceptance_criteria": ["c"]}
    msgs1 = build_prompt_messages(
        node=node, graph=graph,
        deterministic_result={"criteria_mismatches": [{"criterion_id": "c1"}]},
    )
    msgs2 = build_prompt_messages(
        node=node, graph=graph,
        deterministic_result={"criteria_mismatches": [{"criterion_id": "c2"}]},
    )
    u1 = next(m["content"] for m in msgs1 if m["role"] == "user")
    u2 = next(m["content"] for m in msgs2 if m["role"] == "user")
    # Everything up to the deterministic_result zone is identical.
    marker = "deterministic_result: "
    shared_prefix = u1[: u1.index(marker)]
    assert u2.startswith(shared_prefix)
    # The system message (protocol) is byte-identical across evaluations.
    s1 = next(m["content"] for m in msgs1 if m["role"] == "system")
    s2 = next(m["content"] for m in msgs2 if m["role"] == "system")
    assert s1 == s2


def test_prompt_builder_different_nodes_share_project_prefix() -> None:
    """Different nodes over the same graph share protocol+project; they diverge
    at the node zone, not before it."""
    graph = {"project_id": "shared", "nodes": ["a", "b"]}
    ma = build_prompt_messages(
        node={"id": "node-a"}, graph=graph, deterministic_result={"ok": True}
    )
    mb = build_prompt_messages(
        node={"id": "node-b"}, graph=graph, deterministic_result={"ok": True}
    )
    ua = next(m["content"] for m in ma if m["role"] == "user")
    ub = next(m["content"] for m in mb if m["role"] == "user")
    # Shared prefix reaches at least through the graph (project) zone.
    node_marker = "node: "
    shared = ua[: ua.index(node_marker)]
    assert ub.startswith(shared)
    # And the node ids differ only after that point.
    assert "node-a" not in shared
    assert "node-b" not in shared


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
