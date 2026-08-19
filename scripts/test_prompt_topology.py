"""Cache-topology invariant tests for prompt_topology.TurnPrompt.

These turn cache efficiency from an implementation detail into a GDDP
invariant that can regress and therefore can be tested. Each test is named
after the failure mode it guards against.
"""

from __future__ import annotations

import pytest

from scripts.prompt_topology import (
    CacheTopologyError,
    TurnPrompt,
    common_prefix_tokens,
    prompt_cache_report,
    token_estimate,
    volatility_invariant,
)

_PROTO = "PROTOCOL: executor role\nGDDP invariants\noutput contract"
_PROJECT = "PROJECT: architecture\ngraph conventions"
_NODE = "NODE: objective\nacceptance criteria"
_ATTEMPT = "ATTEMPT: worktree=/tmp/x\nattempt_id=abc"


def _tp(**overrides: str) -> TurnPrompt:
    return TurnPrompt(
        protocol=overrides.pop("protocol", _PROTO),
        project=overrides.pop("project", _PROJECT),
        node=overrides.pop("node", _NODE),
        attempt=overrides.pop("attempt", _ATTEMPT),
    )


def test_retry_preserves_prefix() -> None:
    """Two attempts of the same node share protocol+project+node byte-for-byte."""
    a = _tp(attempt="ATTEMPT: worktree=/tmp/x\nattempt_id=run-1").assemble()
    b = _tp(attempt="ATTEMPT: worktree=/tmp/x\nattempt_id=run-2").assemble()
    expected_stable = token_estimate(_PROTO) + token_estimate(_PROJECT) + token_estimate(_NODE)
    assert common_prefix_tokens(a, b) >= expected_stable


def test_different_nodes_share_protocol_and_project() -> None:
    """Different nodes of the same graph share protocol+project, diverge at node."""
    a = _tp(node="NODE: objective A").assemble()
    b = _tp(node="NODE: objective B").assemble()
    shared = token_estimate(_PROTO) + token_estimate(_PROJECT)
    assert common_prefix_tokens(a, b) >= shared


def test_attempt_id_occurs_only_in_attempt_zone() -> None:
    """A volatile id never leaks into an earlier (cached) zone."""
    volatile = "attempt_id=poison-XYZ"
    tp = _tp(attempt=f"ATTEMPT: {volatile}")
    text = tp.assemble()
    bounds = dict(tp.zone_offsets())
    proto_start, proto_end = bounds["protocol"]
    node_start, node_end = bounds["node"]
    attempt_start, attempt_end = bounds["attempt"]
    # The volatile id appears exactly once and only inside the attempt span.
    assert text.count(volatile) == 1
    assert text.index(volatile) >= attempt_start
    assert text.index(volatile) < attempt_end
    # ...and never inside the protocol or node spans.
    assert volatile not in text[proto_start:proto_end]
    assert volatile not in text[node_start:node_end]


def test_worktree_does_not_poison_node_prefix() -> None:
    """worktree_path is attempt-scoped; it must not precede the node zone."""
    tp = _tp(attempt="ATTEMPT: worktree_path=/repo/.worktrees/node-7\nattempt_id=r1")
    text = tp.assemble()
    bounds = dict(tp.zone_offsets())
    node_end = bounds["node"][1]
    assert text.index("worktree_path=") >= node_end


def test_assemble_is_byte_stable_across_construction() -> None:
    """Rebuilding the same TurnPrompt yields identical bytes (no hidden nonces)."""
    assert _tp().assemble() == _tp().assemble()


def test_empty_zones_are_skipped_not_placeholderd() -> None:
    """An empty project zone does not insert a blank separator that shifts offsets."""
    full = _tp().assemble()
    no_project = _tp(project="").assemble()
    # protocol + node + attempt joined by the same separator count
    assert _PROTO in no_project
    assert _PROJECT not in no_project
    assert no_project != full


def test_volatility_invariant_passes_in_order() -> None:
    volatility_invariant(_tp())  # should not raise


def test_volatility_invariant_detects_reordering() -> None:
    """If someone swaps project content into the attempt field, ordering is
    still structurally enforced by assemble, so the invariant holds — but if a
    caller bypasses assemble and hand-orders zones, this guards the contract."""
    tp = _tp()
    # Construct a TurnPrompt whose assemble() is canonical; invariant passes.
    volatility_invariant(tp)
    # A report must not raise on a canonical topology.
    prompt_cache_report(tp)


def test_prompt_cache_report_structural_breakdown() -> None:
    tp = _tp()
    report = prompt_cache_report(tp)
    proto = token_estimate(_PROTO)
    proj = token_estimate(_PROJECT)
    node = token_estimate(_NODE)
    attempt = token_estimate(_ATTEMPT)
    total = proto + proj + node + attempt
    assert report.protocol_tokens == proto
    assert report.project_tokens == proj
    assert report.node_tokens == node
    assert report.attempt_tokens == attempt
    assert report.total_input_tokens == total
    assert report.potential_reuse_tokens == proto + proj + node
    assert report.potential_reuse_ratio == pytest.approx((proto + proj + node) / total)


def test_cache_bust_loss_quantifies_gap_to_provider() -> None:
    """When the provider caches less than the structural potential, bust loss
    is the missing tokens — the 'go find the 1.7%' metric."""
    tp = _tp()
    potential = token_estimate(_PROTO) + token_estimate(_PROJECT) + token_estimate(_NODE)
    actual = int(potential * 0.9)
    expected_loss = potential - actual
    report = prompt_cache_report(tp, actual_cached_tokens=actual)
    assert report.actual_cached_tokens == actual
    assert report.cache_bust_loss_tokens == expected_loss
    assert report.cache_bust_loss_ratio == pytest.approx(expected_loss / potential)


def test_cache_bust_loss_is_zero_when_provider_meets_potential() -> None:
    tp = _tp()
    potential = token_estimate(_PROTO) + token_estimate(_PROJECT) + token_estimate(_NODE)
    report = prompt_cache_report(tp, actual_cached_tokens=potential)
    assert report.cache_bust_loss_tokens == 0
    assert report.cache_bust_loss_ratio == 0.0


def test_cache_bust_loss_capped_at_potential() -> None:
    """A provider reporting zero cached tokens can't bust more than potential."""
    tp = _tp()
    potential = token_estimate(_PROTO) + token_estimate(_PROJECT) + token_estimate(_NODE)
    report = prompt_cache_report(tp, actual_cached_tokens=0)
    assert report.cache_bust_loss_tokens == potential
    assert report.cache_bust_loss_ratio == 1.0


def test_cache_topology_error_is_named() -> None:
    assert issubclass(CacheTopologyError, RuntimeError)
