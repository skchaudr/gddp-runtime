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
    """Per-turn cache report: two separate views, never blended.

    View 1 — provider measurement (authoritative): ``actual_cached_tokens``
    is what the provider reported it served from its prefix cache for this
    turn. It spans the WHOLE prompt the model saw (pi harness: AGENTS.md,
    skills, tool schemas, system prompt + GDDP's zones). GDDP does not author
    or model the harness, so this number is the real cache anchor and is not
    compared against GDDP's own structural potential.

    View 2 — GDDP-authored zone topology: per-zone token estimates and
    ``potential_reuse_tokens`` (protocol + project + node — the stable prefix
    GDDP controls). This describes the SHAPE of what GDDP contributes to the
    cache topology (how much is stable-prefix-shaped vs volatile-tail), not a
    comparable cache-hit ratio. A retry-stable node keeps its node zone
    byte-identical so GDDP's slice stays cacheable; that is the structural
    property GDDP is responsible for.

    There is deliberately no ``cache_bust_loss`` field. A bust-loss computed
    as (GDDP potential - provider actual) is semantically broken: the
    denominator is GDDP's ~hundreds of tokens while the numerator spans the
    ~hundreds-of-thousands-of-token harness GDDP does not model. Modeling the
    harness to produce one grand unified percentage would couple GDDP to pi's
    internal prompt construction; that coupling is rejected until a concrete
    need earns it.
    """

    total_input_tokens: int
    protocol_tokens: int
    project_tokens: int
    node_tokens: int
    attempt_tokens: int
    potential_reuse_tokens: int
    potential_reuse_ratio: float
    actual_cached_tokens: int | None

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
        }


def extract_actual_cached_tokens(events: Sequence[dict]) -> int | None:
    """Extract actual cached input tokens reported across a sequence of RPC/LLM events.

    Inspects common provider usage formats:
      - Pi / openai-codex / xai (VERIFIED against live events.jsonl):
        message.usage.cacheRead  (camelCase, on type=message_end events)
      - Anthropic / OpenRouter: usage.cache_read_input_tokens
      - OpenAI API: usage.prompt_tokens_details.cached_tokens
      - Generic: usage.cached_tokens or usage.cache_read_tokens

    Dedup: pi emits the same usage object on message_start (a zero/pending
    stub), message_end (the authoritative per-call final), and turn_end (a
    cumulative turn summary). Counting all three would triple-count. Only
    message_end events are summed; message_start and turn_end are skipped.
    For event streams with no message_end events at all, any event carrying a
    usage dict is counted once (fallback for non-pi providers).

    Returns total cached tokens if any usage event with cache details is found,
    or None if no provider usage cache metrics were present in the events.

    NOT the executor path any more. Both local transports now read usage off
    canonical events via ``adapters.executor_events.turn_usage``, which cannot
    reach a streaming update and so cannot reproduce the message_update
    over-count described in docs/proposals/executor-event-vocabulary.md §1.2.
    What still calls this is the evaluator's own pi run over `--mode json`
    stdout (runtime/verification/semantic/pi_runner.py), a different surface
    with no recorded fixture yet.
    """
    total_cached = 0
    found_any = False
    has_message_end = any(
        isinstance(evt, dict) and evt.get("type") == "message_end" for evt in events
    )

    for evt in events:
        if not isinstance(evt, dict):
            continue
        # Skip stub and cumulative events to avoid double/triple counting the
        # same per-call usage. message_start carries a pending (zero) stub and
        # turn_end repeats message_end's usage as a cumulative summary.
        if has_message_end and evt.get("type") in {"message_start", "turn_end"}:
            continue

        usage = _find_usage_dict(evt)
        if usage is None:
            continue

        cached = _read_cached_field(usage)
        if cached is not None:
            total_cached += cached
            found_any = True

    return total_cached if found_any else None


def _find_usage_dict(evt: dict) -> dict | None:
    """Locate the usage dict inside one event, preferring nested message.usage."""
    cache_keys = ("cacheRead", "cache_read_input_tokens", "cached_tokens", "cache_read_tokens", "prompt_tokens_details")
    # message.usage (pi openai-codex/xai shape) is the authoritative location.
    msg = evt.get("message")
    if isinstance(msg, dict):
        u = msg.get("usage")
        if isinstance(u, dict) and any(k in u for k in cache_keys):
            return u
    # top-level usage
    u = evt.get("usage")
    if isinstance(u, dict) and any(k in u for k in cache_keys):
        return u
    # nested response/data usage (other providers)
    for key in ("response", "data"):
        val = evt.get(key)
        if isinstance(val, dict):
            su = val.get("usage")
            if isinstance(su, dict) and any(k in su for k in cache_keys):
                return su
    # event itself carries a cache field directly (generic shape)
    if any(k in evt for k in cache_keys):
        return evt
    return None


def _read_cached_field(usage: dict) -> int | None:
    """Read a cached-token count from a usage dict across provider shapes."""
    # Pi / openai-codex / xai (camelCase, verified live).
    cr = usage.get("cacheRead")
    if cr is not None:
        return int(cr)
    # Anthropic / OpenRouter.
    if "cache_read_input_tokens" in usage and usage["cache_read_input_tokens"] is not None:
        return int(usage["cache_read_input_tokens"])
    # OpenAI standard.
    ptd = usage.get("prompt_tokens_details")
    if isinstance(ptd, dict) and ptd.get("cached_tokens") is not None:
        return int(ptd["cached_tokens"])
    # Generic fallbacks.
    for k in ("cached_tokens", "cache_read_tokens"):
        if k in usage and usage[k] is not None:
            return int(usage[k])
    return None


def prompt_cache_report(
    tp: TurnPrompt,
    *,
    actual_cached_tokens: int | None = None,
) -> PromptCacheReport:
    """Build the cache report for one turn — two separate views, never blended.

    ``actual_cached_tokens`` (when supplied) is the provider's authoritative
    measurement across the whole prompt; it is stored as-is and NOT compared
    against the structural zones below. ``potential_reuse_tokens`` is the
    GDDP-authored stable prefix (protocol + project + node) — a structural
    property of what GDDP contributes, not a cache-hit denominator.
    """
    volatility_invariant(tp)
    proto = tp.zone_token_estimate("protocol")
    proj = tp.zone_token_estimate("project")
    node = tp.zone_token_estimate("node")
    attempt = tp.zone_token_estimate("attempt")
    total = proto + proj + node + attempt
    potential = proto + proj + node
    potential_ratio = potential / total if total else 0.0
    return PromptCacheReport(
        total_input_tokens=total,
        protocol_tokens=proto,
        project_tokens=proj,
        node_tokens=node,
        attempt_tokens=attempt,
        potential_reuse_tokens=potential,
        potential_reuse_ratio=potential_ratio,
        actual_cached_tokens=actual_cached_tokens,
    )
