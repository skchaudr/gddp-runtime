"""Focused presentation checks for the runtime jobs entry point."""

from scripts import node_status


def test_static_overview_identifies_config_owned_command_path():
    with node_status.console.capture() as capture:
        node_status._static_overview()

    output = capture.get()
    assert "gddp jobs" in output
    assert "runtime operator CLI" in output
    assert "gddp jobs <command> -h" in output
