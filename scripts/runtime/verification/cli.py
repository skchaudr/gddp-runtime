from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.runtime.verification.orchestrator import verify
from scripts.runtime.verification.receipt_sink import write_receipt
from scripts.runtime.verification.semantic.agent import LLMResponse, OpenAICompatibleRunner, ToolCall
from scripts.runtime.verification.semantic.integrity_runner import IntegrityHarnessRunner
from scripts.runtime.verification.semantic.pi_environment import has_chatgpt_oauth
from scripts.runtime.verification.semantic.pi_runner import PiHarnessRunner
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
        choices=["offline", "live"],
        default="offline",
        help=(
            "Semantic runner mode. offline is network-free and marks unresolved criteria "
            "indeterminate; live uses an OpenAI-compatible DeepSeek or GLM endpoint."
        ),
    )
    parser.add_argument(
        "--semantic-provider",
        choices=["auto", "deepseek", "chatgpt", "glm"],
        default=os.environ.get("GDDP_SEMANTIC_PROVIDER", "auto"),
        help=(
            "Evaluator provider. Pi allows DeepSeek or ChatGPT OAuth; "
            "the legacy runner also accepts GLM."
        ),
    )
    parser.add_argument(
        "--semantic-max-turns",
        type=int,
        default=_env_int("GDDP_SEMANTIC_MAX_TURNS", 15),
        help="Maximum live semantic agent turns before finalization.",
    )
    parser.add_argument(
        "--semantic-max-tool-calls",
        type=int,
        default=_env_int("GDDP_SEMANTIC_MAX_TOOL_CALLS", 40),
        help="Maximum semantic evidence tool calls.",
    )
    parser.add_argument(
        "--semantic-max-tokens",
        type=int,
        default=None,
        help="Estimated total semantic transcript token budget.",
    )
    parser.add_argument(
        "--semantic-provider-max-tokens",
        type=int,
        default=_env_int("GDDP_SEMANTIC_PROVIDER_MAX_TOKENS", 4096),
        help="Maximum tokens requested from the live model per response.",
    )
    parser.add_argument(
        "--semantic-max-tool-result-chars",
        type=int,
        default=_env_int("GDDP_SEMANTIC_MAX_TOOL_RESULT_CHARS", 50_000),
        help="Maximum serialized characters from one semantic evidence tool result.",
    )
    parser.add_argument(
        "--semantic-harness",
        choices=["auto", "pi", "runner"],
        default=os.environ.get("GDDP_SEMANTIC_HARNESS", "auto"),
        help=(
            "Agent harness for the semantic phase. 'pi' drives the pi coding agent "
            "(live, streaming, visible, read-only evidence tools); 'runner' uses the "
            "built-in OpenAI-compatible loop; 'auto' currently resolves to 'runner' "
            "(opt in to pi explicitly)."
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
    return parser


LIVE_PROVIDER_CONFIG = {
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
    "glm": {
        "api_key_env": "GLM_API_KEY",
        "base_url_env": "GLM_BASE_URL",
        "model_env": "GLM_MODEL",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
    },
}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _build_runner(args) -> OfflineFinalizingRunner | OpenAICompatibleRunner:
    if args.semantic_mode == "offline":
        return OfflineFinalizingRunner()

    provider = _select_live_provider(args.semantic_provider)
    config = LIVE_PROVIDER_CONFIG[provider]
    api_key = os.environ.get(config["api_key_env"], "")
    if not api_key:
        raise RuntimeError(f"{config['api_key_env']} is required for --semantic-mode live --semantic-provider {provider}")
    return OpenAICompatibleRunner(
        api_key=api_key,
        base_url=os.environ.get(config["base_url_env"], config["default_base_url"]),
        model=os.environ.get(config["model_env"], config["default_model"]),
        max_tokens=args.semantic_provider_max_tokens,
    )


def _select_live_provider(requested: str) -> str:
    if requested != "auto":
        return requested
    for provider in ("deepseek", "glm"):
        config = LIVE_PROVIDER_CONFIG[provider]
        if os.environ.get(config["api_key_env"]):
            return provider
    required = ", ".join(config["api_key_env"] for config in LIVE_PROVIDER_CONFIG.values())
    raise RuntimeError(f"--semantic-mode live requires one of these env vars: {required}")


def _offline_semantic_skip(**_kwargs):
    """Offline-mode semantic stub: the lane is intentionally not run.

    The orchestrator demands a harness whenever deterministic criteria come
    back indeterminate. Offline (deterministic-only) verification answers
    None so decide() sees no semantic input — without constructing any
    agent infrastructure (PiHarnessRunner, provider keys, PI_CODING_AGENT_DIR).
    """
    return None


def _resolve_harness(args) -> str:
    if args.semantic_harness == "pi":
        return "pi"
    if args.semantic_harness == "runner":
        return "runner"
    # auto: keep the built-in runner as the default; opt in with --semantic-harness pi.
    return "runner"


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

    harness_choice = _resolve_harness(args)
    # The Pi harness owns its model loop. ``runner`` remains in the verifier
    # signature for legacy callers but is not used when Pi is selected.
    runner = OfflineFinalizingRunner() if harness_choice == "pi" else _build_runner(args)
    semantic_max_tokens = args.semantic_max_tokens
    if semantic_max_tokens is None:
        semantic_max_tokens = 96_000 if args.semantic_mode == "live" else 24_000

    semantic_harness = None
    if args.semantic_mode == "offline":
        # Deterministic floor only — never construct agent infrastructure.
        semantic_harness = _offline_semantic_skip
    elif harness_choice == "pi":
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
        runner=runner,
        toolbox=SemanticToolbox(
            repo,
            node_yaml_path=args.node_yaml.resolve(),
            project_yaml_path=args.project_yaml.resolve(),
        ),
        shape_profile=shape_profile,
        config_root=args.config_root.resolve() if args.config_root else None,
        semantic_agent_kwargs={
            "max_turns": args.semantic_max_turns,
            "max_tool_calls": args.semantic_max_tool_calls,
            "max_tokens": semantic_max_tokens,
            "max_tool_result_chars": args.semantic_max_tool_result_chars,
        },
        semantic_harness=semantic_harness,
        integrity_harness=integrity_harness,
        merge_commit_sha=args.merge_commit_sha,
        expected_base_commit_sha=args.expected_base_commit_sha,
        pr_ref=args.pr_ref,
        job_id=args.job_id,
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
