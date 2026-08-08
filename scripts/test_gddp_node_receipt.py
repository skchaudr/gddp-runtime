from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("gddp_node_receipt.py")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture
def git_repo() -> Iterator[Path]:
    repo = Path(tempfile.mkdtemp(prefix="gddp-receipt-test-")).resolve()
    try:
        subprocess.run(
            ["git", "init", "-b", "receipt-test"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        _git(repo, "config", "user.name", "Receipt Test")
        _git(repo, "config", "user.email", "receipt-test@example.invalid")
        (repo / "tracked.txt").write_text("initial\n")
        _git(repo, "add", "tracked.txt")
        _git(repo, "commit", "-m", "initial")
        yield repo
    finally:
        shutil.rmtree(repo)


def _invoke(
    cwd: Path,
    receipts_path: Path,
    *,
    node_id: str = "node-alpha",
    base: str = "claimed-base",
    result: str = "claimed-result",
    omitted: str | None = None,
) -> subprocess.CompletedProcess[str]:
    values = {
        "--node-id": node_id,
        "--base": base,
        "--result": result,
    }
    argv = [sys.executable, str(SCRIPT)]
    for option, value in values.items():
        if option != omitted:
            argv.extend([option, value])
    env = os.environ.copy()
    env["GDDP_RECEIPTS_PATH"] = str(receipts_path)
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_success_appends_one_complete_receipt_line(git_repo: Path):
    receipts_path = git_repo / "receipts.jsonl"
    base = _git(git_repo, "rev-parse", "HEAD")

    completed = _invoke(
        git_repo,
        receipts_path,
        node_id="Node_CASE-1",
        base=base,
        result=base,
    )

    assert completed.returncode == 0, completed.stderr
    lines = receipts_path.read_text().splitlines()
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert set(receipt) == {
        "node_id",
        "base",
        "result",
        "timestamp_utc",
        "git_head",
        "git_branch",
        "git_toplevel",
    }
    assert receipt["node_id"] == "Node_CASE-1"
    assert receipt["base"] == base
    assert receipt["result"] == base
    assert receipt["timestamp_utc"].endswith("+00:00")


def test_git_context_is_observed_instead_of_copied_from_claims(git_repo: Path):
    receipts_path = git_repo / "receipts.jsonl"
    claimed_result = "0" * 40

    completed = _invoke(
        git_repo,
        receipts_path,
        result=claimed_result,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(receipts_path.read_text())
    assert receipt["result"] == claimed_result
    assert receipt["git_head"] == _git(git_repo, "rev-parse", "HEAD")
    assert receipt["git_head"] != claimed_result
    assert receipt["git_branch"] == _git(
        git_repo, "rev-parse", "--abbrev-ref", "HEAD"
    )
    assert receipt["git_toplevel"] == _git(
        git_repo, "rev-parse", "--show-toplevel"
    )


@pytest.mark.parametrize("omitted", ["--node-id", "--base", "--result"])
def test_missing_required_argument_preserves_receipt_file(
    git_repo: Path, omitted: str
):
    receipts_path = git_repo / "receipts.jsonl"
    original = b'{"existing":"receipt"}\n'
    receipts_path.write_bytes(original)

    completed = _invoke(git_repo, receipts_path, omitted=omitted)

    assert completed.returncode != 0
    assert omitted in completed.stderr
    assert receipts_path.read_bytes() == original


def test_non_git_working_directory_fails_without_creating_receipt():
    directory = Path(tempfile.mkdtemp(prefix="gddp-receipt-nongit-")).resolve()
    receipts_path = directory / "receipts.jsonl"
    try:
        completed = _invoke(directory, receipts_path)

        assert completed.returncode != 0
        assert "git context" in completed.stderr.casefold()
        assert not receipts_path.exists()
    finally:
        shutil.rmtree(directory)


def test_identical_calls_append_independently_parseable_json_lines(git_repo: Path):
    receipts_path = git_repo / "receipts.jsonl"
    head = _git(git_repo, "rev-parse", "HEAD")

    first = _invoke(git_repo, receipts_path, base=head, result=head)
    second = _invoke(git_repo, receipts_path, base=head, result=head)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    raw = receipts_path.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.splitlines()
    assert len(lines) == 2
    receipts = [json.loads(line) for line in lines]
    assert [
        (receipt["node_id"], receipt["base"], receipt["result"])
        for receipt in receipts
    ] == [("node-alpha", head, head), ("node-alpha", head, head)]
