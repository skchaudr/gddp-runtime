"""Operator steer channel: steer.jsonl parsing for the pi_rpc supervisor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.pi_rpc_adapter import _read_steer_messages  # noqa: E402


def test_plain_lines_become_messages(tmp_path: Path) -> None:
    steer = tmp_path / "steer.jsonl"
    steer.write_text("focus on the failing test\nkeep the diff small\n")
    messages, offset = _read_steer_messages(steer, 0)
    assert messages == ["focus on the failing test", "keep the diff small"]
    assert offset == steer.stat().st_size


def test_json_lines_take_message_field(tmp_path: Path) -> None:
    steer = tmp_path / "steer.jsonl"
    line = json.dumps({"ts": "2026-08-12T00:00:00Z", "message": "stop after this file"})
    steer.write_text(line + "\n")
    messages, _ = _read_steer_messages(steer, 0)
    assert messages == ["stop after this file"]


def test_offset_continuation_reads_only_appended(tmp_path: Path) -> None:
    steer = tmp_path / "steer.jsonl"
    steer.write_text("first\n")
    first, offset = _read_steer_messages(steer, 0)
    assert first == ["first"]
    with steer.open("a") as handle:
        handle.write("second\n")
    second, _ = _read_steer_messages(steer, offset)
    assert second == ["second"]


def test_missing_or_empty_file_is_noop(tmp_path: Path) -> None:
    assert _read_steer_messages(tmp_path / "nope.jsonl", 0) == ([], 0)
    steer = tmp_path / "steer.jsonl"
    steer.write_text("")
    assert _read_steer_messages(steer, 0) == ([], 0)


def test_blank_and_malformed_lines_skipped(tmp_path: Path) -> None:
    steer = tmp_path / "steer.jsonl"
    steer.write_text('\n{"no_message": true}\n{"message": ""}\nreal message\n')
    messages, _ = _read_steer_messages(steer, 0)
    assert messages == ["real message"]
