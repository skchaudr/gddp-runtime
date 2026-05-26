"""
accept_node.py — Propose a graph truth change by opening an evidence PR.

The decision loop never mutates graph truth directly. When review_pr passes,
this power assembles the evidence packet and opens a PR against gddp-config
proposing to mark the node complete. A human merges, or doesn't.
"""

import logging
from typing import Any, Dict

from ...graph_updater import open_evidence_pr
from ..context_reader import DecisionContext
from ..schema import AcceptResult, EscalateResult, EvidencePacket

logger = logging.getLogger("decision_loop.accept_node")


def run(
    ctx: DecisionContext,
    node_id: str,
    source_pr_number: int,
    source_pr_url: str,
    review_evidence: Dict[str, Any],
) -> AcceptResult | EscalateResult:
    """
    Assemble evidence packet and open a PR against gddp-config.

    Args:
        ctx: The current decision loop context
        node_id: The node being accepted
        source_pr_number: The Jules PR that passed review
        source_pr_url: URL of the source PR
        review_evidence: Structured evidence from review_pr (acceptance
            verdicts, scope check, test status)

    Returns:
        AcceptResult on success (PR opened), EscalateResult on failure
    """
    project_id = ctx.project.project_id

    evidence = EvidencePacket(
        acceptance_check=review_evidence.get("acceptance_check", []),
        scope_verification=review_evidence.get("scope_verification", {}),
        test_status=review_evidence.get("test_status", {}),
        risks=review_evidence.get("risks"),
        followup_candidates=review_evidence.get("followup_candidates"),
    )

    result = open_evidence_pr(
        node_id=node_id,
        project_id=project_id,
        source_pr_number=source_pr_number,
        source_pr_url=source_pr_url,
        evidence=review_evidence,
    )

    if not result.get("ok"):
        logger.error(
            "Evidence PR failed for node=%s project=%s: %s",
            node_id, project_id, result.get("reason"),
        )
        return EscalateResult(
            action="escalate",
            node_id=node_id,
            project_id=project_id,
            reason=f"evidence_pr_failed: {result.get('reason')}",
            ok=True,
        )

    logger.info(
        "Evidence PR opened: %s (node=%s, source PR=#%d)",
        result["evidence_pr_url"], node_id, source_pr_number,
    )

    return AcceptResult(
        action="accept_node",
        node_id=node_id,
        project_id=project_id,
        source_pr_number=source_pr_number,
        source_pr_url=source_pr_url,
        evidence_pr_url=result["evidence_pr_url"],
        evidence=evidence,
        status="acceptance_proposed",
        ok=True,
    )
