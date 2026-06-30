"""Constraint forbidden-pattern scan — ported from verify_node.py."""

from __future__ import annotations

import re
from pathlib import Path

from ..schemas import ConstraintCheck
from .probes import probe_for, read_repo_file

FORBIDDEN_PATTERNS = [
    (r"\bsource\b.*\b(grok|pi|gemini|droid|codex|jules)\b.*\.zsh",
     "sourcing an executor-specific module from a common-layer file"),
    (r"^\s*python3?\b", "introducing a python runtime dependency in a zsh lib"),
]


def collect_constraint_files(node_yaml: dict, repo: Path) -> list[str]:
    """Files the constraints scope: explicit probe files + all lib/*.zsh."""
    files: set[str] = set()
    node_id = node_yaml.get("node_id", "")
    for item in node_yaml.get("acceptance", []):
        probe = probe_for(node_id, item.get("id", ""))
        if probe:
            files.update(probe.get("files", []))
            if probe.get("file"):
                files.add(probe["file"])
    if (repo / "lib").is_dir():
        for f in sorted((repo / "lib").glob("*.zsh")):
            files.add(f.relative_to(repo).as_posix())
    return sorted(files)


def evaluate_constraint(
    text: str,
    repo: Path,
    constraint_files: list[str],
) -> ConstraintCheck:
    """Scan referenced lib files for forbidden patterns."""
    bodies = [
        (f, c)
        for f in constraint_files
        if (c := read_repo_file(repo, f)) is not None
    ]
    evidence: list[str] = []
    violated = False
    for rx, why in FORBIDDEN_PATTERNS:
        comp = re.compile(rx, re.MULTILINE)
        for fname, body in bodies:
            for m in comp.finditer(body):
                line_no = body.count("\n", 0, m.start()) + 1
                evidence.append(f"{fname}:{line_no}: {why} ({m.group(0)!r})")
                violated = True
    if "AA_TARGETS_CONF" in text or "targets.conf" in text:
        for fname, body in bodies:
            if re.search(r"AA_TARGETS_CONF=.*targets\.conf", body):
                evidence.append(
                    f"{fname}: AA_TARGETS_CONF default points at "
                    f"targets.conf (preserved)"
                )
                break
    status = "violated" if violated else "clear"
    return ConstraintCheck(
        constraint=text,
        status=status,
        confidence=0.85 if not violated else 0.75,
        method="forbidden_pattern_scan",
        evidence=evidence or ["no forbidden patterns matched"],
        reasoning=(
            "Scanned referenced lib files for forbidden patterns "
            "(executor sourcing, runtime deps). "
            + ("No violations." if not violated else f"{len(evidence)} violation(s).")
        ),
    )