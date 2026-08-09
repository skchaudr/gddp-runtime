"""Post-mission evidence slicing for Factory mission engagements."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mission_git_verify import verify_engagement_history, verify_git_result


@dataclass(frozen=True)
class CollectedNodeEvidence:
    """One node's manifest and reconciliation routing decision."""

    feature_id: str
    manifest_path: Path
    base_sha: str | None
    result_sha: str | None
    worker_session_id: str | None
    completion_id: str | None
    completion_digest_sha256: str | None
    review_required: bool
    review_reason: str | None
    completion_quarantine_reason: str | None


def collect_mission_evidence(
    *,
    mission_dir: str | Path,
    output_dir: str | Path,
    engagement_id: str,
    result_ref: str,
    demanded_feature_ids: Sequence[str] | None = None,
    planned_feature_ids: Sequence[str] | None = None,
    receipts_path: str | Path | None = None,
    mission_outcome: str | None = None,
    mission_failure_reason: str | None = None,
    mission_process: Mapping[str, object] | None = None,
    worktree: Mapping[str, object] | None = None,
    git_verified: Mapping[str, Mapping[str, object]] | None = None,
    git_repo_path: str | Path | None = None,
    origin_remote: str | None = None,
    push_audit_path: str | Path | None = None,
) -> list[CollectedNodeEvidence]:
    """Read mission artifacts and write one exact-feature manifest per node.

    Factory files are cross-check evidence and may be absent or malformed.
    Missing or disagreeing evidence is represented explicitly and routes only
    the affected node to review.
    """

    mission_path = Path(mission_dir).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    state = _read_json_object(mission_path / "state.json")
    mission_id = _string(state.get("missionId")) if state else None
    observed_ids = _read_feature_ids(mission_path / "features.json")
    feature_ids = (
        tuple(str(feature_id) for feature_id in demanded_feature_ids)
        if demanded_feature_ids is not None
        else observed_ids
    )

    handoffs = _read_handoffs(mission_path / "handoffs")
    progress = _read_progress(mission_path / "progress_log.jsonl")
    receipt_file = (
        Path(receipts_path).resolve()
        if receipts_path is not None
        else mission_path / "receipts.jsonl"
    )
    receipts = _read_receipts(receipt_file)
    first_receipt = next(
        (
            records[-1]
            for feature_id in feature_ids
            if (records := receipts.get(feature_id))
        ),
        None,
    )
    engagement_base = (
        _string(first_receipt.get("base"))
        if first_receipt is not None
        else None
    )
    engagement_history = (
        verify_engagement_history(
            git_repo_path,
            base_sha=engagement_base,
            engagement_branch=result_ref,
            demanded_node_ids=feature_ids,
        )
        if git_repo_path is not None and engagement_base is not None
        else None
    )
    push_records = (
        _read_jsonl(Path(push_audit_path).resolve())
        if push_audit_path is not None
        else None
    )
    expected_plan_ids = (
        tuple(str(feature_id) for feature_id in planned_feature_ids)
        if planned_feature_ids is not None
        else feature_ids
    )
    drift_reason = _feature_drift_reason(expected_plan_ids, observed_ids)

    collected: list[CollectedNodeEvidence] = []
    for feature_id in feature_ids:
        progress_evidence = _progress_evidence(progress.get(feature_id, ()))
        handoff = _select_handoff(
            handoffs.get(feature_id, ()),
            _string(progress_evidence.get("worker_session_id"))
            if progress_evidence
            else None,
        )
        receipt_records = receipts.get(feature_id, ())
        receipt = receipt_records[-1] if receipt_records else None
        worker_session_id = _worker_session_id(progress_evidence, handoff)
        base_sha = _string(receipt.get("base")) if receipt else None
        result_sha = _string(receipt.get("result")) if receipt else None
        selected_handoff = _select_handoff_fields(handoff)
        selected_progress = (
            {
                "started_at": progress_evidence["started_at"],
                "completed_at": progress_evidence["completed_at"],
                "outcome": progress_evidence["outcome"],
            }
            if progress_evidence is not None
            else None
        )
        selected_verification = (
            dict(git_verified[feature_id])
            if git_verified is not None and feature_id in git_verified
            else None
        )
        if (
            selected_verification is None
            and git_repo_path is not None
            and base_sha is not None
            and result_sha is not None
        ):
            selected_verification = verify_git_result(
                git_repo_path,
                base_sha=base_sha,
                result_sha=result_sha,
                engagement_branch=result_ref,
                origin_remote=origin_remote,
                expected_node_id=feature_id,
            ).to_manifest()
        cross_check = _cross_check(receipt, handoff, selected_verification)
        push_verification = (
            _push_verification(
                push_records,
                result_sha=result_sha,
                result_ref=result_ref,
                completed_at=(
                    _string(selected_progress.get("completed_at"))
                    if selected_progress is not None
                    else None
                ),
            )
            if push_records is not None
            else None
        )
        receipt_context_reasons = (
            _receipt_git_context_reasons(
                receipt,
                git_repo_path=git_repo_path,
                engagement_branch=result_ref,
            )
            if receipt is not None
            else []
        )
        protected_push_reasons = (
            _protected_branch_push_reasons(
                git_repo_path,
                result_sha=result_sha,
                engagement_branch=result_ref,
            )
            if git_repo_path is not None and result_sha is not None
            else []
        )
        quarantine_reasons = _quarantine_reasons(
            cross_check, selected_verification
        )
        quarantine_reasons.extend(receipt_context_reasons)
        quarantine_reasons.extend(protected_push_reasons)
        if (
            engagement_history is not None
            and not engagement_history.verified
            and engagement_history.completion_quarantine_reason
        ):
            quarantine_reasons.append(
                engagement_history.completion_quarantine_reason
            )
        missing = _missing_channels(
            receipt=receipt,
            handoff=selected_handoff,
            progress=selected_progress,
            mission_id=mission_id,
        )
        reasons = list(missing)
        if drift_reason:
            reasons.append(drift_reason)
        if _receipts_conflict(receipt_records):
            reasons.append("conflicting_receipts")
        if receipt is not None and _receipt_identity_conflicts(receipt):
            reasons.append("conflicting_receipt_feature_ids")
        reasons.extend(_disagreement_reasons(cross_check))
        reasons.extend(receipt_context_reasons)
        reasons.extend(protected_push_reasons)
        reasons.extend(quarantine_reasons)
        if (
            push_verification is not None
            and push_verification["verified"] is not True
        ):
            reasons.append("feature_push_not_verified")
            if result_sha is not None:
                quarantine_reasons.append(
                    f"feature commit {result_sha} lacks a successful individual "
                    f"push to origin/{result_ref}"
                )
        node_complete = _node_complete(
            receipt, selected_handoff, selected_progress, cross_check
        )
        handoff_state = (
            _string(selected_handoff.get("successState"))
            if selected_handoff is not None
            else None
        )
        if handoff_state is not None and handoff_state != "success":
            reasons.append(f"handoff_{handoff_state}")
        if mission_outcome in {"crashed", "failed"} and not node_complete:
            reasons.append(f"mission_{mission_outcome}")
            if worktree is not None and worktree.get("dirty") is True:
                reasons.append("dirty_worktree")
        reasons = list(dict.fromkeys(reasons))
        review_reason = ", ".join(reasons) if reasons else None
        completion_quarantine_reason = (
            "; ".join(dict.fromkeys(quarantine_reasons))
            if quarantine_reasons
            else None
        )
        completion_id = _completion_id(
            mission_id=mission_id,
            feature_id=feature_id,
            worker_session_id=worker_session_id,
        )
        completion_digest_sha256 = (
            _completion_digest(
                completion_id=completion_id,
                feature_id=feature_id,
                worker_session_id=worker_session_id,
                base_sha=base_sha,
                result_sha=result_sha,
                result_ref=result_ref,
                receipt=receipt,
                handoff=selected_handoff,
                progress=selected_progress,
            )
            if completion_id is not None
            else None
        )

        manifest = {
            "engagement_id": engagement_id,
            "mission_dir": str(mission_path),
            "mission_id": mission_id,
            "feature_id": feature_id,
            "worker_session_id": worker_session_id,
            "completion_id": completion_id,
            "completion_digest_sha256": completion_digest_sha256,
            "base_sha": base_sha,
            "result_sha": result_sha,
            "result_ref": result_ref,
            "receipt": dict(receipt) if receipt is not None else None,
            "handoff": selected_handoff,
            "progress": selected_progress,
            "git_verified": selected_verification,
            "engagement_history": (
                engagement_history.to_manifest()
                if engagement_history is not None
                else None
            ),
            "push_verification": push_verification,
            "cross_check": cross_check,
            "missing_channels": missing,
            "review_required": review_reason is not None,
            "review_reason": review_reason,
            "completion_quarantine_reason": completion_quarantine_reason,
            "mission_outcome": mission_outcome,
            "mission_failure_reason": mission_failure_reason,
            "mission_process": (
                dict(mission_process) if mission_process is not None else None
            ),
            "worktree": dict(worktree) if worktree is not None else None,
        }
        manifest_path = destination / _manifest_name(feature_id)
        _write_json(manifest_path, manifest)
        collected.append(
            CollectedNodeEvidence(
                feature_id=feature_id,
                manifest_path=manifest_path,
                base_sha=base_sha,
                result_sha=result_sha,
                worker_session_id=worker_session_id,
                completion_id=completion_id,
                completion_digest_sha256=completion_digest_sha256,
                review_required=review_reason is not None,
                review_reason=review_reason,
                completion_quarantine_reason=completion_quarantine_reason,
            )
        )
    return collected


