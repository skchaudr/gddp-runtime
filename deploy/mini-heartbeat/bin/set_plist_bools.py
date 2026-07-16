#!/usr/bin/env python3
"""Set approved launchd plist boolean keys without editing XML as text."""

import os
import plistlib
import sys
import tempfile
from pathlib import Path


APPROVED_KEYS = {"RunAtLoad", "KeepAlive"}


def set_true(plist_path: Path, keys: list[str]) -> None:
    invalid_keys = set(keys) - APPROVED_KEYS
    if invalid_keys:
        raise ValueError(f"unsupported plist key(s): {', '.join(sorted(invalid_keys))}")

    with plist_path.open("rb") as source:
        plist = plistlib.load(source)

    for key in keys:
        plist[key] = True

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=plist_path.parent,
            prefix=f".{plist_path.name}.",
            delete=False,
        ) as destination:
            plistlib.dump(plist, destination, sort_keys=False)
            temporary_path = Path(destination.name)
        os.chmod(temporary_path, plist_path.stat().st_mode)
        os.replace(temporary_path, plist_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(arguments: list[str]) -> int:
    if len(arguments) < 2:
        print(
            "usage: set_plist_bools.py PLIST_PATH KEY [KEY ...]",
            file=sys.stderr,
        )
        return 2

    try:
        set_true(Path(arguments[0]), arguments[1:])
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        print(f"set_plist_bools.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
