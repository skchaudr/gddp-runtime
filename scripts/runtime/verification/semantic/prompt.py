from __future__ import annotations

import json
from typing import Any

from scripts.prompt_topology import TurnPrompt


SYSTEM_PROMPT = """You are the GDDP semantic verification investigator.

Use only the provided read-only tools. Investigate acceptance criteria against
the repo evidence. Do not choose the final project verdict. When finished, call
submit_verdict with arguments matching SemanticOutput:
{
  "judgments": [
    {
      "criterion_id": "...",
      "judgment": "judged_pass | judged_fail | indeterminate",
      "confidence": 0.0,
      "evidence": ["file:line or tool evidence"],
      "reasoning": "why this judgment follows"
    }
  ],
  "overall_reasoning": "...",
  "risks": null,
  "followup_candidates": null,
  "budget_exhausted": false
}
"""


# Prefix caching discounts a byte-identical prompt prefix. The evaluator prompt
# is a cache topology with four monotonically-more-volatile zones:
#   protocol  = SYSTEM_PROMPT (nearly immutable, shared by every evaluation)
#   project   = framing + stable canonical pointers + graph (stable across
#               the whole frontier — shared by every node of the same graph)
#   node      = the node under evaluation (stable across retries of that node)
#   attempt   = deterministic_result + shape_profile + per-node neighbor
#               pointers (varies every run)
# A single json.dumps(..., sort_keys=True) over the merged context dict would
# alphabetize top-level keys and hoist "deterministic_result" (volatile) ahead
# of "graph" (stable), busting the cached prefix for every evaluation. Each
# zone is internally byte-stable (sort_keys=True within the zone); only the
# ZONE ORDER is load-bearing. Do not merge the zones back into one dump.
_STABLE_FRAMING = (
    "Investigate the following GDDP verification context. Focus on "
    "criteria that deterministic checks could not resolve.\n\n"
)


def _zone(label: str, value: Any) -> str:
    """One byte-stable labeled JSON zone. None renders as the JSON null."""
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"{label}: {body}"


def build_turn_prompt(
    node: dict[str, Any],
    graph: dict[str, Any],
    deterministic_result: Any,
    shape_profile: dict[str, Any] | None = None,
    *,
    stable_prefix_extra: str = "",
    volatile_tail_extra: str = "",
) -> TurnPrompt:
    """Build the four-zone TurnPrompt for one evaluation.

    Protocol (SYSTEM_PROMPT) is carried separately in the system message by
    ``build_prompt_messages``; here it is left empty so the user-message text
    is exactly project + node + attempt.
    """
    project = _STABLE_FRAMING + stable_prefix_extra + _zone("graph", graph)
    node_zone = _zone("node", node)
    attempt_zone = _zone("deterministic_result", deterministic_result) + "\n" + _zone(
        "shape_profile", shape_profile
    )
    if volatile_tail_extra:
        attempt_zone = attempt_zone + "\n" + volatile_tail_extra
    return TurnPrompt(
        protocol="",  # SYSTEM_PROMPT lives in the system message
        project=project,
        node=node_zone,
        attempt=attempt_zone,
    )


def build_prompt_messages(
    node: dict[str, Any],
    graph: dict[str, Any],
    deterministic_result: Any,
    shape_profile: dict[str, Any] | None = None,
    *,
    stable_prefix_extra: str = "",
    volatile_tail_extra: str = "",
) -> list[dict[str, Any]]:
    tp = build_turn_prompt(
        node=node,
        graph=graph,
        deterministic_result=deterministic_result,
        shape_profile=shape_profile,
        stable_prefix_extra=stable_prefix_extra,
        volatile_tail_extra=volatile_tail_extra,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": tp.assemble()},
    ]
