"""Evaluator cache-report wiring tests.

PiHarnessRunner.run() spawns `pi` so it is not unit-testable here. These
tests cover the load-bearing, pure part: the TurnPrompt the evaluator builds
(constructed the same way pi_runner.run() builds it) produces a structural
prompt_cache_report whose protocol zone is the SYSTEM_PROMPT and whose zone
order is stable->volatile. This is the GDDP-authored shape view that lands in
the verdict receipt's budget_trace.prompt_cache_report.
"""

from __future__ import annotations

from scripts.prompt_topology import TurnPrompt, prompt_cache_report
from scripts.runtime.verification.semantic.prompt import build_turn_prompt
from scripts.runtime.verification.semantic.pi_runner import PI_SYSTEM_PROMPT


def _eval_turn_prompt(*, node, graph, deterministic_result, shape_profile=None):
    """Mirror what pi_runner.run() builds: protocol=SYSTEM_PROMPT, user zones
    from build_turn_prompt."""
    eval_tp = build_turn_prompt(
        node=node,
        graph=graph,
        deterministic_result=deterministic_result,
        shape_profile=shape_profile,
    )
    return TurnPrompt(
        protocol=PI_SYSTEM_PROMPT,
        project=eval_tp.project,
        node=eval_tp.node,
        attempt=eval_tp.attempt,
    )


def test_evaluator_report_protocol_is_system_prompt():
    """The protocol zone of the evaluator's report is the SYSTEM_PROMPT (the
    cached prefix shared by every evaluation), not the empty string the
    user-message-only build_turn_prompt carries."""
    tp = _eval_turn_prompt(
        node={"id": "n1"}, graph={"project_id": "p1"}, deterministic_result={"ok": True}
    )
    report = prompt_cache_report(tp)
    assert report.protocol_tokens > 0
    assert tp.protocol == PI_SYSTEM_PROMPT


def test_evaluator_report_zones_are_stable_to_volatile():
    """protocol (system) -> project (graph) -> node -> attempt; the cacheable
    prefix reaches through the graph zone, and the per-node variance starts at
    the node zone."""
    tp_a = _eval_turn_prompt(
        node={"id": "node-a"}, graph={"project_id": "shared"}, deterministic_result={"ok": True}
    )
    tp_b = _eval_turn_prompt(
        node={"id": "node-b"}, graph={"project_id": "shared"}, deterministic_result={"ok": True}
    )
    text_a = tp_a.assemble()
    text_b = tp_b.assemble()
    # Different nodes share protocol + project prefix.
    node_marker = "node: "
    shared_prefix = text_a[: text_a.index(node_marker)]
    assert text_b.startswith(shared_prefix)
    assert "node-a" not in shared_prefix
    assert "node-b" not in shared_prefix
    # And the report reflects potential_reuse = protocol + project + node.
    report = prompt_cache_report(tp_a)
    assert report.potential_reuse_tokens == (
        report.protocol_tokens + report.project_tokens + report.node_tokens
    )


def test_evaluator_report_retry_preserves_protocol_project_node():
    """Two evaluations of the same node with different deterministic_result
    share protocol + project + node byte-for-byte; only the attempt tail
    changes. The structural potential_reuse_tokens is identical across
    retries (it is the retry-stable prefix)."""
    node = {"id": "n1", "acceptance_criteria": ["c"]}
    graph = {"project_id": "p1"}
    tp1 = _eval_turn_prompt(node=node, graph=graph, deterministic_result={"r": 1})
    tp2 = _eval_turn_prompt(node=node, graph=graph, deterministic_result={"r": 2})
    r1 = prompt_cache_report(tp1)
    r2 = prompt_cache_report(tp2)
    assert r1.potential_reuse_tokens == r2.potential_reuse_tokens
    assert r1.protocol_tokens == r2.protocol_tokens
    assert r1.project_tokens == r2.project_tokens
    assert r1.node_tokens == r2.node_tokens
    # Only the attempt tail differs.
    assert tp1.assemble()[: tp1.assemble().index("deterministic_result: ")] == (
        tp2.assemble()[: tp2.assemble().index("deterministic_result: ")]
    )


def test_evaluator_report_actual_cached_from_json_stdout():
    """Under --mode json, stdout is JSONL events with message.usage.cacheRead.
    _extract_cached_from_stdout parses it and feeds actual_cached_tokens into
    the report — the same provider-reality path the executor uses."""
    import json
    import tempfile
    from scripts.runtime.verification.semantic.pi_runner import _extract_cached_from_stdout

    # Real pi json-mode stdout shape (message_end with usage.cacheRead).
    events = [
        {"type": "session", "version": 3, "id": "x"},
        {"type": "agent_start"},
        {"type": "message_start", "message": {"role": "assistant", "usage": {"cacheRead": 0}}},
        {"type": "message_end", "message": {"role": "assistant", "usage": {"input": 5000, "output": 100, "cacheRead": 42000, "cacheWrite": 0}}},
        {"type": "turn_end", "message": {"usage": {"cacheRead": 42000}}},
        {"type": "agent_end"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        stdout_path = f.name
    # Deduped: message_end only, not message_start/turn_end.
    assert _extract_cached_from_stdout(stdout_path) == 42000

    # Missing file -> None (crash before any output).
    assert _extract_cached_from_stdout("/nonexistent/path") is None

    # No usage events -> None.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"type": "agent_start"}) + "\n")
        f.write(json.dumps({"type": "agent_end"}) + "\n")
        assert _extract_cached_from_stdout(f.name) is None


def test_evaluator_report_serializes_for_budget_trace():
    """The report as_dict() is JSON-serializable and carries provider reality
    (None) + GDDP zones, ready to attach to budget_trace.prompt_cache_report."""
    import json

    tp = _eval_turn_prompt(
        node={"id": "n1"}, graph={"project_id": "p1"}, deterministic_result={"ok": True}
    )
    d = prompt_cache_report(tp).as_dict()
    # Round-trips through JSON (budget_trace is dict[str, Any]).
    json.dumps(d)
    assert d["actual_cached_tokens"] is None
    assert "protocol_tokens" in d and "potential_reuse_tokens" in d
