"""Deterministic criterion probes — ported from gddp-config/scripts/verify_node.py."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ..schemas import CriterionCheck

CHECK_PROBES = {
    # ── common-core ──
    "aa-root-and-state-paths": {
        "type": "symbol",
        "files": ["lib/common.zsh"],
        "patterns": [r"\bAA_ROOT\b", r"\bAA_DATA_HOME\b",
                     r"\bAA_STATE_HOME\b", r"\bAA_SCHEMA\b"],
        "all": True,
    },
    "aa-init-dirs-creates-state": {
        "type": "func",
        "files": ["lib/common.zsh", "lib/fire.zsh"],
        "name": "aa_init_dirs",
        "patterns": [r"aa_packet_dir", r"aa_runs_dir"],
    },
    "aa-validate-packet-schema": {
        "type": "func",
        "files": ["lib/common.zsh"],
        "name": "aa_validate_packet",
        "patterns": [r"aa_require_jq", r"jq .*-f", r"AA_SCHEMA"],
    },
    "aa-require-jq-errors": {
        "type": "func",
        "files": ["lib/common.zsh"],
        "name": "aa_require_jq",
        "patterns": [r"command -v jq", r"aa_die"],
    },
    "slug-and-iso-helpers": {
        "type": "symbol",
        "files": ["lib/common.zsh"],
        "patterns": [r"aa_slug", r"aa_now_iso", r"aa_now_id",
                     r"aa_title_from_prompt"],
        "all": True,
    },

    # ── dispatch-grok ──
    # grk tiers must be distinct: graph says speed + frontier resolve to
    # distinct variants incl --model grok-frontier. In the real targets.conf
    # the speed tier is identical to default (no --model), which is a genuine
    # criteria_mismatch this probe surfaces deterministically.
    "grk-tier-variants": {
        "type": "tier_distinct",
        "target": "grk",
        "file": "targets.conf",
        "require_distinct": ["default", "speed", "frontier"],
        "marker": r"--model grok-frontier",
        "mismatch_kind": "tier_distinct",
        "human_question": ("grk speed tier is identical to default in "
                           "targets.conf (no --model). Is that intended, or "
                           "should speed map to a distinct grok variant?"),
    },
    "grk-default-tier": {
        "type": "tier_distinct",
        "target": "grk",
        "file": "targets.conf",
        "require_present": ["default"],
        "also_check_files": ["lib/targets.zsh"],
        "patterns": [r"aa_target_lookup"],
        "mismatch_kind": "source_path",
    },
    "acceptance-test-covers-grk": {
        "type": "path",
        "path": "tests/acceptance.zsh",
        "also_grep": [r"\bgrk\b|grok"],
        "needs_evidence_when_absent": True,
        "evidence_what": "tests/acceptance.zsh grk/sync-target smoke path",
    },

    # ── dispatch-codex ──
    # cdx and codex are aliases; reconciliation must handle both.
    "cdx-async-placeholder": {
        "type": "tier_distinct",
        "target": "cdx",
        "file": "targets.conf",
        "require_present": ["default"],
        "alias_of": "cdx",
        "aliases": ["codex"],
        "mismatch_kind": "alias_integration",
        "human_question": ("cdx and codex are aliases for __codex_async. "
                           "Does reconciliation handle both refs cleanly?"),
    },

    # ── sell-valuables: intake + listing ──
    "incoming-readme-documents-layout": {
        "type": "symbol",
        "files": ["incoming/README.md"],
        "patterns": [r"description\.txt", r"photos/", r"meta\.yaml",
                     r"YYYY-MM-DD-short-slug"],
        "all": True,
    },
    "example-folder-present": {
        "type": "paths",
        "paths": ["incoming/_example/description.txt",
                  "incoming/_example/meta.yaml",
                  "incoming/_example/photos/.gitkeep"],
    },
    "meta-yaml-fields-documented": {
        "type": "symbol",
        "files": ["incoming/README.md"],
        "patterns": [r"price_hint", r"shipping", r"condition",
                     r"category_hint"],
        "all": True,
    },
    "underscore-folders-ignored": {
        "type": "symbol",
        "files": ["src/sell_valuables/generate_listing.py"],
        "patterns": [r"not d\.name\.startswith\(\"_\"\)"],
        "all": True,
    },
    "gitignore-incoming-artifacts": {
        "type": "symbol",
        "files": ["incoming/.gitignore"],
        "patterns": [r"\*", r"!README\.md", r"!_example/", r"!_example/\*\*"],
        "all": True,
    },
    "item-intake-dataclass": {
        "type": "symbol",
        "files": ["src/sell_valuables/intake.py"],
        "patterns": [r"@dataclass\(frozen=True\)", r"class ItemIntake",
                     r"item_id: str", r"root: Path", r"description: str",
                     r"photos: tuple\[Path, \.\.\.\]", r"meta: dict"],
        "all": True,
    },
    "load-item-requires-description": {
        "type": "func",
        "files": ["src/sell_valuables/intake.py"],
        "name": "load_item",
        "patterns": [r"description\.txt", r"FileNotFoundError",
                     r"if not description", r"ValueError"],
    },
    "photos-filtered-by-extension": {
        "type": "symbol",
        "files": ["src/sell_valuables/intake.py"],
        "patterns": [r"PHOTO_EXTENSIONS", r"\.jpg", r"\.jpeg", r"\.png",
                     r"\.heic", r"\.webp", r"suffix\.lower\(\)"],
        "all": True,
    },
    "meta-yaml-parsed": {
        "type": "func",
        "files": ["src/sell_valuables/intake.py"],
        "name": "load_item",
        "patterns": [r"meta\.yaml", r"yaml\.safe_load",
                     r"isinstance\(meta, dict\)", r"ValueError"],
    },
    "resolve-incoming-root": {
        "type": "func",
        "files": ["src/sell_valuables/intake.py"],
        "name": "resolve_incoming_root",
        "patterns": [r"parents\[2\]", r"return root / \"incoming\""],
    },
    "build-title-first-line": {
        "type": "func",
        "files": ["src/sell_valuables/listing.py"],
        "name": "build_title",
        "patterns": [r"splitlines\(\)\[0\]", r"max_len: int = 80",
                     r"\.\.\."],
    },
    "build-body-condition-shipping": {
        "type": "func",
        "files": ["src/sell_valuables/listing.py"],
        "name": "build_body",
        "patterns": [r"condition", r"shipping", r"Local pickup only",
                     r"Shipping available"],
    },
    "build-body-photo-count": {
        "type": "func",
        "files": ["src/sell_valuables/listing.py"],
        "name": "build_body",
        "patterns": [r"if item\.photos", r"Photos:", r"len\(item\.photos\)"],
    },
    "listing-markdown-structure": {
        "type": "func",
        "files": ["src/sell_valuables/listing.py"],
        "name": "build_listing_markdown",
        "patterns": [r"\*\*Price:\*\*", r"FB_MARKETPLACE_CREATE_URL",
                     r"build_body"],
    },
    "fb-create-url-constant": {
        "type": "symbol",
        "files": ["src/sell_valuables/listing.py"],
        "patterns": [r"FB_MARKETPLACE_CREATE_URL",
                     r"facebook\.com/marketplace/create/item"],
        "all": True,
    },
    "listing-cli:console-script-entrypoint": {
        "type": "symbol",
        "files": ["pyproject.toml"],
        "patterns": [r"sell-listing\s*=\s*\"sell_valuables\.generate_listing:main\""],
        "all": True,
    },
    "generate-listing-writes-file": {
        "type": "func",
        "files": ["src/sell_valuables/generate_listing.py"],
        "name": "generate_listing",
        "patterns": [r"load_item", r"listing\.md", r"build_listing_markdown",
                     r"write_text"],
    },
    "item-id-argument": {
        "type": "func",
        "files": ["src/sell_valuables/generate_listing.py"],
        "name": "main",
        "patterns": [r"item_id", r"incoming/ not found", r"incoming / args\.item_id"],
    },
    "auto-single-candidate": {
        "type": "symbol",
        "files": ["src/sell_valuables/generate_listing.py"],
        "patterns": [r"candidates", r"not d\.name\.startswith\(\"_\"\)",
                     r"len\(candidates\) != 1"],
        "all": True,
    },
    "incoming-override-flag": {
        "type": "symbol",
        "files": ["src/sell_valuables/generate_listing.py"],
        "patterns": [r"--incoming", r"args\.incoming or resolve_incoming_root"],
        "all": True,
    },

    # ── sell-valuables: FB hook + Playwright ──
    "fb-post-hook:console-script-entrypoint": {
        "type": "symbol",
        "files": ["pyproject.toml"],
        "patterns": [r"sell-post-fb\s*=\s*\"sell_valuables\.post_to_fb:main\""],
        "all": True,
    },
    "generates-listing-first": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "main",
        "patterns": [r"generate_listing\(item_dir\)", r"Wrote"],
    },
    "open-flag-browser": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"--open", r"webbrowser\.open", r"FB_MARKETPLACE_CREATE_URL",
                     r"subprocess\.run\(\[\"open\""],
        "all": True,
    },
    "playwright-flag-skeleton": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"--playwright", r"post_with_playwright", r"dry_run=True",
                     r"print\(result\)"],
        "all": True,
    },
    "default-manual-instructions": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"Open manually:", r"--open or --playwright"],
        "all": True,
    },
    "optional-browser-extra": {
        "type": "symbol",
        "files": ["pyproject.toml", "src/sell_valuables/post_to_fb.py"],
        "patterns": [r"browser\s*=", r"playwright",
                     r"pip install -e '\.\[browser\]'"],
        "all": True,
    },
    "storage-state-path": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"\.fb-session", r"storage_state\.json",
                     r"storage_state"],
        "all": True,
    },
    "playwright-import-error": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"except ImportError", r"RuntimeError",
                     r"Playwright not installed"],
    },
    "chromium-launch": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"chromium\.launch\(headless=headless\)",
                     r"page\.goto\(FB_MARKETPLACE_CREATE_URL"],
    },
    "session-dir-created": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"session_dir\.mkdir\(parents=True, exist_ok=True\)"],
    },
    "result-dict-fields": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"\"item_id\"", r"\"title\"", r"\"photo_count\"",
                     r"\"dry_run\"", r"\"submitted\""],
    },
    "title-from-build-title": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"\"title\": build_title\(item\)"],
    },
    "form-fill-selectors-scaffold": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "_fill_marketplace_form",
        "patterns": [r"_try_fill\(\"Title\"", r"_try_fill\(\"Price\"",
                     r"_try_fill\(\"Description\"",
                     r"set_input_files"],
        "human_question": ("Selectors are active code now, but live Facebook "
                           "selector drift still needs a headed logged-in run."),
    },
    "photo-loop-scaffold": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "_fill_marketplace_form",
        "patterns": [r"if item\.photos", r"for p in item\.photos",
                     r"set_input_files"],
        "human_question": ("Photo upload path is wired; live headed run should "
                           "confirm Facebook accepts the selector."),
    },
    "dry-run-stops-before-submit": {
        "type": "func",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "name": "post_with_playwright",
        "patterns": [r"dry_run", r"submitted\": False",
                     r"Stopped before submit"],
    },
    "dry-run-default-true": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"dry_run: bool = True", r"dry_run=True"],
        "all": True,
    },
    "submit-not-implemented-guard": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"Submit not implemented", r"decision\.md selector approval"],
        "all": True,
    },
    "publish-click-scaffold": {
        "type": "human_review",
        "reason": ("No Publish click scaffold should be enabled until selector "
                   "approval exists; confirm whether a commented final-step "
                   "placeholder is desired before treating this as missing."),
        "human_question": ("Should the graph require a commented Publish-click "
                           "placeholder, or is the stronger not-implemented "
                           "submit guard the intended evidence?"),
    },
    "submitted-flag-false-until-wired": {
        "type": "symbol",
        "files": ["src/sell_valuables/post_to_fb.py"],
        "patterns": [r"\"submitted\": False", r"Submit not implemented"],
        "all": True,
    },
    "human-review-required-policy": {
        "type": "project_policy",
        "path": "graphs/sell-valuables/project.yaml",
        "patterns": [r"require_human_review_before_overnight:\s*true"],
    },

    # ── sell-valuables: docs + tests ──
    "imessage-shortcuts-doc-exists": {
        "type": "symbol",
        "files": ["docs/imessage-shortcuts.md"],
        "patterns": [r"Apple does not expose iMessage to Python",
                     r"manual folder workflow|Manual"],
        "all": True,
    },
    "manual-steps-documented": {
        "type": "symbol",
        "files": ["docs/imessage-shortcuts.md"],
        "patterns": [r"incoming/YYYY-MM-DD-slug", r"photos/",
                     r"description\.txt", r"sell-listing", r"sell-post-fb"],
        "all": True,
    },
    "shortcuts-recommended-flow": {
        "type": "symbol",
        "files": ["docs/imessage-shortcuts.md"],
        "patterns": [r"Shortcuts", r"Share sheet", r"slug", r"iCloud Drive",
                     r"description\.txt"],
        "all": True,
    },
    "later-options-noted": {
        "type": "symbol",
        "files": ["docs/imessage-shortcuts.md"],
        "patterns": [r"Twilio", r"BlueBubbles"],
        "all": True,
    },
    "incoming-readme-cross-link": {
        "type": "symbol",
        "files": ["incoming/README.md"],
        "patterns": [r"docs/imessage-shortcuts\.md"],
        "all": True,
    },
    "sample-item-fixture": {
        "type": "paths",
        "paths": ["tests/fixtures/sample-item/description.txt",
                  "tests/fixtures/sample-item/meta.yaml"],
    },
    "test-load-item-fixture": {
        "type": "symbol",
        "files": ["tests/test_listing.py"],
        "patterns": [r"def test_load_item_fixture", r"item_id",
                     r"description", r"price_hint"],
        "all": True,
    },
    "test-build-title-first-line": {
        "type": "symbol",
        "files": ["tests/test_listing.py"],
        "patterns": [r"def test_build_title_from_first_line", r"build_title"],
        "all": True,
    },
    "test-listing-markdown-content": {
        "type": "symbol",
        "files": ["tests/test_listing.py"],
        "patterns": [r"test_listing_markdown_includes_price_and_fb_url",
                     r"\*\*Price:\*\*", r"facebook\.com/marketplace/create",
                     r"pickup"],
        "all": True,
    },
    "pytest-dev-extra": {
        "type": "symbol",
        "files": ["pyproject.toml", "README.md"],
        "patterns": [r"dev\s*=", r"pytest", r"pip install -e '\.\[dev\]'"],
        "all": True,
    },
}

def probe_for(node_id: str, criterion_id: str) -> dict | None:
    """Return node-specific probe first, then shared criterion probe."""
    return CHECK_PROBES.get(f"{node_id}:{criterion_id}") or CHECK_PROBES.get(criterion_id)


def slug_keywords(criterion_text: str) -> list[str]:
    """Fallback probe targets derived from the criterion text itself.

    Used when CHECK_PROBES has no explicit entry: extract identifiers named in
    the criterion and look for them in source files that match the repo layout.
    Deterministic and conservative — if nothing matches, the check is
    `indeterminate`, not `fail`.
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", criterion_text)
    stop = {"the", "and", "for", "with", "from", "when", "not", "are",
            "must", "via", "into", "only", "that", "this", "under",
            "clear", "error", "returns", "non-zero", "installed", "against",
            "missing", "invalid", "filesystem", "produce", "helpers",
            "exists", "writes", "reads", "accepts", "returns", "spawns",
            "mode", "target", "repo", "cwd", "loaded", "valid", "receipt",
            "populated", "passes", "regressions"}
    out: list[str] = []
    for token in tokens:
        if token.lower() in stop:
            continue
        if (
            "_" in token
            or "-" in token
            or token.startswith(("aa", "AA"))
            or any(ch.isupper() for ch in token[1:])
        ):
            out.append(token)
    return out


