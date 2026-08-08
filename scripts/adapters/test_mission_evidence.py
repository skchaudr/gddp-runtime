from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.adapters.mission_evidence import collect_mission_evidence


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def _mission_fixture(tmp_path: Path) -> tuple[Path, Path]:
    mission_dir = tmp_path / "mission"
    output_dir = tmp_path / "engagement-evidence"
    (mission_dir / "handoffs").mkdir(parents=True)
    (mission_dir / "features.json").write_text(
        json.dumps(
            {
                "features": [
                    {"id": "node-alpha", "status": "completed"},
                    {"id": "node-beta", "status": "completed"},
                ]
            }
        )
    )
    (mission_dir / "state.json").write_text(
        json.dumps({"missionId": "mis_fixture", "state": "completed"})
    )
    return mission_dir, output_dir


def _write_complete_channels(mission_dir: Path) -> None:
    handoffs = [
        {
            "featureId": "node-beta",
            "workerSessionId": "worker-beta",
            "commitId": "b" * 40,
            "repoPath": "/repos/beta",
            "successState": "success",
        },
        {
            "featureId": "node-alpha",
            "workerSessionId": "worker-alpha",
            "commitId": "a" * 40,
            "repoPath": "/repos/alpha",
            "successState": "success",
        },
    ]
    for index, handoff in enumerate(handoffs):
        (mission_dir / "handoffs" / f"{index}.json").write_text(json.dumps(handoff))

    _write_jsonl(
        mission_dir / "progress_log.jsonl",
        [
            {
                "timestamp": "2026-08-07T02:00:00Z",
                "type": "worker_started",
                "featureId": "node-beta",
                "workerSessionId": "worker-beta",
            },
            {
                "timestamp": "2026-08-07T01:00:00Z",
                "type": "worker_selected_feature",
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
            },
            {
                "timestamp": "2026-08-07T01:00:01Z",
                "type": "worker_started",
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
            },
            {
                "timestamp": "2026-08-07T02:05:00Z",
                "type": "worker_completed",
                "featureId": "node-beta",
                "workerSessionId": "worker-beta",
                "successState": "success",
            },
            {
                "timestamp": "2026-08-07T01:05:00Z",
                "type": "worker_completed",
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
                "successState": "success",
            },
        ],
    )
    _write_jsonl(
        mission_dir / "receipts.jsonl",
        [
            {
                "node_id": "node-beta",
                "base": "3" * 40,
                "result": "b" * 40,
                "git_head": "b" * 40,
                "git_branch": "gddp/eng-1",
                "git_toplevel": "/repos/beta",
                "timestamp_utc": "2026-08-07T02:04:00Z",
            },
            {
                "node_id": "node-alpha",
                "base": "2" * 40,
                "result": "a" * 40,
                "git_head": "a" * 40,
                "git_branch": "gddp/eng-1",
                "git_toplevel": "/repos/alpha",
                "timestamp_utc": "2026-08-07T01:04:00Z",
            },
        ],
    )


def test_complete_evidence_is_joined_only_by_exact_feature_id(tmp_path):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    _write_complete_channels(mission_dir)

    collected = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-1",
        result_ref="gddp/eng-1",
        demanded_feature_ids=("node-alpha", "node-beta"),
    )

    assert [item.feature_id for item in collected] == ["node-alpha", "node-beta"]
    assert len(list(output_dir.glob("*.json"))) == 2
    by_feature = {
        item.feature_id: json.loads(item.manifest_path.read_text())
        for item in collected
    }
    alpha = by_feature["node-alpha"]
    beta = by_feature["node-beta"]

    required = {
        "engagement_id",
        "mission_dir",
        "mission_id",
        "feature_id",
        "worker_session_id",
        "base_sha",
        "result_sha",
        "result_ref",
        "receipt",
        "handoff",
        "progress",
        "git_verified",
        "cross_check",
    }
    assert required <= alpha.keys()
    assert alpha["engagement_id"] == "eng-1"
    assert alpha["mission_dir"] == str(mission_dir)
    assert alpha["mission_id"] == "mis_fixture"
    assert alpha["worker_session_id"] == "worker-alpha"
    assert alpha["base_sha"] == "2" * 40
    assert alpha["result_sha"] == "a" * 40
    assert alpha["result_ref"] == "gddp/eng-1"
    assert alpha["handoff"] == {
        "commitId": "a" * 40,
        "repoPath": "/repos/alpha",
        "successState": "success",
    }
    assert alpha["progress"] == {
        "started_at": "2026-08-07T01:00:01Z",
        "completed_at": "2026-08-07T01:05:00Z",
        "outcome": "success",
    }
    assert alpha["cross_check"]["receipt_matches_handoff"] is True
    assert alpha["git_verified"] is None
    assert by_feature["node-beta"]["worker_session_id"] == "worker-beta"
    assert by_feature["node-beta"]["handoff"]["repoPath"] == "/repos/beta"
    assert by_feature["node-beta"]["base_sha"] == "3" * 40
    assert all(not item.review_required for item in collected)


