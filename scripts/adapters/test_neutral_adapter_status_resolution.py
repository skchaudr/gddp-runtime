"""Contract: neutral adapters resolve status via recorded attempt_dir."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.cursor_cli_adapter import CursorCliAdapter
from adapters.executor_protocol import SessionRef
from adapters.local_subprocess_adapter import LocalSubprocessAdapter
from adapters.pi_rpc_adapter import PiRpcAdapter
from runtime.local_attempt import ExitState, write_exit_state

_ADAPTERS = (
    ("cursor_cli", CursorCliAdapter, {"repo": "owner/repo"}),
    (
        "local_subprocess",
        LocalSubprocessAdapter,
        {"repo": "owner/repo", "argv": ["/bin/true"]},
    ),
    ("pi_rpc", PiRpcAdapter, {"repo": "owner/repo", "model": "m"}),
)


def _adapter(executor: str, cls: type, kwargs: dict, *, spool_root: Path):
    return cls(**kwargs, spool_root=spool_root)


def _recorded_attempt(tmp_path: Path, session_id: str) -> Path:
    recorded = tmp_path / "legacy-spool" / session_id
    recorded.mkdir(parents=True)
    return recorded


@pytest.mark.parametrize("executor,cls,kwargs", _ADAPTERS)
def test_status_reads_recorded_attempt_dir_outside_canonical_spool(
    tmp_path, executor, cls, kwargs
):
    canonical = tmp_path / "canonical-spool"
    canonical.mkdir()
    session_id = "att-recorded"
    recorded = _recorded_attempt(tmp_path, session_id)
    write_exit_state(recorded, ExitState(returncode=0, cancelled=False, plumbing=False))

    adapter = _adapter(executor, cls, kwargs, spool_root=canonical)
    session_ref = SessionRef(
        executor=executor,
        session_id=session_id,
        attempt_dir=str(recorded),
    )

    assert adapter.status(session_ref).state == "completed"
    assert adapter.status(SessionRef(executor=executor, session_id=session_id)).state == (
        "failed"
    )


@pytest.mark.parametrize("executor,cls,kwargs", _ADAPTERS)
def test_status_reads_failed_recorded_attempt_dir_outside_canonical_spool(
    tmp_path, executor, cls, kwargs
):
    canonical = tmp_path / "canonical-spool"
    canonical.mkdir()
    session_id = "att-failed"
    recorded = _recorded_attempt(tmp_path, session_id)
    write_exit_state(
        recorded,
        ExitState(
            returncode=17,
            cancelled=False,
            plumbing=False,
            error="persist rejected",
        ),
    )

    adapter = _adapter(executor, cls, kwargs, spool_root=canonical)
    session_ref = SessionRef(
        executor=executor,
        session_id=session_id,
        attempt_dir=str(recorded),
    )

    assert adapter.status(session_ref).state == "failed"
