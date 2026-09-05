"""Tests for the orchestrator wake prompt.

The properties pinned here are the ones a stateless allocator cannot recover
from: a contract that promises an action the decision channel refuses, a
prefix that silently changes between wakes (re-billing the whole prompt and
breaking the cache the design exists to use), or run constants leaking into
the volatile zone.
"""

import os

from .orchestrator_decision import ACTIONS, parse_decision
from .orchestrator_pack import (
    Capacity,
    EvaluatorSurface,
    GraphSurface,
    OrchestratorPack,
    render_pack,
)
from .orchestrator_prompt import ALLOCATOR_CONTRACT, build_wake_prompt

RUN_BLOCK = "Advised: keep nodes small. Worker budget for this run: 3."


def _pack(**overrides) -> OrchestratorPack:
    fields = {
        "project_id": "demo",
        "repo": "owner/demo",
        "generated_at": "2026-09-04T12:00:00+00:00",
        "capacity": Capacity(max_concurrent_jobs=2, active_jobs=0, free_slots=2),
        "graph": GraphSurface(
            total_nodes=1, status_counts={"ready": 1}, dispatchable=["alpha"]
        ),
        "workers": [],
        "plumbing": [],
        "nodes": [],
        "evaluator": EvaluatorSurface(),
        "human_gate": [],
        "steer": [],
        "decisions": [],
        "pointers": {"graph": "/graphs/demo"},
    }
    fields.update(overrides)
    return OrchestratorPack(**fields)


# --- the contract and the decision channel must agree -----------------------


def test_every_channel_action_is_named_in_the_contract():
    """A wake can only emit what parse_decision accepts; the contract must
    teach exactly that vocabulary, all of it."""
    for action in sorted(ACTIONS):
        assert f"- {action}" in ALLOCATOR_CONTRACT


def test_every_parsed_field_is_named_in_the_contract():
    """The JSON example is the model's schema. A field the channel reads but
    the contract omits would arrive by improvisation; a field the contract
    shows but the channel ignores would be a promise the runtime breaks."""
    for field in ("action", "node_id", "from_n", "to_n", "reason", "expect", "surfaces"):
        assert field in ALLOCATOR_CONTRACT


def test_every_pack_surface_is_named_in_the_contract():
    for surface in ("worker", "plumbing", "node", "graph", "evaluator", "human_gate"):
        assert surface in ALLOCATOR_CONTRACT


def test_the_contracts_example_decision_parses():
    """The shape the contract demonstrates must survive the channel."""
    decision = parse_decision(
        {
            "action": "dispatch",
            "node_id": "alpha",
            "to_n": 3,
            "reason": "only dispatchable node and capacity is free",
            "expect": "an attempt handle appears for alpha",
            "surfaces": {"worker": "idle", "graph": "one dispatchable"},
        }
    )
    assert decision.action == "dispatch" and decision.to_n == 3


# --- prefix discipline -------------------------------------------------------


def test_prompt_opens_with_the_byte_identical_contract():
    one = build_wake_prompt(_pack(), run_block=RUN_BLOCK)
    two = build_wake_prompt(
        _pack(generated_at="2026-09-04T13:00:00+00:00"), run_block=RUN_BLOCK
    )

    assert one.startswith(ALLOCATOR_CONTRACT)
    assert two.startswith(ALLOCATOR_CONTRACT)
    shared = os.path.commonprefix([one, two])
    assert f"### THIS RUN\n{RUN_BLOCK}" in shared


def test_contract_carries_nothing_volatile():
    """A date, a project name, or a count in the contract would re-bill the
    prefix on every wake that differs in it."""
    assert "2026" not in ALLOCATOR_CONTRACT
    assert "demo" not in ALLOCATOR_CONTRACT


def test_run_block_precedes_the_pack():
    prompt = build_wake_prompt(_pack(), run_block=RUN_BLOCK)

    assert prompt.index("### THIS RUN") < prompt.index("### PACK")


def test_pack_renders_verbatim_as_the_delta_zone():
    pack = _pack()
    prompt = build_wake_prompt(pack, run_block=RUN_BLOCK)

    assert prompt.endswith(render_pack(pack))


def test_empty_run_block_leaves_no_zone():
    prompt = build_wake_prompt(_pack())

    assert "### THIS RUN" not in prompt
    assert prompt.startswith(ALLOCATOR_CONTRACT)