def _read_feature_ids(path: Path) -> tuple[str, ...]:
    payload = _read_json_object(path)
    raw_features = payload.get("features") if payload else None
    if not isinstance(raw_features, list):
        return ()
    feature_ids: list[str] = []
    for raw_feature in raw_features:
        if not isinstance(raw_feature, dict):
            continue
        feature_id = _string(raw_feature.get("id"))
        if feature_id is not None:
            feature_ids.append(feature_id)
    return tuple(feature_ids)


def _read_handoffs(directory: Path) -> dict[str, list[dict[str, object]]]:
    handoffs: dict[str, list[dict[str, object]]] = {}
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError:
        return handoffs
    for path in paths:
        payload = _read_json_object(path)
        feature_id = _string(payload.get("featureId")) if payload else None
        if feature_id is not None:
            handoffs.setdefault(feature_id, []).append(payload)
    return handoffs


def _read_progress(path: Path) -> dict[str, list[dict[str, object]]]:
    by_feature: dict[str, list[dict[str, object]]] = {}
    for event in _read_jsonl(path):
        feature_id = _string(event.get("featureId"))
        if feature_id is not None:
            by_feature.setdefault(feature_id, []).append(event)
    return by_feature


def _read_receipts(path: Path) -> dict[str, list[dict[str, object]]]:
    receipts: dict[str, list[dict[str, object]]] = {}
    for receipt in _read_jsonl(path):
        feature_id = _string(receipt.get("node_id"))
        if feature_id is None:
            feature_id = _string(receipt.get("featureId"))
        if feature_id is not None:
            receipts.setdefault(feature_id, []).append(receipt)
    return receipts


