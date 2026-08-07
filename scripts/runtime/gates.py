"""
gates.py — Per-node gate tokens for mission-mode execution.

A gate token is a tiny JSON file written into the target repo's .gddp/gates/
directory when a node passes evaluation and is marked provisional. A
mission-mode executor reads these tokens as an admission signal: feature N+1
may start only when .gddp/gates/<dep-node-id>.token exists.

Gates are evidence, not lifecycle. write_gate never blocks or raises into
the caller — a failed gate write leaves the node provisional (the operator
can still accept by hand) and logs a warning.

revocation: revoke_gate deletes a node's token so that dependents re-block.
This runs when a human rejects or defers a provisional node, restoring the
admission contract that a gate token means "this node's work is good."
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _gate_dir(repo_path: str | Path) -> Path:
    return Path(repo_path) / ".gddp" / "gates"


def _gate_path(repo_path: str | Path, node_id: str) -> Path:
    return _gate_dir(repo_path) / f"{node_id}.token"


def write_gate(
    repo_path: str | Path,
    node_id: str,
    verdict_receipt_path: str | None = None,
) -> Path | None:
    """Atomically write a gate token for *node_id* into *repo_path*.

    Returns the token path on success, ``None`` on failure (never raises).
    The JSON content carries the node id, a SHA-256 of the verdict receipt
    (when a path is given), the receipt path, and an ISO-8601 timestamp.

    Uses a unique same-directory tempfile per call so concurrent writers
    cannot collide on a shared ``<node>.tmp`` inode.
    """
    try:
        gdir = _gate_dir(repo_path)
        gdir.mkdir(parents=True, exist_ok=True)
        gpath = _gate_path(repo_path, node_id)

        content: dict[str, str] = {
            "node_id": node_id,
            "issued_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds"),
        }
        if verdict_receipt_path:
            p = Path(verdict_receipt_path)
            if p.exists():
                content["verdict_receipt_sha256"] = hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                content["receipt_path"] = str(p)
            else:
                content["receipt_path"] = str(p)
                content["verdict_receipt_sha256"] = ""

        # Atomic write: unique tempfile in same dir, then os.replace.
        fd, tmp = tempfile.mkstemp(
            dir=str(gdir), prefix=f"{node_id}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(content, indent=2, sort_keys=True))
            os.replace(tmp, gpath)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return gpath
    except Exception as exc:
        print(f"  → gate write WARNING (non-fatal): {exc}")
        return None


def revoke_gate(repo_path: str | Path, node_id: str) -> bool:
    """Delete a node's gate token so dependents re-block.

    Returns True if the token was deleted, False if it was already absent.
    Never raises — a failed revoke leaves the token in place (conservative:
    it over-admits rather than under-admitting, and the operator can clean up).
    """
    gpath = _gate_path(repo_path, node_id)
    if not gpath.exists():
        return False
    try:
        gpath.unlink()
        return True
    except Exception as exc:
        print(f"  → gate revoke WARNING (non-fatal): {exc}")
        return False


def read_gate(repo_path: str | Path, node_id: str) -> dict | None:
    """Return the parsed gate token, or ``None`` if absent / corrupt / invalid.

    A valid gate must be a JSON object with a ``node_id`` field matching
    *node_id*. An arbitrary ``{}`` does not satisfy a dependency.
    """
    gpath = _gate_path(repo_path, node_id)
    if not gpath.exists():
        return None
    try:
        data = json.loads(gpath.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("node_id") != node_id:
        return None
    return data


def gate_satisfied(repo_path: str | Path, depends_on: list[str]) -> bool:
    """True when every dependency in *depends_on* has a valid gate token.

    An empty dependency list is trivially satisfied (root nodes).
    """
    return all(read_gate(repo_path, dep) is not None for dep in depends_on)
