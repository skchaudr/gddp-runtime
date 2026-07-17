import tempfile
from pathlib import Path

from scripts.runtime.verification.receipt_sink import receipt_path, write_receipt


class FakeReceipt:
    def __init__(self, node_id: str, payload: str):
        self.node_id = node_id
        self.payload = payload

    def model_dump_json(self, indent: int = 2) -> str:
        return self.payload


def test_receipt_path_includes_zero_based_attempt():
    path = receipt_path(
        "project-a",
        "node-a",
        base=Path("/receipts"),
        job_id="job_123",
        attempt=0,
    )
    assert path == Path("/receipts/project-a/node-a/job_123-attempt0.json")


def test_job_id_only_path_remains_compatible():
    path = receipt_path(
        "project-a", "node-a", base=Path("/receipts"), job_id="job_123"
    )
    assert path == Path("/receipts/project-a/node-a/job_123.json")


def test_writing_retry_receipt_preserves_first_attempt():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        first_path = write_receipt(
            FakeReceipt("node-a", '{"attempt": 0}'),
            "project-a",
            base=base,
            job_id="job_123",
            attempt=0,
        )
        second_path = write_receipt(
            FakeReceipt("node-a", '{"attempt": 1}'),
            "project-a",
            base=base,
            job_id="job_123",
            attempt=1,
        )

        assert first_path != second_path
        assert first_path.read_text() == '{"attempt": 0}'
        assert second_path.read_text() == '{"attempt": 1}'


def test_same_attempt_rerun_gets_deterministic_collision_suffix():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        first_path = write_receipt(
            FakeReceipt("node-a", '{"run": 1}'), "project-a", base=base,
            job_id="job_123", attempt=0,
        )
        rerun_path = write_receipt(
            FakeReceipt("node-a", '{"run": 2}'), "project-a", base=base,
            job_id="job_123", attempt=0,
        )

        assert rerun_path.name == "job_123-attempt0-rerun1.json"
        assert first_path.read_text() == '{"run": 1}'
        assert rerun_path.read_text() == '{"run": 2}'


def test_node_only_receipt_overwrites_legacy_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        first_path = write_receipt(FakeReceipt("node-a", '{"run": 1}'), "project-a", base=base)
        second_path = write_receipt(FakeReceipt("node-a", '{"run": 2}'), "project-a", base=base)

        assert second_path == first_path
        assert first_path.read_text() == '{"run": 2}'


def test_job_id_only_receipt_overwrites_legacy_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        first_path = write_receipt(
            FakeReceipt("node-a", '{"run": 1}'), "project-a", base=base, job_id="job_123",
        )
        second_path = write_receipt(
            FakeReceipt("node-a", '{"run": 2}'), "project-a", base=base, job_id="job_123",
        )

        assert second_path == first_path
        assert first_path.read_text() == '{"run": 2}'