def _push_verification(
    records: Sequence[Mapping[str, object]],
    *,
    result_sha: str | None,
    result_ref: str,
    completed_at: str | None,
) -> dict[str, object]:
    expected_argv = [
        "git",
        "push",
        "origin",
        f"HEAD:refs/heads/{result_ref}",
    ]
    expected_origin_ref = f"origin/{result_ref}"
    matching = [
        dict(record)
        for record in records
        if result_sha is not None and record.get("commit_sha") == result_sha
    ]
    successful = next(
        (
            record
            for record in reversed(matching)
            if record.get("allowed") is True
            and record.get("returncode") == 0
            and record.get("argv") == expected_argv
            and expected_origin_ref
            in (record.get("origin_containing_refs") or ())
            and _timestamp_at_or_before(
                _string(record.get("timestamp_utc")),
                completed_at,
            )
        ),
        None,
    )
    return {
        "verified": successful is not None,
        "expected_argv": expected_argv,
        "expected_origin_ref": expected_origin_ref,
        "feature_completed_at": completed_at,
        "matching_attempts": matching,
        "successful_attempt": successful,
    }


def _timestamp_at_or_before(
    observed: str | None,
    boundary: str | None,
) -> bool:
    if observed is None or boundary is None:
        return False
    try:
        observed_at = dt.datetime.fromisoformat(observed.replace("Z", "+00:00"))
        boundary_at = dt.datetime.fromisoformat(boundary.replace("Z", "+00:00"))
    except ValueError:
        return False
    return observed_at <= boundary_at


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _progress_evidence(
    events: Sequence[Mapping[str, object]],
) -> dict[str, str | None] | None:
    if not events:
        return None
    terminal = next(
        (
            event
            for event in reversed(events)
            if event.get("type") in {"worker_completed", "worker_failed"}
        ),
        None,
    )
    selected_worker = _string(terminal.get("workerSessionId")) if terminal else None
    if selected_worker is None:
        selected_worker = next(
            (
                worker
                for event in reversed(events)
                if (worker := _string(event.get("workerSessionId"))) is not None
            ),
            None,
        )
    worker_events = [
        event
        for event in events
        if selected_worker is None
        or _string(event.get("workerSessionId")) == selected_worker
    ]
    started = next(
        (
            _string(event.get("timestamp"))
            for event in worker_events
            if event.get("type") == "worker_started"
        ),
        None,
    )
    completed = _string(terminal.get("timestamp")) if terminal else None
    outcome = None
    if terminal is not None:
        outcome = _string(terminal.get("successState"))
        if outcome is None and terminal.get("type") == "worker_failed":
            outcome = "failure"
    return {
        "worker_session_id": selected_worker,
        "started_at": started,
        "completed_at": completed,
        "outcome": outcome,
    }


