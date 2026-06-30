from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """You are the GDDP semantic verification investigator.

Use only the provided read-only tools. Investigate acceptance criteria against
the repo evidence. Do not choose the final project verdict. Return only JSON
matching SemanticOutput:
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


def build_prompt_messages(
    node: dict[str, Any],
    graph: dict[str, Any],
    deterministic_result: Any,
    shape_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = {
        "node": node,
        "graph": graph,
        "deterministic_result": deterministic_result,
        "shape_profile": shape_profile,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Investigate the following GDDP verification context. Focus on "
                "criteria that deterministic checks could not resolve.\n\n"
                f"{json.dumps(context, indent=2, sort_keys=True, default=str)}"
            ),
        },
    ]
