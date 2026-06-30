from __future__ import annotations

import os
from pathlib import Path


def receipt_path(project_id: str, node_id: str, base: Path | None = None) -> Path:
    root = base or Path(os.environ.get("GDDP_RECEIPTS_DIR", Path.home() / ".gddp" / "receipts"))
    return root / project_id / f"{node_id}.json"


def write_receipt(receipt, project_id: str, base: Path | None = None) -> Path:
    path = receipt_path(project_id, receipt.node_id, base=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return path


def receipt_exists(project_id: str, node_id: str, base: Path | None = None) -> bool:
    return receipt_path(project_id, node_id, base=base).exists()
