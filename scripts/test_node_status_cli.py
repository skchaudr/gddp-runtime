"""Focused presentation checks for the runtime jobs entry point."""

from scripts import node_status


def test_menu_choice_uses_one_keypress_without_enter(monkeypatch):
    monkeypatch.setattr(node_status, "_read_key", lambda: "o")

    assert node_status._menu_choice({"l": (), "o": ()}, default="l") == "o"


def test_menu_choice_keeps_enter_as_the_default_shortcut(monkeypatch):
    monkeypatch.setattr(node_status, "_read_key", lambda: "\r")

    assert node_status._menu_choice({"l": (), "o": ()}, default="l") == "l"


def test_static_overview_identifies_config_owned_command_path():
    with node_status.console.capture() as capture:
        node_status._static_overview()

    output = capture.get()
    assert "gddp jobs" in output
    assert "runtime operator CLI" in output
    assert "gddp jobs <command> -h" in output