def mentioned_paths_from_text(text: str) -> list[str]:
    """Return repo-looking paths mentioned in criterion text.

    Two shapes: slash-containing relative paths with any extension
    (``gate-smoke/a.txt``, ``docs/guide.rst``), and bare filenames with a
    known source/config extension (``echo.py``). The extension allowlist
    alone was a blind spot — criteria about .txt/.csv/.sql artifacts were
    never recognized as path-bearing at all.
    """
    paths: list[str] = []
    # Slash-containing relative paths, any extension.
    for raw in re.findall(r"[\w.-]+(?:/[\w.-]+)+\.\w+", text):
        paths.append(raw.strip("`'\".,);:"))
    # Bare filenames with known extensions.
    for raw in re.findall(r"[\w./-]+\.(?:py|ts|tsx|js|json|toml|yaml|yml|zsh|md)", text):
        paths.append(raw.strip("`'\".,);:"))
    return sorted(set(paths))


def _decode_escaped(text: str) -> str:
    """Interpret common escape sequences in a criterion's quoted literal
    (``\\n``, ``\\t``, ``\\r``) so it can be compared against file bytes.
    Conservative manual replacement — not unicode_escape, which mangles
    non-ASCII text."""
    return text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


def _path_content_check(cid: str, text: str, repo: Path,
                        existing: list[str]) -> CriterionCheck | None:
    """Deterministic content proof for criteria that name exactly one
    existing path and quote exactly one expected literal.

    "exactly" in the criterion → full-content equality; otherwise substring
    containment. Returns None when the shape does not fit (caller falls
    through to the keyword probe).
    """
    if len(existing) != 1:
        return None
    quoted = re.findall(r'"([^"\n]+)"', text)
    if len(quoted) != 1:
        return None
    rel = existing[0]
    expected = _decode_escaped(quoted[0])
    content = read_repo_file(repo, rel)
    if content is None:
        return None
    exact = "exactly" in text.lower()
    matched = (content == expected) if exact else (expected in content)
    how = "exact-content" if exact else "substring"
    if matched:
        return CriterionCheck(
            id=cid, criterion=text, status="pass",
            confidence=0.9, method="path_content_check",
            evidence=[f"{rel} matches quoted literal ({how})"],
            reasoning=(f"Read {rel} and verified it "
                       f"{'equals' if exact else 'contains'} the criterion's "
                       f"quoted literal ({how} check)."),
            mismatch_kind="", mismatch_detail="",
            needs_evidence=False, human_question="",
        )
    return CriterionCheck(
        id=cid, criterion=text, status="fail",
        confidence=0.85, method="path_content_check",
        evidence=[
            f"{rel} content does not match quoted literal ({how})",
            f"expected: {expected!r}"[:200],
            f"actual:   {content!r}"[:200],
        ],
        reasoning=(f"Read {rel}; its content does not "
                   f"{'equal' if exact else 'contain'} the criterion's "
                   f"quoted literal."),
        mismatch_kind="content", mismatch_detail=rel,
        needs_evidence=False,
        human_question="Is the expected content stale, or is the file wrong?",
    )


