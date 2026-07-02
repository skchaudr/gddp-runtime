from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.runtime.verification.orchestrator import verify
from scripts.runtime.verification.receipt_sink import write_receipt
from scripts.runtime.verification.semantic.agent import LLMResponse, ToolCall
from scripts.runtime.verification.semantic.tools import SemanticToolbox


class OfflineFinalizingRunner:
    """Network-free runner for real CLI receipts when no LLM is configured.

    It uses the prompt context produced by the semantic agent and finalizes every
    unresolved deterministic criterion as indeterminate. This keeps the receipt
    honest: the verifier ran, but semantic meaning was not resolved by a model.
    """

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        context = _extract_prompt_context(messages)
        criteria = context.get("deterministic_result", {}).get("criteria", [])
        judgments = []
        for criterion in criteria:
            if criterion.get("status") != "indeterminate":
                continue
            judgments.append(
                {
                    "criterion_id": criterion.get("id", ""),
                    "judgment": "indeterminate",
                    "confidence": min(float(criterion.get("confidence", 0.2)), 0.2),
                    "evidence": criterion.get("evidence", []),
                    "reasoning": (
                        "Offline verifier CLI could not resolve this criterion semantically; "
                        "a live semantic runner or human review is required."
                    ),
                }
            )
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="offline-submit-verdict",
                    name="submit_verdict",
                    args={
                        "judgments": judgments,
                        "overall_reasoning": (
                            "Offline verifier CLI finalized unresolved semantic criteria "
                            "as indeterminate without network or graph mutation."
                        ),
                        "risks": "Semantic verification was not completed by a live model.",
                        "followup_candidates": None,
                        "budget_exhausted": True,
                    },
                )
            ],
            finish_reason="tool_use",
        )


def _extract_prompt_context(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        start = content.find("{")
        if start == -1:
            continue
        try:
            return json.loads(content[start:])
        except json.JSONDecodeError:
            continue
    return {}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GDDP verifier and write a receipt.")
    parser.add_argument("--node-yaml", required=True, type=Path, help="Path to the node YAML file.")
    parser.add_argument("--project-yaml", required=True, type=Path, help="Path to the project YAML file.")
    parser.add_argument("--repo", required=True, type=Path, help="Path to the source repo to verify.")
    parser.add_argument("--config-root", type=Path, help="Path to gddp-config root for project_policy probes.")
    parser.add_argument("--receipt-dir", type=Path, help="Directory where the JSON receipt should be written.")
    parser.add_argument("--shape-profile", type=Path, help="Optional shape profile YAML path.")
    parser.add_argument(
        "--semantic-mode",
        choices=["offline"],
        default="offline",
        help="Semantic runner mode. offline is network-free and marks unresolved criteria indeterminate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    node_yaml = _load_yaml(args.node_yaml)
    project_yaml = _load_yaml(args.project_yaml)
    shape_profile = _load_yaml(args.shape_profile) if args.shape_profile else None
    repo = args.repo.resolve()

    receipt = verify(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=repo,
        runner=OfflineFinalizingRunner(),
        toolbox=SemanticToolbox(repo),
        shape_profile=shape_profile,
        config_root=args.config_root.resolve() if args.config_root else None,
    )
    path = write_receipt(receipt, receipt.project_id, base=args.receipt_dir)
    print(
        json.dumps(
            {
                "receipt_path": str(path),
                "verdict": receipt.verdict.value,
                "criteria_confidence": receipt.criteria_confidence,
                "completeness_status": receipt.completeness_status,
                "required_next_action": receipt.required_next_action,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