def _select_handoff_fields(
    handoff: Mapping[str, object] | None,
) -> dict[str, str | None] | None:
    if handoff is None:
        return None
    return {
        "commitId": _string(handoff.get("commitId")),
        "repoPath": _string(handoff.get("repoPath")),
        "successState": _string(handoff.get("successState")),
    }


def _select_handoff(
    handoffs: Sequence[Mapping[str, object]],
    worker_session_id: str | None,
) -> Mapping[str, object] | None:
    if not handoffs:
        return None
    if worker_session_id is not None:
        for handoff in reversed(handoffs):
            if _string(handoff.get("workerSessionId")) == worker_session_id:
                return handoff
    return handoffs[-1]


def _receipts_conflict(receipts: Sequence[Mapping[str, object]]) -> bool:
    boundaries = {
        (_string(receipt.get("base")), _string(receipt.get("result")))
        for receipt in receipts
    }
    return len(boundaries) > 1


def _receipt_identity_conflicts(receipt: Mapping[str, object]) -> bool:
    node_id = _string(receipt.get("node_id"))
    feature_id = _string(receipt.get("featureId"))
    return node_id is not None and feature_id is not None and node_id != feature_id


def _same_git_repository(left: str | Path, right: str | Path) -> bool:
    """True when both paths resolve to the same git common directory.

    Engagement worktrees share a common dir with the main checkout, so path
    equality is the wrong check — compare ``rev-parse --git-common-dir``.
    """
    import subprocess

    def common_dir(path: str | Path) -> str | None:
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError:
            return None
        try:
            process = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=str(resolved),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if process.returncode != 0 or not process.stdout.strip():
            return None
        common = Path(process.stdout.strip())
        if not common.is_absolute():
            common = resolved / common
        try:
            return str(common.resolve())
        except OSError:
            return str(common)

    left_common = common_dir(left)
    right_common = common_dir(right)
    if left_common is None or right_common is None:
        try:
            return str(Path(left).resolve()) == str(Path(right).expanduser().resolve())
        except OSError:
            return False
    return left_common == right_common


