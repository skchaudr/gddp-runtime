"""Capability declarations must match the code that implements them.

A capability audit (2026-09-03) found three declarations that contradicted
their own adapters. All three came from adapters with no `capabilities()`
method at all, where `adapter_capabilities()` synthesizes a least-capable
declaration from `supports_engagement()` alone
(`executor_protocol.py:288-304`) — so any real capability beyond engagement
was silently reported absent.

That matters unevenly. Of the declared fields, only four are load-bearing:
`engagement`, `resume`, `cancellation`, and `midturn_steering`. The rest are
written to `capabilities.json` and never read back for a decision. These
tests cover the load-bearing ones plus `reply`, which the reconciler probes
by `hasattr` rather than by declaration — a divergence that made the
declaration unusable as a policy input.
"""

from __future__ import annotations

import inspect
import sys

import pytest

from adapters.executor_protocol import ExecutorCapabilities, adapter_capabilities
from adapters.jules_api_adapter import JulesApiAdapter
from adapters.local_subprocess_adapter import (
    DroidSubprocessAdapter,
    LocalSubprocessAdapter,
)
from adapters.mission_adapter import MissionAdapter


def _local(tmp_path, cls=LocalSubprocessAdapter):
    return cls(
        repo="owner/repo",
        argv=(sys.executable, "-c", "pass"),
        spool_root=tmp_path,
    )


# --------------------------------------------------------------------------- #
# cancellation: three adapters SIGTERM but declared "none"
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cls", [LocalSubprocessAdapter, DroidSubprocessAdapter])
def test_local_transports_declare_the_cancellation_they_implement(tmp_path, cls):
    """`cancel()` killpg's SIGTERM and returns True, so the kind is
    preemptive. The synthesized default said "none", and `cancellation` is
    read by `dispatcher.cancel_remote_session` to render operator-facing
    outcome text — a killable attempt was being reported uncancellable.
    """
    caps = _local(tmp_path, cls).capabilities()

    assert caps.cancellation == "preemptive"
    assert caps.supports("cancellation") is True
    assert "SIGTERM" in inspect.getsource(cls.cancel)


def test_droid_inherits_the_local_declaration_under_its_own_name():
    """droid is a LocalSubprocessAdapter subclass that only swaps argv, so it
    must not report a different transport identity or lose the fix."""
    assert DroidSubprocessAdapter.capabilities is LocalSubprocessAdapter.capabilities
    assert DroidSubprocessAdapter.executor_name == "droid"


def test_mission_declares_cancellation_and_engagement():
    caps = MissionAdapter("owner/repo").capabilities()

    assert caps.cancellation == "preemptive"
    assert caps.engagement is True
    assert "SIGTERM" in inspect.getsource(MissionAdapter.cancel)


def test_mission_engagement_declaration_agrees_with_its_shim():
    """`engagement` is the one capability the dispatcher hard-gates on
    (`dispatcher.py:179`) while the reconciler reads `supports_engagement()`
    (`reconciler.py:284`). Two read sites for one boolean: they must agree.
    """
    adapter = MissionAdapter("owner/repo")

    assert adapter.capabilities().engagement is adapter.supports_engagement()


# --------------------------------------------------------------------------- #
# reply: implemented but declared absent
# --------------------------------------------------------------------------- #


def test_jules_api_declares_the_reply_it_implements():
    adapter = JulesApiAdapter("owner/repo", api_key="test-key")
    caps = adapter.capabilities()

    assert caps.reply is True
    assert callable(getattr(adapter, "reply", None))


def test_jules_api_still_declares_no_cancellation():
    """Not every conservative default was wrong: `cancel()` genuinely returns
    False because the documented API has no non-destructive cancel.
    """
    adapter = JulesApiAdapter("owner/repo", api_key="test-key")

    assert adapter.capabilities().cancellation == "none"
    assert adapter.cancel.__doc__ is not None
    assert adapter.cancel(None) is False


# --------------------------------------------------------------------------- #
# the general rule this audit produced
# --------------------------------------------------------------------------- #


def test_an_adapter_implementing_reply_must_declare_it(tmp_path):
    """The reconciler probes `hasattr(adapter, "reply")` rather than the
    declaration, so an adapter can implement reply while declaring it absent
    and nothing breaks — until a policy layer starts trusting declarations.
    Close the divergence by construction.
    """
    adapters = [
        JulesApiAdapter("owner/repo", api_key="test-key"),
        _local(tmp_path),
        _local(tmp_path, DroidSubprocessAdapter),
        MissionAdapter("owner/repo"),
    ]

    for adapter in adapters:
        caps = adapter_capabilities(adapter, getattr(adapter, "executor_name", "?"))
        implements_reply = callable(getattr(adapter, "reply", None))
        assert caps.reply is implements_reply, (
            f"{caps.executor}: declares reply={caps.reply} but "
            f"implements_reply={implements_reply}"
        )


def test_a_synthesized_declaration_is_still_least_capable():
    """The fallback path must stay conservative for adapters that have not
    declared yet — the fix is per-adapter honesty, not a laxer default."""

    class Undeclared:
        pass

    caps = adapter_capabilities(Undeclared(), "undeclared")

    assert caps == ExecutorCapabilities(executor="undeclared")
    assert caps.cancellation == "none"
    assert caps.engagement is False
    assert caps.reply is False
