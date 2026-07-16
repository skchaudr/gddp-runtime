from __future__ import annotations

import os
from pathlib import Path


def receipt_path(
    project_id: str,
    node_id: str,
    base: Path | None = None,
    job_id: str | None = None,
    attempt: int | None = None,
) -> Path:
    """Return the receipt file path.

    When job_id and attempt are provided, the path preserves each job attempt:
      <base>/<project>/<node>/<job_id>-attempt<N>.json

    The job-id-only and node-only forms remain for existing callers.
    """
    root = base or Path(os.environ.get("GDDP_RECEIPTS_DIR", Path.home() / ".gddp" / "receipts"))
    if job_id:
        if attempt is not None:
            return root / project_id / node_id / f"{job_id}-attempt{attempt}.json"
        return root / project_id / node_id / f"{job_id}.json"
    return root / project_id / f"{node_id}.json"


def write_receipt(
    receipt,
    project_id: str,
    base: Path | None = None,
    job_id: str | None = None,
    attempt: int | None = None,
) -> Path:
    path = receipt_path(
        project_id, receipt.node_id, base=base, job_id=job_id, attempt=attempt
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return path


def receipt_exists(
    project_id: str,
    node_id: str,
    base: Path | None = None,
    job_id: str | None = None,
    attempt: int | None = None,
) -> bool:
    return receipt_path(
        project_id, node_id, base=base, job_id=job_id, attempt=attempt
    ).exists()