def _receipt_git_context_reasons(
    receipt: Mapping[str, object],
    *,
    git_repo_path: str | Path | None,
    engagement_branch: str,
) -> list[str]:
    """Quarantine when receipt self-description disagrees with claimed result.

    The receipt CLI records observed git_head/branch/toplevel independently of
    the claimed --result. Collection must reject envelopes where the cargo
    (result) does not match the label (observed context).
    """
    reasons: list[str] = []
    result_sha = _string(receipt.get("result"))
    git_head = _string(receipt.get("git_head"))
    git_branch = _string(receipt.get("git_branch"))
    git_toplevel = _string(receipt.get("git_toplevel"))
    if result_sha is None:
        return reasons
    if git_head is not None and git_head != result_sha:
        reasons.append(
            f"receipt result {result_sha} does not match observed git_head "
            f"{git_head}"
        )
    if git_repo_path is not None and git_toplevel is not None:
        # Factory may remove its worktree immediately after mission exit, before
        # GDDP collection. When the receipt path still exists, compare Git
        # common directories. When it is gone, the branch/result ancestry check
        # below is the durable repository-identity proof.
        receipt_worktree = Path(git_toplevel).expanduser()
        if receipt_worktree.exists() and not _same_git_repository(
            git_repo_path, receipt_worktree
        ):
            reasons.append(
                f"receipt git_toplevel {git_toplevel!r} is not the same git "
                f"repository as engagement repo {str(git_repo_path)!r}"
            )
    if git_repo_path is not None and git_branch is not None and result_sha is not None:
        from .mission_git_verify import _is_ancestor, _resolve_local_branch

        branch_name = git_branch.removeprefix("refs/heads/")
        tip = _resolve_local_branch(Path(git_repo_path), branch_name)
        if tip is None:
            reasons.append(
                f"receipt git_branch {git_branch!r} is not resolvable in the "
                f"engagement repo"
            )
        elif not _is_ancestor(Path(git_repo_path), result_sha, tip):
            reasons.append(
                f"receipt result {result_sha} is not reachable from claimed "
                f"git_branch {git_branch!r} (tip {tip})"
            )
    return reasons


