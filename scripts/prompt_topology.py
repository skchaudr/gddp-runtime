"""Cache-aware prompt topology for GDDP executors and evaluators.

A GDDP turn prompt is not a string — it is a stack of zones with monotonically
increasing volatility:

    protocol   nearly immutable     (executor/evaluator role, GDDP invariants,
                                     output contract, tool-use policy)
    project    stable across graph  (architecture, project constraints,
                                     graph conventions, canonical doc pointers)
    node       stable across retries (objective, acceptance criteria,
                                     dependency receipts)
    attempt    deliberately volatile (worktree_path, attempt_id, retry
                                     feedback, current observations)

Prefix caching discounts a byte-identical prompt prefix. Emitting zones in
this order means:

    retries of the same node reuse protocol + project + node
    different nodes of the same graph reuse protocol + project
    different graphs reuse protocol

Reversing any pair of zones busts the cache for everything after them on
every turn. That ordering is load-bearing and is the point of this module:
turn prompt construction as a *cache topology*, not string assembly.

Usage:

    tp = TurnPrompt(protocol=..., project=..., node=..., attempt=...)
    text = tp.assemble()
    report = prompt_cache_report(tp, actual_cached_tokens=...)

The helpers ``common_prefix_tokens`` and ``zone_offsets`` make the cache
invariant testable: two turns that differ only in the attempt zone must share
a common prefix that spans protocol + project + node.
"""

from __future__ import annotations

from dataclasses import dataclass

# Stable separator between zones. Never inject a volatile value (timestamp,
# run id) into a separator — it would bust the cache at every zone boundary.
# This exact byte sequence is load-bearing for prefix stability.
_ZONE_SEP = "\n\n"


@dataclass(frozen=True)
class TurnPrompt:
    """Four-zone prompt with monotonically increasing volatility.

    Every zone is a plain string. ``assemble`` emits them in volatility order;
    ``zone_offsets`` reports the (start, end) char bounds of each zone in the
    assembled text so tests can assert a volatile value lands only in the
    attempt zone.
    """

    protocol: str
    project: str
    node: str
    attempt: str

    def assemble(self) -> str:
        return _ZONE_SEP.join(
            zone for zone in (self.protocol, self.project, self.node, self.attempt)
            if zone
        )

    def zone_offsets(self) -> dict[str, tuple[int, int]]:
        """Return {name: (start, end)} char bounds in the assembled text.

        Insertion order is the canonical zone order, so callers can iterate
        in volatility order. Empty zones are reported with a zero-width span at
        the current cursor so callers can detect them; they are NOT emitted
        into the assembled text.
        """
        zones: dict[str, tuple[int, int]] = {}
        cursor = 0
        for name, body in (
            ("protocol", self.protocol),
            ("project", self.project),
            ("node", self.node),
            ("attempt", self.attempt),
        ):
            if not body:
                zones[name] = (cursor, cursor)
                continue
            start = cursor
            end = cursor + len(body)
            zones[name] = (start, end)
            cursor = end + len(_ZONE_SEP)
        return zones

    def zone_token_estimate(self, name: str) -> int:
        return token_estimate(getattr(self, name))


# Canonical zone order. Tests and reports reference this instead of a literal
# tuple so a future zone addition changes one symbol.
ZONE_ORDER: tuple[str, ...] = ("protocol", "project", "node", "attempt")


def token_estimate(text: str) -> int:
    """Rough local token estimate (chars / 4).

    Good enough to enforce stability invariants and produce a cost-tracker
    breakdown without provider tokenization. The authoritative cached-token
    count comes from the provider and is an input to ``prompt_cache_report``.
    """
    return max(0, (len(text) + 3) // 4)


def common_prefix_tokens(a: str, b: str) -> int:
    """Token estimate of the longest byte-identical prefix of a and b.

    Two turns that differ only in a late zone share the entire early prefix;
    this returns its size in tokens. Use it to assert the cache invariant:
    ``common_prefix_tokens(retry1, retry2) >= EXPECTED_STABLE_PREFIX``.
    """
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return token_estimate(a[:i])


def volatility_invariant(tp: TurnPrompt) -> None:
    """Assert the topology's monotonically-increasing-volatility contract.

    A zone that is *empty* cannot be tested for volatility from a single
    instance, so it is skipped; the contract that matters is zone ORDER, which
    is enforced structurally by ``assemble``. This helper exists so a future
    caller that swaps zone contents raises a named error instead of silently
    busting the cache.

    Raises ``CacheTopologyError`` if the assembled text's zone offsets are out
    of the canonical order.
    """
    offsets = tp.zone_offsets()
    seen: list[str] = []
    for name, (start, end) in tp.zone_offsets().items():
        if end <= start:
            continue  # empty zone — not present, cannot be out of order
        seen.append(name)
    canonical = [z for z in ZONE_ORDER if z in seen]
    if seen != canonical:
        raise CacheTopologyError(
            f"zones out of volatility order: {seen} (canonical: {canonical})"
        )


class CacheTopologyError(RuntimeError):
    """Raised when prompt zones violate the monotonic-volatility invariant."""


@dataclass(frozen=True)
class PromptCacheReport:
    """Per-turn cache-efficiency breakdown for the cost tracker.

    The first four fields are structural (knowable from topology alone).
    ``actual_cached_tokens`` is the provider-reported cached-input-token count
    for this turn; when supplied it yields the real economics. When absent the
    report still shows the *potential* reuse ceiling.

    ``cache_bust_loss_tokens`` is the metric Sab wants: structurally reusable
    tokens the provider did not cache. ``cache_bust_loss_ratio`` is its share
    of the potential-reuse prefix. A non-zero bust loss says "go find the
    stupid 1.7%."
    """

    total_input_tokens: int
    protocol_tokens: int
    project_tokens: int
    node_tokens: int
    attempt_tokens: int
    potential_reuse_tokens: int
    potential_reuse_ratio: float
    actual_cached_tokens: int | None
    cache_bust_loss_tokens: int
    cache_bust_loss_ratio: float

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "protocol_tokens": self.protocol_tokens,
            "project_tokens": self.project_tokens,
            "node_tokens": self.node_tokens,
            "attempt_tokens": self.attempt_tokens,
            "potential_reuse_tokens": self.potential_reuse_tokens,
            "potential_reuse_ratio": round(self.potential_reuse_ratio, 4),
            "actual_cached_tokens": self.actual_cached_tokens,
            "cache_bust_loss_tokens": self.cache_bust_loss_tokens,
            "cache_bust_loss_ratio": round(self.cache_bust_loss_ratio, 4),
        }