def existing_paths_from_text(repo: Path, text: str) -> list[str]:
    """Return existing repo-relative paths mentioned in criterion text."""
    return sorted({p for p in mentioned_paths_from_text(text) if (repo / p).is_file()})


def fallback_scan_files(repo: Path, text: str = "") -> list[str]:
    """Candidate source files for unregistered deterministic probes."""
    explicit = existing_paths_from_text(repo, text)
    if explicit:
        return explicit

    candidates: list[Path] = []
    lib_dir = repo / "lib"
    if lib_dir.is_dir():
        candidates.extend(sorted(lib_dir.glob("*.zsh")))
    for dirname, patterns in (
        ("src", ("*.py", "*.ts", "*.tsx", "*.js")),
        ("scripts", ("*.py", "*.ts", "*.tsx", "*.js")),
        ("tests", ("*.py", "*.ts", "*.tsx", "*.js")),
    ):
        base = repo / dirname
        if base.is_dir():
            for pattern in patterns:
                candidates.extend(sorted(base.rglob(pattern)))
    return sorted({p.relative_to(repo).as_posix() for p in candidates if p.is_file()})


def read_repo_file(repo: Path, rel: str) -> str | None:
    p = repo / rel
    if not p.is_file():
        return None
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None


def grep_all(haystacks: list[str], patterns: list[str], want_all: bool):
    """Return (matched: bool, evidence: list[str])."""
    hits: dict[str, list[str]] = {p: [] for p in patterns}
    for p in patterns:
        rx = re.compile(p)
        for hay in haystacks:
            for m in rx.finditer(hay):
                line_no = hay.count("\n", 0, m.start()) + 1
                hits[p].append(f"line {line_no}: {m.group(0)!r}")
    if want_all:
        matched = all(hits[p] for p in patterns)
    else:
        matched = any(hits[p] for p in patterns)
    evidence: list[str] = []
    for p in patterns:
        if hits[p]:
            evidence.append(f"{p} -> {hits[p][0]}")
    return matched, evidence