def _protected_branch_push_reasons(
    git_repo_path: str | Path,
    *,
    result_sha: str,
    engagement_branch: str,
    protected_branches: Sequence[str] = ("main", "master"),
) -> list[str]:
    """Detect engagement commits that landed on protected branches.

    Environment push guards are best-effort (absolute git + ``-c
    core.hooksPath=/dev/null`` can bypass them). Collection must still catch
    protected-branch pollution by checking whether any feature result is an
    ancestor of the *live* remote protected tip (``git ls-remote``), falling
    back to cached origin/* and local tips when offline.
    """
    from .mission_git_verify import (
        _is_ancestor,
        _object_type,
        _remote_branch_tip,
        _remote_branches_containing,
        _resolve_local_branch,
    )

    reasons: list[str] = []
    repo = Path(git_repo_path)
    engagement_name = engagement_branch.removeprefix("refs/heads/")
    protected = {
        name
        for name in protected_branches
        if name != engagement_name and not engagement_name.endswith(f"/{name}")
    }
    if not protected:
        return reasons

    def _append(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    def _result_on_tip(tip: str) -> bool:
        if tip == result_sha:
            return True
        if _object_type(repo, tip) != "commit":
            return False
        return _is_ancestor(repo, result_sha, tip)

    # Live remote tips first — catches direct URL pushes that leave origin/*
    # cache stale. Offline / missing remote → None and we fall through.
    for name in protected:
        live_tip = _remote_branch_tip(repo, "origin", name)
        if live_tip is None:
            continue
        if _result_on_tip(live_tip):
            _append(
                f"feature result {result_sha} is reachable from protected "
                f"branch origin/{name} (ls-remote tip {live_tip}) — "
                f"protected-branch push detected"
            )

    # Cached remote-tracking refs (may be stale; still useful offline).
    for remote_ref in _remote_branches_containing(repo, result_sha):
        short = remote_ref.removeprefix("origin/")
        if short in protected:
            _append(
                f"feature result {result_sha} is reachable from protected "
                f"branch {remote_ref} — protected-branch push detected "
                f"(cached origin ref)"
            )

    # Local protected branch tips as final offline fallback.
    for name in protected:
        tip = _resolve_local_branch(repo, name)
        if tip is not None and _is_ancestor(repo, result_sha, tip):
            _append(
                f"feature result {result_sha} is reachable from protected "
                f"branch {name} (local tip {tip}) — protected-branch push "
                f"detected"
            )
    return reasons


def _worker_session_id(
    progress: Mapping[str, object] | None,
    handoff: Mapping[str, object] | None,
) -> str | None:
    if progress is not None:
        worker = _string(progress.get("worker_session_id"))
        if worker is not None:
            return worker
    return _string(handoff.get("workerSessionId")) if handoff else None


def _cross_check(
    receipt: Mapping[str, object] | None,
    handoff: Mapping[str, object] | None,
    git_verified: Mapping[str, object] | None,
) -> dict[str, bool | None]:
    receipt_result = _string(receipt.get("result")) if receipt else None
    handoff_result = _string(handoff.get("commitId")) if handoff else None
    verified_result = (
        _string(git_verified.get("result_sha")) if git_verified else None
    )
    return {
        "receipt_matches_handoff": (
            receipt_result == handoff_result
            if receipt_result is not None and handoff_result is not None
            else None
        ),
        "receipt_matches_git": (
            receipt_result == verified_result
            if receipt_result is not None and verified_result is not None
            else None
        ),
    }


def _missing_channels(
    *,
    receipt: Mapping[str, object] | None,
    handoff: Mapping[str, object] | None,
    progress: Mapping[str, object] | None,
    mission_id: str | None,
) -> list[str]:
    missing: list[str] = []
    if receipt is None:
        missing.append("receipt")
    else:
        for field in ("base", "result"):
            if _string(receipt.get(field)) is None:
                missing.append(f"receipt.{field}")
    if handoff is None:
        missing.append("handoff")
    else:
        for field in ("commitId", "repoPath", "successState"):
            if _string(handoff.get(field)) is None:
                missing.append(f"handoff.{field}")
    if progress is None:
        missing.append("progress")
    else:
        for field in ("started_at", "completed_at", "outcome"):
            if _string(progress.get(field)) is None:
                missing.append(f"progress.{field}")
    if mission_id is None:
        missing.append("mission_id")
    return missing


def _node_complete(
    receipt: Mapping[str, object] | None,
    handoff: Mapping[str, object] | None,
    progress: Mapping[str, object] | None,
    cross_check: Mapping[str, bool | None],
) -> bool:
    return bool(
        receipt
        and _string(receipt.get("base"))
        and _string(receipt.get("result"))
        and handoff
        and handoff.get("successState") == "success"
        and progress
        and progress.get("outcome") == "success"
        and cross_check.get("receipt_matches_handoff") is True
        and cross_check.get("receipt_matches_git") is not False
    )


def _disagreement_reasons(cross_check: Mapping[str, bool | None]) -> list[str]:
    return [
        key
        for key, matches in cross_check.items()
        if matches is False
    ]


def _quarantine_reasons(
    cross_check: Mapping[str, bool | None],
    git_verified: Mapping[str, object] | None,
) -> list[str]:
    reasons: list[str] = []
    if git_verified is not None:
        verification_reason = _string(
            git_verified.get("completion_quarantine_reason")
        )
        if verification_reason is not None:
            reasons.append(verification_reason)
    if cross_check.get("receipt_matches_handoff") is False:
        reasons.append("receipt result does not match handoff commitId")
    if cross_check.get("receipt_matches_git") is False:
        reasons.append("receipt result does not match git-verified result")
    return reasons


def _feature_drift_reason(
    demanded_ids: tuple[str, ...], observed_ids: tuple[str, ...]
) -> str | None:
    if demanded_ids == observed_ids:
        return None
    return "feature_id_drift"


def _completion_id(
    *,
    mission_id: str | None,
    feature_id: str,
    worker_session_id: str | None,
) -> str | None:
    """Build Factory's stable per-worker feature completion identity."""
    if mission_id is None or worker_session_id is None:
        return None
    return f"{mission_id}:{feature_id}:{worker_session_id}"


def _completion_digest(
    *,
    completion_id: str,
    feature_id: str,
    worker_session_id: str | None,
    base_sha: str | None,
    result_sha: str | None,
    result_ref: str,
    receipt: Mapping[str, object] | None,
    handoff: Mapping[str, object] | None,
    progress: Mapping[str, object] | None,
) -> str:
    """Hash the normalized completion envelope used for replay comparison."""
    envelope = {
        "completion_id": completion_id,
        "feature_id": feature_id,
        "worker_session_id": worker_session_id,
        "base_sha": base_sha,
        "result_sha": result_sha,
        "result_ref": result_ref,
        "receipt": dict(receipt) if receipt is not None else None,
        "handoff": dict(handoff) if handoff is not None else None,
        "progress": dict(progress) if progress is not None else None,
    }
    normalized = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def _manifest_name(feature_id: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in feature_id
    ).strip("-")
    digest = hashlib.sha256(feature_id.encode()).hexdigest()[:12]
    return f"{safe or 'feature'}--{digest}.json"


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    temporary.replace(path)
