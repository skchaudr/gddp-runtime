"""Archived with jules_cli_adapter.py — not collected (pytest norecursedirs).

CLI-only tests moved out of the live suite in Phase 2B. Kept for reference.
"""
from __future__ import annotations

# NOTE: these snippets are historical reference; imports assume the pre-archive
# layout (adapters.jules_cli_adapter). Not executed under current pytest.ini.

def test_jules_successful_list_without_session_is_missing(monkeypatch):
    import adapters.jules_cli_adapter as jca

    monkeypatch.setattr(
        jca.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="ID  STATUS\nother-session  Running\n",
            stderr="",
        ),
    )

    status = JulesCliAdapter(repo="owner/repo").status(
        SessionRef("jules_cli", "expected-session")
    )

    assert status.state == "missing"
    assert "not found" in (status.error or "")


def test_dispatcher_selects_jules_cli_adapter(monkeypatch):
    job = _sample_job(executor="jules_cli")

    cli_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef(
                executor="jules_cli", session_id="1234567890123456"
            ),
        )
    )
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)
    # Guard: the action adapter must not be selected.
    action_dispatch = MagicMock()
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)

    result = dispatch(job, "owner/repo")

    cli_dispatch.assert_called_once()
    action_dispatch.assert_not_called()
    assert result.success is True
    assert result.session_ref is not None
    assert result.session_ref.executor == "jules_cli"
    assert result.session_ref.session_id == "1234567890123456"


def test_jules_cli_status_awaiting_maps_to_needs_operator(monkeypatch):
    """Live Jules output shows "Awaiting User F" (truncated). It must not fall
    through to running; it means the executor is blocked on a human."""
    import adapters.jules_cli_adapter as jca
    from types import SimpleNamespace

    session_id = "16944924106855934613"
    list_output = (
        f"{session_id}\tUpdate old...\tskchaudr/saboorkc.dev\t"
        "6 days ago\tAwaiting User F\n"
    )

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=list_output, stderr="")

    monkeypatch.setattr(jca.subprocess, "run", fake_run)

    adapter = JulesCliAdapter(repo="skchaudr/saboorkc.dev")
    status = adapter.status(
        SessionRef(executor="jules_cli", session_id=session_id)
    )
    assert status.state == "needs_operator"


def test_jules_cli_status_unknown_keyword_still_running(monkeypatch):
    """Regression guard: an unrecognized keyword that is not "awaiting" still
    falls through to running (the original fail-safe behaviour)."""
    import adapters.jules_cli_adapter as jca
    from types import SimpleNamespace

    session_id = "16944924106855934614"
    list_output = f"{session_id}\tsome task\towner/repo\t1 day ago\tIn Review\n"

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=list_output, stderr="")

    monkeypatch.setattr(jca.subprocess, "run", fake_run)

    adapter = JulesCliAdapter(repo="owner/repo")
    status = adapter.status(
        SessionRef(executor="jules_cli", session_id=session_id)
    )
    assert status.state == "running"


@pytest.mark.parametrize(
    "poll_result",
    [
        subprocess.TimeoutExpired(["jules", "remote", "list"], 30),
        FileNotFoundError("jules"),
        OSError("subprocess unavailable"),
        SimpleNamespace(returncode=2, stdout="", stderr="service unavailable"),
    ],
    ids=["timeout", "missing-binary", "subprocess-error", "nonzero"],
)


def test_jules_cli_status_infrastructure_failure_is_transient(
    monkeypatch, poll_result
):
    import adapters.jules_cli_adapter as jca

    def fake_run(*args, **kwargs):
        if isinstance(poll_result, BaseException):
            raise poll_result
        return poll_result

    monkeypatch.setattr(jca.subprocess, "run", fake_run)

    status = JulesCliAdapter(repo="owner/repo").status(
        SessionRef(executor="jules_cli", session_id="target-session")
    )

    assert status.state == "poll_error"
    assert status.error


# =========================================================================== #
# 7. Issue #6 — GDDP_EXECUTOR_OVERRIDE reroutes dispatch without graph changes
# =========================================================================== #