def parse_targets_conf(text: str) -> dict[str, dict[str, str]]:
    """Parse aa-cli targets.conf into {target: {tier: command}}.

    Rows look like: `grk  default  sync  grk` or `codex default async __codex_async # alias`.
    Comment lines (start with #) and blank lines are skipped. An inline
    trailing comment (after the command) is stripped.
    """
    out: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        # Support both 3-column (target mode command, tier=default) and
        # 4-column (target tier mode command) legacy shapes.
        if len(parts) >= 4 and parts[1] in ("default", "speed", "frontier"):
            target, tier, _mode, command = parts[0], parts[1], parts[2], parts[3]
        else:
            target, _mode, command = parts[0], parts[1], parts[2]
            tier = "default"
        out.setdefault(target, {})[tier] = command
    return out


# ── Criterion evaluation ───────────────────────────────────────────────────

def evaluate_criterion(
    item: dict,
    repo: Path,
    node_id: str = "",
    *,
    config_root: Path | None = None,
) -> CriterionCheck:
    cid = item.get("id", "<no-id>")
    text = item.get("criterion", "")

    # ── command_proof: explicit command in criterion dict runs FIRST ──
    cmd = item.get("command", "")
    if cmd:
        timeout = int(os.environ.get("GDDP_COMMAND_PROOF_TIMEOUT", "300"))
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=repo, capture_output=True,
                text=True, timeout=timeout,
            )
            exit_code = proc.returncode
            combined_output = (proc.stdout + proc.stderr).strip()
            evidence = [
                f"$ {cmd}",
                f"exit {exit_code}",
                combined_output[-1500:] if combined_output else "",
            ]
            if exit_code == 0:
                return CriterionCheck(
                    id=cid, criterion=text, status="pass",
                    confidence=0.95, method="command_proof",
                    evidence=evidence,
                    reasoning=f"Ran `{cmd}` (exit 0). Command passed.",
                    mismatch_kind="", mismatch_detail="",
                    needs_evidence=False, human_question="",
                )
            else:
                return CriterionCheck(
                    id=cid, criterion=text, status="fail",
                    confidence=0.9, method="command_proof",
                    evidence=evidence,
                    reasoning=f"Ran `{cmd}` (exit {exit_code}). Command failed.",
                    mismatch_kind="", mismatch_detail="",
                    needs_evidence=False, human_question="",
                )
        except subprocess.TimeoutExpired:
            return CriterionCheck(
                id=cid, criterion=text, status="indeterminate",
                confidence=0.3, method="command_proof_error",
                evidence=[f"$ {cmd}", f"timed out after {timeout}s"],
                reasoning=f"`{cmd}` timed out after {timeout}s.",
                mismatch_kind="", mismatch_detail="",
                needs_evidence=False, human_question="",
            )
        except OSError as exc:
            return CriterionCheck(
                id=cid, criterion=text, status="indeterminate",
                confidence=0.3, method="command_proof_error",
                evidence=[f"$ {cmd}", f"OSError: {exc}"],
                reasoning=f"`{cmd}` could not run: {exc}.",
                mismatch_kind="", mismatch_detail="",
                needs_evidence=False, human_question="",
            )

    probe = probe_for(node_id, cid)

    if probe is None:
        # Fallback: keyword probe across files implied by the repo layout.
        kws = slug_keywords(text)
        mentioned_paths = mentioned_paths_from_text(text)
        existing_paths = [p for p in mentioned_paths if (repo / p).is_file()]
        missing_paths = [p for p in mentioned_paths if not (repo / p).is_file()]
        if mentioned_paths and not existing_paths:
            return CriterionCheck(
                id=cid, criterion=text, status="indeterminate",
                confidence=0.2, method="path_mentioned_missing",
                evidence=[f"{p} absent" for p in missing_paths],
                reasoning=("The criterion names source path(s) that are not "
                           "present in the checkout. The harness did not scan "
                           "unrelated files as substitutes."),
                mismatch_kind="source_path",
                mismatch_detail=", ".join(f"{p} absent" for p in missing_paths),
                needs_evidence=False,
                human_question=("Is the criterion path stale, or has the "
                                "implementation not landed yet?"),
            )
        content_check = _path_content_check(cid, text, repo, existing_paths)
        if content_check is not None:
            return content_check
        if not kws:
            return CriterionCheck(
                id=cid, criterion=text, status="indeterminate",
                confidence=0.1, method="no_probe", evidence=[],
                reasoning=("No deterministic probe is registered for this "
                           "criterion and no usable identifiers were found "
                           "in its text. Needs a human or an explicit probe."),
                mismatch_kind="", mismatch_detail="",
                needs_evidence=False, human_question="",
            )
        scan_files = fallback_scan_files(repo, text)
        named = [(f, read_repo_file(repo, f) or "") for f in scan_files]
        patterns = [re.escape(k) for k in kws]
        matched, evidence = grep_all([h for _, h in named], patterns,
                                      want_all=False)
        # Keyword scan is inherently weak evidence — finding strings in files
        # does not prove the criterion is satisfied. Always mark indeterminate
        # so the semantic layer gets a chance to judge. The confidence reflects
        # how strong the keyword signal is (0.5 = found strings, 0.2 = nothing).
        status = "indeterminate"
        scope = ", ".join(scan_files[:4]) + ("..." if len(scan_files) > 4 else "")
        if missing_paths:
            evidence.extend(f"{p} absent" for p in missing_paths)
        return CriterionCheck(
            id=cid, criterion=text, status=status,
            confidence=0.5 if matched else 0.2,
            method="keyword_scan_source",
            evidence=(evidence or [f"no hit in source scan ({scope or 'no files'})"])[:6],
            reasoning=(f"Scanned source files ({scope or 'none'}) for identifiers named in the "
                       f"criterion ({', '.join(kws)}). "
                       + ("String match found — semantic investigation needed to confirm." if matched
                          else "No complete match — "
                          "absence could mean rewording, missing path, or missing implementation.")),
            mismatch_kind="source_path" if missing_paths else "",
            mismatch_detail=", ".join(f"{p} absent" for p in missing_paths),
            needs_evidence=False,
            human_question=("Is the criterion path stale, or has the implementation not landed yet?")
            if missing_paths else "",
        )

    ptype = probe["type"]
    mk = probe.get("mismatch_kind", "")
    hq = probe.get("human_question", "")
    mismatch_detail = ""
    needs_evidence = False

    if ptype == "tier_distinct":
        return eval_tier_distinct(cid, text, probe, repo, mk, hq)

    if ptype == "human_review":
        reason = probe.get("reason", "This criterion requires human review.")
        return CriterionCheck(
            id=cid, criterion=text, status="indeterminate",
            confidence=0.8, method=ptype, evidence=[reason],
            reasoning=reason, mismatch_kind=mk or "human_review",
            mismatch_detail=reason,
            needs_evidence=False,
            human_question=hq or probe.get("human_question", ""))

    if ptype == "path":
        rel = probe["path"]
        exists = (repo / rel).exists()
        also_grep = probe.get("also_grep", [])
        evidence: list[str] = [f"{rel} {'exists' if exists else 'absent'}"]
        grep_ok = True
        if exists and also_grep:
            body = read_repo_file(repo, rel) or ""
            gm, gev = grep_all([body], also_grep, want_all=False)
            grep_ok = gm
            evidence.extend(gev or [f"none of {also_grep} found in {rel}"])
        if exists and grep_ok:
            status, conf, reasoning = "pass", 0.9, (
                f"Path {rel} exists and contains expected marker(s) "
                f"{also_grep or '(none required)'}.")
        elif exists and not grep_ok:
            status, conf, reasoning = "indeterminate", 0.5, (
                f"Path {rel} exists but none of {also_grep} found in it.")
            mk = mk or "wording"
            mismatch_detail = f"{rel} exists but lacks marker(s) {also_grep}"
        else:
            status, conf = "indeterminate", 0.4
            reasoning = f"Path {rel} absent."
            if probe.get("needs_evidence_when_absent"):
                needs_evidence = True
                reasoning += (f" Needs {probe.get('evidence_what', 'evidence')} "
                              "which was not found.")
        return CriterionCheck(
            id=cid, criterion=text, status=status, confidence=conf,
            method=ptype, evidence=evidence[:12], reasoning=reasoning,
            mismatch_kind=mk, mismatch_detail=mismatch_detail,
            needs_evidence=needs_evidence, human_question=hq)

    if ptype == "paths":
        paths = probe["paths"]
        missing_paths = [p for p in paths if not (repo / p).exists()]
        evidence = [f"{p} {'exists' if (repo / p).exists() else 'absent'}"
                    for p in paths]
        return CriterionCheck(
            id=cid, criterion=text,
            status="pass" if not missing_paths else "fail",
            confidence=0.95 if not missing_paths else 0.7,
            method=ptype, evidence=evidence,
            reasoning=("All required paths exist." if not missing_paths
                       else "Missing required path(s): "
                       + ", ".join(missing_paths)),
            mismatch_kind=mk or ("source_path" if missing_paths else ""),
            mismatch_detail=", ".join(missing_paths),
            needs_evidence=False, human_question=hq)

    if ptype == "project_policy":
        rel = probe["path"]
        root = config_root if config_root is not None else repo
        policy_file = root / rel
        body = policy_file.read_text(errors="replace") if policy_file.is_file() else None
        evidence = [f"{rel} {'exists' if body is not None else 'absent'}"]
        if body is None:
            return CriterionCheck(
                id=cid, criterion=text, status="fail", confidence=0.6,
                method=ptype, evidence=evidence,
                reasoning=f"Project policy file {rel} is missing.",
                mismatch_kind=mk or "source_path",
                mismatch_detail=f"{rel} missing",
                needs_evidence=False, human_question=hq)
        matched, ev = grep_all([body], probe["patterns"], want_all=True)
        evidence.extend(ev)
        return CriterionCheck(
            id=cid, criterion=text,
            status="pass" if matched else "fail",
            confidence=0.9 if matched else 0.7, method=ptype,
            evidence=evidence[:12],
            reasoning=(f"Checked project policy in {rel}. "
                       + ("Policy present." if matched
                          else "Policy marker missing.")),
            mismatch_kind=mk or ("" if matched else "project_policy"),
            mismatch_detail=("" if matched
                             else f"{rel} lacks {probe['patterns']}"),
            needs_evidence=False, human_question=hq)

    files = probe["files"]
    contents = [(f, read_repo_file(repo, f)) for f in files]
    missing = [f for f, c in contents if c is None]
    present = [(f, c) for f, c in contents if c is not None]
    evidence: list[str] = []
    if missing:
        evidence.append(f"missing files: {', '.join(missing)}")
        mk = mk or "source_path"
        mismatch_detail = (f"expected files not found in repo: "
                           f"{', '.join(missing)}")
    bodies = [c for _, c in present]

    if ptype in ("symbol", "any_of"):
        patterns = probe["patterns"]
        want_all = probe.get("all", ptype == "symbol")
        matched, ev = grep_all(bodies, patterns, want_all=want_all)
        for fname, _ in present:
            evidence.append(f"in {fname}")
        evidence.extend(ev)
        status = "pass" if matched else "fail"
        conf = 0.9 if matched else (0.3 if not present else 0.7)
        reasoning = (f"Probed {', '.join(files)} for "
                     f"{'all of' if want_all else 'any of'} "
                     f"{patterns}. " + ("All present." if matched
                                        else "Pattern(s) missing."))
    elif ptype == "func":
        fname = probe["name"]
        patterns = [rf"\b{re.escape(fname)}\s*\(", *probe.get("patterns", [])]
        matched, ev = grep_all(bodies, patterns, want_all=True)
        for f, _ in present:
            evidence.append(f"in {f}")
        evidence.extend(ev)
        status = "pass" if matched else "fail"
        conf = 0.9 if matched else 0.4
        reasoning = (f"Looked for function `{fname}()` plus body markers "
                     f"{probe.get('patterns', [])} in {', '.join(files)}. "
                     + ("Defined and uses expected helpers." if matched
                        else "Function or markers not found."))
    else:
        status, conf, matched, reasoning = ("indeterminate", 0.0, False,
                                            "unknown probe type")

    return CriterionCheck(
        id=cid, criterion=text, status=status, confidence=conf,
        method=ptype, evidence=evidence[:12], reasoning=reasoning,
        mismatch_kind=mk, mismatch_detail=mismatch_detail,
        needs_evidence=needs_evidence, human_question=hq)