@pytest.mark.parametrize("missing_channel", ["receipt", "handoff", "progress"])
def test_missing_channels_write_partial_manifest_and_route_to_review(
    tmp_path, missing_channel
):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    _write_complete_channels(mission_dir)
    if missing_channel == "receipt":
        (mission_dir / "receipts.jsonl").unlink()
    elif missing_channel == "handoff":
        for path in (mission_dir / "handoffs").glob("*.json"):
            path.unlink()
    else:
        (mission_dir / "progress_log.jsonl").unlink()

    collected = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-1",
        result_ref="gddp/eng-1",
        demanded_feature_ids=("node-alpha", "node-beta"),
    )

    assert len(collected) == 2
    assert all(item.review_required for item in collected)
    for item in collected:
        manifest = json.loads(item.manifest_path.read_text())
        assert manifest[missing_channel] is None
        assert missing_channel in manifest["missing_channels"]
        assert manifest["review_required"] is True
        assert missing_channel in manifest["review_reason"]


def test_missing_optional_handoff_field_is_preserved_as_null_and_reviewed(tmp_path):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    _write_complete_channels(mission_dir)
    alpha_path = mission_dir / "handoffs" / "1.json"
    alpha = json.loads(alpha_path.read_text())
    del alpha["repoPath"]
    alpha_path.write_text(json.dumps(alpha))

    collected = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-1",
        result_ref="gddp/eng-1",
        demanded_feature_ids=("node-alpha", "node-beta"),
    )

    alpha_result = collected[0]
    alpha_manifest = json.loads(alpha_result.manifest_path.read_text())
    assert alpha_manifest["handoff"]["repoPath"] is None
    assert alpha_result.review_required is True
    assert "handoff.repoPath" in alpha_result.review_reason


def test_malformed_artifacts_do_not_crash_or_fabricate_values(tmp_path):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    (mission_dir / "progress_log.jsonl").write_text("{broken\n")
    (mission_dir / "receipts.jsonl").write_text("not-json\n")
    (mission_dir / "handoffs" / "broken.json").write_text("[not-an-object]")

    collected = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-malformed",
        result_ref="gddp/eng-malformed",
        demanded_feature_ids=("node-alpha", "node-beta"),
    )

    assert len(collected) == 2
    for item in collected:
        manifest = json.loads(item.manifest_path.read_text())
        assert item.review_required is True
        assert manifest["receipt"] is None
        assert manifest["handoff"] is None
        assert manifest["progress"] is None
        assert manifest["base_sha"] is None
        assert manifest["result_sha"] is None


def test_conflicting_receipts_are_preserved_but_route_only_that_node_to_review(
    tmp_path,
):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    _write_complete_channels(mission_dir)
    with (mission_dir / "receipts.jsonl").open("a") as receipts:
        receipts.write(
            json.dumps(
                {
                    "node_id": "node-alpha",
                    "base": "9" * 40,
                    "result": "a" * 40,
                    "git_head": "a" * 40,
                }
            )
            + "\n"
        )

    alpha, beta = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-conflict",
        result_ref="gddp/eng-conflict",
        demanded_feature_ids=("node-alpha", "node-beta"),
    )

    assert alpha.review_required is True
    assert "conflicting_receipts" in (alpha.review_reason or "")
    assert json.loads(alpha.manifest_path.read_text())["base_sha"] == "9" * 40
    assert beta.review_required is False


def test_crash_preserves_completed_node_and_reviews_incomplete_node(tmp_path):
    mission_dir, output_dir = _mission_fixture(tmp_path)
    _write_complete_channels(mission_dir)
    (mission_dir / "state.json").write_text(
        json.dumps({"missionId": "mis_fixture", "state": "running"})
    )
    (mission_dir / "handoffs" / "0.json").unlink()
    receipt_lines = (mission_dir / "receipts.jsonl").read_text().splitlines()
    (mission_dir / "receipts.jsonl").write_text(receipt_lines[1] + "\n")
    progress_records = [
        json.loads(line)
        for line in (mission_dir / "progress_log.jsonl").read_text().splitlines()
        if json.loads(line).get("featureId") != "node-beta"
    ]
    progress_records.append(
        {
            "timestamp": "2026-08-07T02:00:00Z",
            "type": "worker_started",
            "featureId": "node-beta",
            "workerSessionId": "worker-beta",
        }
    )
    _write_jsonl(mission_dir / "progress_log.jsonl", progress_records)

    collected = collect_mission_evidence(
        mission_dir=mission_dir,
        output_dir=output_dir,
        engagement_id="eng-crashed",
        result_ref="gddp/eng-crashed",
        demanded_feature_ids=("node-alpha", "node-beta"),
        mission_outcome="crashed",
    )

    alpha, beta = collected
    assert alpha.feature_id == "node-alpha"
    assert alpha.review_required is False
    assert json.loads(alpha.manifest_path.read_text())["result_sha"] == "a" * 40
    assert beta.feature_id == "node-beta"
    assert beta.review_required is True
    beta_manifest = json.loads(beta.manifest_path.read_text())
    assert beta_manifest["worker_session_id"] == "worker-beta"
    assert beta_manifest["result_sha"] is None
    assert beta_manifest["mission_outcome"] == "crashed"
    assert "crashed" in beta.review_reason
