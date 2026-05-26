"""
escalate.py — Flag blocked or unexpected state.

Writes an escalation record to SQLite and logs to stdout (visible via journalctl).
v0: no Telegram/WhatsApp — just SQLite + logs.
"""

import json
import logging
from typing import Optional

from ..schema import EscalateResult

logger = logging.getLogger("decision_loop.escalate")


def run(
    reason: str,
    node_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> EscalateResult:
    """
    Create an escalation result. The engine handles writing it to SQLite.
    """
    result = EscalateResult(
        action="escalate",
        node_id=node_id,
        project_id=project_id,
        reason=reason,
        ok=True,
    )

    # Log so journalctl catches it
    logger.warning(
        "ESCALATION: %s | node=%s | project=%s",
        reason,
        node_id or "none",
        project_id or "none",
    )

    return result