def eval_tier_distinct(cid, text, probe, repo, mk, hq):
    """Evaluate a tier_distinct probe against targets.conf.

    Checks the named target exists with required tiers, that tiers in
    require_distinct resolve to DISTINCT commands, and that aliases resolve
    to the same command as the canonical target. Surfaces tier_distinct and
    alias_integration mismatches specifically (not flat pass/fail).
    """
    rel = probe.get("file", "targets.conf")
    target = probe["target"]
    body = read_repo_file(repo, rel)
    evidence = []
    mismatch_detail = ""

    if body is None:
        return CriterionCheck(
            id=cid, criterion=text, status="indeterminate", confidence=0.3,
            method="tier_distinct", evidence=[rel + " absent"],
            reasoning=rel + " not found in repo.",
            mismatch_kind="source_path", mismatch_detail=rel + " not found",
            needs_evidence=False, human_question=hq)

    targets = parse_targets_conf(body)
    tiers = targets.get(target, {})
    tier_parts = []
    for t in sorted(tiers):
        tier_parts.append(t + "=" + str(tiers[t]))
    tier_str = ", ".join(tier_parts) if tier_parts else "NOT FOUND"
    evidence.append(rel + ": " + target + " -> " + tier_str)

    if not tiers:
        return CriterionCheck(
            id=cid, criterion=text, status="fail", confidence=0.5,
            method="tier_distinct", evidence=evidence,
            reasoning="Target '" + target + "' not registered in " + rel + ".",
            mismatch_kind=(mk or "source_path"),
            mismatch_detail=target + " has no rows in " + rel,
            needs_evidence=False, human_question=hq)

    require_present = probe.get("require_present", [])
    missing_tiers = [t for t in require_present if t not in tiers]
    if missing_tiers:
        evidence.append("missing tiers for " + target + ": "
                        + ", ".join(missing_tiers))
        return CriterionCheck(
            id=cid, criterion=text, status="fail", confidence=0.5,
            method="tier_distinct", evidence=evidence,
            reasoning=(target + " missing required tier(s) "
                       + str(missing_tiers) + "."),
            mismatch_kind=(mk or "source_path"),
            mismatch_detail=(target + " missing tiers " + str(missing_tiers)),
            needs_evidence=False, human_question=hq)
    require_distinct = probe.get("require_distinct")
    marker = probe.get("marker")
    nondistinct = []
    if require_distinct:
        cmds = {}
        for t in require_distinct:
            if t in tiers:
                cmds[t] = tiers[t]
        by_cmd = {}
        for t in cmds:
            key = cmds[t] if cmds[t] else "none"
            by_cmd.setdefault(key, []).append(t)
        for cmd in by_cmd:
            ts = by_cmd[cmd]
            if len(ts) > 1:
                nondistinct.append("+".join(ts) + " -> " + cmd)
        if marker:
            has_marker = any(c and re.search(marker, c) for c in cmds.values())
            if not has_marker:
                evidence.append("required marker " + marker + " not in any " + target + " tier command")
    aliases = probe.get("aliases", [])
    alias_problems = []
    if aliases:
        canon_cmd = tiers.get("default")
        for al in aliases:
            al_tiers = targets.get(al, {})
            al_cmd = al_tiers.get("default")
            if not al_tiers:
                alias_problems.append("alias " + al + " not in " + rel)
            elif al_cmd != canon_cmd:
                alias_problems.append("alias " + al + " default=" + str(al_cmd) + " != " + target + " default=" + str(canon_cmd))
    marker_ok = True
    if marker:
        marker_ok = any(c and re.search(marker, c) for c in tiers.values())
    ok = (not nondistinct) and (not alias_problems) and marker_ok
    if ok:
        status = "pass"
        conf = 0.85
        reasoning = target + " tiers resolve as expected in " + rel + "; no distinctness, marker, or alias problems."
    else:
        status = "indeterminate"
        conf = 0.6
        parts = []
        if nondistinct:
            parts.append("non-distinct tiers: " + "; ".join(nondistinct))
        if alias_problems:
            parts.append("alias issues: " + "; ".join(alias_problems))
        mismatch_detail = "; ".join(parts) if parts else "tier/alias mismatch"
        joined = "; ".join(parts) if parts else "mismatch"
        reasoning = target + " in " + rel + ": " + joined + ". Code partially disagrees with the criterion; needs human decision on whether the gap is intended."
        if not mk:
            mk = "alias_integration" if alias_problems else "tier_distinct"
        if not hq:
            hq = target + " tier/alias config in " + rel + " does not fully match the criterion. Is the gap intended?"
    return CriterionCheck(
        id=cid, criterion=text, status=status, confidence=conf,
        method="tier_distinct", evidence=evidence[:12], reasoning=reasoning,
        mismatch_kind=mk, mismatch_detail=mismatch_detail,
        needs_evidence=False, human_question=hq)



