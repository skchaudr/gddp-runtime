"""Atomic completion identity comparison for executor-session returns."""

from __future__ import annotations

import sqlite3
import string
from dataclasses import dataclass
from typing import Literal

from .state_recorder import mark_jobs_awaiting_review, now


@dataclass(frozen=True)
class CompletionDecision:
    """Result of submitting one normalized executor completion."""

    action: Literal["proceed", "stored", "duplicate", "quarantined"]
    existing_session_db_id: str | None = None
    result_commit_sha: str | None = None
    evidence_manifest_path: str | None = None
    quarantine_reason: str | None = None
    quarantined_session_db_ids: tuple[str, ...] = ()


def submit_completion(
    con: sqlite3.Connection,
    *,
    session_db_id: str,
    completion_id: str | None,
    completion_digest_sha256: str | None,
    result_commit_sha: str | None,
    evidence_manifest_path: str | None,
) -> CompletionDecision:
    """Compare and persist one completion under a SQLite write lock.

    A null completion identity remains backward-compatible and makes no
    records-discipline changes. Non-null identities require a normalized
    SHA-256 digest. Exact replays return the first stored result without a
    write. Digest conflicts preserve both envelopes on their session rows and
    route every involved job to ``awaiting_review``.
    """

    if completion_id is None:
        return CompletionDecision(action="proceed")
    normalized_id = completion_id.strip()
    if not normalized_id:
        raise ValueError("completion_id cannot be empty")
    normalized_digest = _normalize_digest(completion_digest_sha256)
    if con.in_transaction:
        raise RuntimeError("completion comparison requires a transaction boundary")

    con.execute("BEGIN IMMEDIATE")
    try:
        incoming = con.execute(
            """
            SELECT session_db_id, job_id, completion_id,
                   completion_digest_sha256, result_commit_sha,
                   evidence_manifest_path
              FROM executor_sessions
             WHERE session_db_id = ?
            """,
            (session_db_id,),
        ).fetchone()
        if incoming is None:
            raise ValueError(f"executor session not found: {session_db_id}")

        existing = con.execute(
            """
            SELECT session_db_id, job_id, completion_id,
                   completion_digest_sha256, result_commit_sha,
                   evidence_manifest_path
              FROM executor_sessions
             WHERE completion_id = ?
            """,
            (normalized_id,),
        ).fetchone()

        if existing is None:
            con.execute(
                """
                UPDATE executor_sessions
                   SET completion_id = ?,
                       completion_digest_sha256 = ?,
                       result_commit_sha = COALESCE(?, result_commit_sha),
                       evidence_manifest_path =
                           COALESCE(?, evidence_manifest_path),
                       updated_at = ?
                 WHERE session_db_id = ?
                """,
                (
                    normalized_id,
                    normalized_digest,
                    result_commit_sha,
                    evidence_manifest_path,
                    now(),
                    session_db_id,
                ),
            )
            con.commit()
            return CompletionDecision(
                action="stored",
                existing_session_db_id=session_db_id,
                result_commit_sha=result_commit_sha,
                evidence_manifest_path=evidence_manifest_path,
            )

        existing_digest = _normalize_digest(existing["completion_digest_sha256"])
        if existing_digest == normalized_digest:
            if str(existing["session_db_id"]) != str(incoming["session_db_id"]):
                con.execute(
                    """
                    UPDATE executor_sessions
                       SET state = 'completion_duplicate',
                           completion_digest_sha256 = ?,
                           result_commit_sha = ?,
                           evidence_manifest_path = ?,
                           updated_at = ?
                     WHERE session_db_id = ?
                    """,
                    (
                        existing_digest,
                        existing["result_commit_sha"],
                        existing["evidence_manifest_path"],
                        now(),
                        session_db_id,
                    ),
                )
            con.commit()
            return CompletionDecision(
                action="duplicate",
                existing_session_db_id=str(existing["session_db_id"]),
                result_commit_sha=existing["result_commit_sha"],
                evidence_manifest_path=existing["evidence_manifest_path"],
            )

        reason = _conflict_reason(
            completion_id=normalized_id,
            existing=existing,
            existing_digest=existing_digest,
            incoming=incoming,
            incoming_digest=normalized_digest,
            incoming_result_commit_sha=result_commit_sha,
            incoming_evidence_manifest_path=evidence_manifest_path,
        )
        involved_session_ids = {
            str(existing["session_db_id"]),
            str(incoming["session_db_id"]),
        }
        for involved_session_id in involved_session_ids:
            is_incoming_only = (
                involved_session_id == str(incoming["session_db_id"])
                and involved_session_id != str(existing["session_db_id"])
            )
            if is_incoming_only:
                con.execute(
                    """
                    UPDATE executor_sessions
                       SET state = 'completion_quarantined',
                           completion_digest_sha256 = ?,
                           completion_quarantine_reason = ?,
                           result_commit_sha = COALESCE(?, result_commit_sha),
                           evidence_manifest_path =
                               COALESCE(?, evidence_manifest_path),
                           error = ?,
                           updated_at = ?
                     WHERE session_db_id = ?
                    """,
                    (
                        normalized_digest,
                        reason,
                        result_commit_sha,
                        evidence_manifest_path,
                        reason,
                        now(),
                        involved_session_id,
                    ),
                )
            else:
                con.execute(
                    """
                    UPDATE executor_sessions
                       SET state = 'completion_quarantined',
                           completion_quarantine_reason = ?,
                           error = ?,
                           updated_at = ?
                     WHERE session_db_id = ?
                    """,
                    (reason, reason, now(), involved_session_id),
                )

        job_ids = {
            str(existing["job_id"]),
            str(incoming["job_id"]),
        }
        mark_jobs_awaiting_review(con, job_ids)
        con.commit()
        return CompletionDecision(
            action="quarantined",
            existing_session_db_id=str(existing["session_db_id"]),
            result_commit_sha=existing["result_commit_sha"],
            evidence_manifest_path=existing["evidence_manifest_path"],
            quarantine_reason=reason,
            quarantined_session_db_ids=tuple(sorted(involved_session_ids)),
        )
    except Exception:
        con.rollback()
        raise


def _normalize_digest(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("non-null completion_id requires a SHA-256 digest")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in string.hexdigits for character in normalized
    ):
        raise ValueError("completion_digest_sha256 must be 64 hexadecimal characters")
    return normalized


def _conflict_reason(
    *,
    completion_id: str,
    existing,
    existing_digest: str,
    incoming,
    incoming_digest: str,
    incoming_result_commit_sha: str | None,
    incoming_evidence_manifest_path: str | None,
) -> str:
    return (
        "conflicting completion_id "
        f"{completion_id!r}: existing(session_db_id="
        f"{existing['session_db_id']!r}, digest={existing_digest!r}, "
        f"result_commit_sha={existing['result_commit_sha']!r}, "
        f"evidence_manifest_path={existing['evidence_manifest_path']!r}); "
        f"incoming(session_db_id={incoming['session_db_id']!r}, "
        f"digest={incoming_digest!r}, "
        f"result_commit_sha={incoming_result_commit_sha!r}, "
        f"evidence_manifest_path={incoming_evidence_manifest_path!r})"
    )
