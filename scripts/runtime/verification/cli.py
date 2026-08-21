from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.runtime.verification.orchestrator import verify
from scripts.runtime.verification.receipt_sink import write_receipt
from scripts.runtime.verification.semantic.integrity_runner import IntegrityHarnessRunner
from scripts.runtime.verification.semantic.pi_environment import has_chatgpt_oauth
from scripts.runtime.verification.semantic.pi_runner import PiHarnessRunner


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
        choices=["offline", "live"],
        default="offline",
        help=(
            "Semantic runner mode. offline is network-free (deterministic floor only); "
            "live drives the pi coding agent as the semantic investigator."
        ),
    )
    parser.add_argument(
        "--semantic-provider",
        choices=["auto", "deepseek", "chatgpt", "glm"],
        default=os.environ.get("GDDP_SEMANTIC_PROVIDER", "auto"),
        help=(
            "Evaluator provider. Pi allows DeepSeek or ChatGPT OAuth; GLM is rejected."
        ),
    )
    parser.add_argument(
        "--semantic-harness",
        choices=["auto", "pi"],
        default=os.environ.get("GDDP_SEMANTIC_HARNESS", "pi"),
        help=(
            "Agent harness for the semantic phase. Pi is the only live harness; "
            "'auto' resolves to pi. Kept for flag compatibility with the bridge."
        ),
    )
    parser.add_argument(
        "--semantic-thinking",
        default=os.environ.get("GDDP_SEMANTIC_THINKING", "medium"),
        help="Pi thinking level (off|minimal|low|medium|high|xhigh) when --semantic-harness pi.",
    )
    parser.add_argument(
        "--semantic-pi-model",
        default=os.environ.get("GDDP_SEMANTIC_PI_MODEL", ""),
        help="Pi model id (e.g. deepseek-v4-flash) for --semantic-harness pi. Defaults to provider default.",
    )
    parser.add_argument(
        "--integrity",
        choices=["on", "off"],
        default="off",
        help=(
            "Enable lane 2 integrity review (fresh-eyes drift review). "
            "Default off; the bridge flips this on later. When on, the integrity "
            "harness runs after criteria adjudication on every verification, "
            "including row-12 deterministic clean passes."
        ),
    )
    # Phase 1 provenance: pin the exact change being judged.
    parser.add_argument("--merge-commit-sha", default=None, help="Merge commit SHA from the webhook payload.")
    parser.add_argument("--base", dest="expected_base_commit_sha", default=None, help="Dispatch-recorded base commit the subject was built on; enables subject-diff evidence.")
    parser.add_argument("--pr-ref", default=None, help="PR number or URL.")
    parser.add_argument("--job-id", default=None, help="SQLite job_id for per-attempt receipt path.")
    parser.add_argument("--attempt", type=int, default=None, help="Persisted zero-based jobs.attempt value.")
    parser.add_argument(
        "--execution-attempt-id",
        default=None,
        help="Optional executor-neutral attempt identity for receipt provenance.",
    )
    parser.add_argument(
        "--evidence-manifest-sha256",
        default=None,
        help="Optional SHA-256 digest of the collected per-node evidence manifest.",
    )
    parser.add_argument(
        "--mission-receipt-id",
        default=None,
        help="Optional stable mission completion/receipt identity.",
    )
    return parser


def _offline_semantic_skip(**_kwargs):
    """Offline-mode semantic stub: the lane is intentionally not run.

    The orchestrator demands a harness whenever deterministic criteria come
    back indeterminate. Offline (deterministic-only) verification answers
    None so decide() sees no semantic input — without constructing any
    agent infrastructure (PiHarnessRunner, provider keys, PI_CODING_AGENT_DIR).
    """
    return None