def extract_actual_cached_tokens(events: Sequence[dict]) -> int | None:
    """Extract actual cached input tokens reported across a sequence of RPC/LLM events.

    Inspects common provider usage formats:
      - Anthropic / OpenRouter: usage.cache_read_input_tokens
      - OpenAI API: usage.prompt_tokens_details.cached_tokens
      - Generic / Pi events: usage.cached_tokens or usage.cache_read_tokens

    Returns total cached tokens if any usage event with cache details is found,
    or None if no provider usage cache metrics were present in the events.
    """
    total_cached = 0
    found_any = False

    for evt in events:
        if not isinstance(evt, dict):
            continue

        usage_candidates: list[dict] = []
        if "cache_read_input_tokens" in evt or "cached_tokens" in evt or "cache_read_tokens" in evt or "prompt_tokens_details" in evt:
            usage_candidates.append(evt)
        for key in ("usage", "event", "message", "response", "data"):
            val = evt.get(key)
            if isinstance(val, dict):
                if "cache_read_input_tokens" in val or "cached_tokens" in val or "cache_read_tokens" in val or "prompt_tokens_details" in val:
                    usage_candidates.append(val)
                sub_usage = val.get("usage")
                if isinstance(sub_usage, dict):
                    usage_candidates.append(sub_usage)

        if not usage_candidates:
            continue

        usage = usage_candidates[0]
        if "cache_read_input_tokens" in usage and usage["cache_read_input_tokens"] is not None:
            total_cached += int(usage["cache_read_input_tokens"])
            found_any = True
        elif isinstance(usage.get("prompt_tokens_details"), dict):
            ptd = usage["prompt_tokens_details"]
            if "cached_tokens" in ptd and ptd["cached_tokens"] is not None:
                total_cached += int(ptd["cached_tokens"])
                found_any = True
        elif "cached_tokens" in usage and usage["cached_tokens"] is not None:
            total_cached += int(usage["cached_tokens"])
            found_any = True
        elif "cache_read_tokens" in usage and usage["cache_read_tokens"] is not None:
            total_cached += int(usage["cache_read_tokens"])
            found_any = True

    return total_cached if found_any else None


def prompt_cache_report(
    tp: TurnPrompt,
    *,
    actual_cached_tokens: int | None = None,
) -> PromptCacheReport:
    """Build the cache-efficiency breakdown for one turn.

    ``potential_reuse_tokens`` is everything ahead of the attempt zone:
    protocol + project + node. For a retry of the same node that is the exact
    prefix the provider should serve from cache. ``actual_cached_tokens`` is
    what the provider reported; the gap is cache bust loss.
    """
    volatility_invariant(tp)
    proto = tp.zone_token_estimate("protocol")
    proj = tp.zone_token_estimate("project")
    node = tp.zone_token_estimate("node")
    attempt = tp.zone_token_estimate("attempt")
    total = proto + proj + node + attempt
    potential = proto + proj + node
    potential_ratio = potential / total if total else 0.0
    if actual_cached_tokens is None:
        bust = 0
        bust_ratio = 0.0
    else:
        # potential - actual, never negative, never above potential
        bust = max(0, potential - actual_cached_tokens)
        bust_ratio = bust / potential if potential else 0.0
    return PromptCacheReport(
        total_input_tokens=total,
        protocol_tokens=proto,
        project_tokens=proj,
        node_tokens=node,
        attempt_tokens=attempt,
        potential_reuse_tokens=potential,
        potential_reuse_ratio=potential_ratio,
        actual_cached_tokens=actual_cached_tokens,
        cache_bust_loss_tokens=bust,
        cache_bust_loss_ratio=bust_ratio,
    )