def _pi_provider(args) -> str:
    """Map the gddp --semantic-provider name to a pi provider name."""
    requested = args.semantic_provider
    if requested == "deepseek":
        return "deepseek"
    if requested == "chatgpt":
        return "openai-codex"
    if requested == "glm":
        raise RuntimeError(
            "evaluator Pi does not allow GLM; use deepseek or chatgpt (openai-codex OAuth)"
        )
    # auto: prefer the explicit DeepSeek key, then ChatGPT OAuth.
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if has_chatgpt_oauth():
        return "openai-codex"
    raise RuntimeError(
        "--semantic-harness pi needs DEEPSEEK_API_KEY or configured openai-codex OAuth"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    node_yaml = _load_yaml(args.node_yaml)
    project_yaml = _load_yaml(args.project_yaml)
    shape_profile = _load_yaml(args.shape_profile) if args.shape_profile else None
    repo = args.repo.resolve()

    semantic_harness = None
    if args.semantic_mode == "offline":
        # Deterministic floor only — never construct agent infrastructure.
        semantic_harness = _offline_semantic_skip
    else:
        pi_runner = PiHarnessRunner(
            provider=_pi_provider(args),
            model=args.semantic_pi_model or None,
            thinking=args.semantic_thinking,
            config_root=args.config_root.resolve() if args.config_root else None,
        )
        semantic_harness = pi_runner.run

    integrity_harness = None
    if args.integrity == "on":
        integrity_pi_runner = IntegrityHarnessRunner(
            provider=_pi_provider(args),
            model=args.semantic_pi_model or None,
            thinking=args.semantic_thinking,
        )
        integrity_harness = integrity_pi_runner.run

    receipt = verify(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=repo,
        shape_profile=shape_profile,
        config_root=args.config_root.resolve() if args.config_root else None,
        semantic_harness=semantic_harness,
        integrity_harness=integrity_harness,
        merge_commit_sha=args.merge_commit_sha,
        expected_base_commit_sha=args.expected_base_commit_sha,
        pr_ref=args.pr_ref,
        job_id=args.job_id,
        execution_attempt_id=args.execution_attempt_id,
        evidence_manifest_sha256=args.evidence_manifest_sha256,
        mission_receipt_id=args.mission_receipt_id,
    )
    path = write_receipt(
        receipt,
        receipt.project_id,
        base=args.receipt_dir,
        job_id=args.job_id,
        attempt=args.attempt,
    )
    summary = {
        "receipt_path": str(path),
        "verdict": receipt.verdict.value,
        "criteria_confidence": receipt.criteria_confidence,
        "completeness_status": receipt.completeness_status,
        "required_next_action": receipt.required_next_action,
    }
    # Phase 1 provenance: surface in the summary so jobs_status.py can display it.
    if receipt.evaluated_tree_sha:
        summary["evaluated_tree_sha"] = receipt.evaluated_tree_sha
    if receipt.evaluated_commit_sha:
        summary["evaluated_commit_sha"] = receipt.evaluated_commit_sha
    if receipt.merge_commit_sha:
        summary["merge_commit_sha"] = receipt.merge_commit_sha
    if receipt.pr_ref:
        summary["pr_ref"] = receipt.pr_ref
    if receipt.execution_attempt_id:
        summary["execution_attempt_id"] = receipt.execution_attempt_id
    if receipt.evidence_manifest_sha256:
        summary["evidence_manifest_sha256"] = receipt.evidence_manifest_sha256
    if receipt.mission_receipt_id:
        summary["mission_receipt_id"] = receipt.mission_receipt_id
    # Summaries are operator-facing; raw coverage evidence remains in receipt.
    if receipt.context_coverage:
        criteria_coverage = receipt.context_coverage.criteria
        summary["context_coverage"] = {
            "criteria": (
                criteria_coverage
                if isinstance(criteria_coverage, str)
                else criteria_coverage.rating
            ),
            "integrity": receipt.context_coverage.integrity.rating,
            "overall": receipt.context_coverage.overall,
        }
    # Two-lane evaluation: include criteria_verdict and integrity when present
    # so the bridge and return_router can see both lanes.
    if receipt.criteria_verdict is not None:
        summary["criteria_verdict"] = receipt.criteria_verdict.value
    if receipt.integrity is not None:
        summary["integrity"] = {
            "verdict": receipt.integrity.verdict,
            "intent_preserved": receipt.integrity.intent_preserved,
            "graph_integrity_preserved": receipt.integrity.graph_integrity_preserved,
            "required_human_review": receipt.integrity.required_human_review,
            "confidence": receipt.integrity.confidence,
            "findings": [f.model_dump() for f in receipt.integrity.findings],
            "reasoning": receipt.integrity.reasoning,
            "lane_status": (
                receipt.integrity.lane_status.value
                if receipt.integrity.lane_status else None
            ),
            "harness_error": receipt.integrity.harness_error,
        }
        # Phase 3: include graph_observations when present.
        if receipt.integrity.graph_observations:
            summary["integrity"]["graph_observations"] = [
                o.model_dump() for o in receipt.integrity.graph_observations
            ]
        if receipt.integrity.graph_recommendations:
            summary["integrity"]["graph_recommendations"] = [
                r.model_dump() for r in receipt.integrity.graph_recommendations
            ]
    # Surface the criteria lane's free-text intelligence (risks, followups)
    # and the deterministic lane's human-review questions so they reach the
    # operator view instead of living only in the receipt file.
    if receipt.semantic is not None:
        if receipt.semantic.risks:
            summary["semantic_risks"] = receipt.semantic.risks
        if receipt.semantic.followup_candidates:
            summary["followup_candidates"] = receipt.semantic.followup_candidates
    if receipt.deterministic.human_review_questions:
        summary["human_review_questions"] = [
            {"criterion_id": q.criterion_id, "question": q.question}
            for q in receipt.deterministic.human_review_questions
        ]
    summary["lane_status"] = {
        "criteria": (
            receipt.semantic.lane_status.value if receipt.semantic and receipt.semantic.lane_status
            else "completed" if receipt.semantic else "not_run"
        ),
        "integrity": (
            receipt.integrity.lane_status.value if receipt.integrity and receipt.integrity.lane_status
            else "completed" if receipt.integrity else "not_run"
        ),
    }
    summary["harness_error"] = {
        "criteria": receipt.semantic.harness_error if receipt.semantic else None,
        "integrity": receipt.integrity.harness_error if receipt.integrity else None,
    }
    if receipt.evaluation_timing is not None:
        summary["evaluation_timing"] = receipt.evaluation_timing.model_dump()
    # Surface criteria-lane findings (non-pass judgments) so the return_router
    # can use them for retry decisions alongside integrity findings.
    criteria_findings = []
    if receipt.semantic:
        for j in receipt.semantic.judgments:
            if j.judgment != "judged_pass":
                criteria_findings.append({
                    "criterion_id": j.criterion_id,
                    "judgment": j.judgment,
                    "evidence": j.evidence,
                    "reasoning": j.reasoning,
                })
    if criteria_findings:
        summary["criteria_findings"] = criteria_findings
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
