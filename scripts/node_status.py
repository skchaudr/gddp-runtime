"""
node_status.py — Inspect and set job/node queue state (human-operated).

Usage:
    gddp jobs list [--state awaiting_review]
    gddp jobs show <job_id | node_id> [--full]
    gddp jobs results [--all]
    gddp jobs set <job_id | node_id> <state> --reason "..."

States (canon: gddp-config schemas/v1/queue_record.yaml):
    intake classified blocked ready running awaiting_result
    awaiting_review complete failed deferred cancelled

What `set` does:
    1. Shows current state and asks for confirmation
    2. Updates jobs.queue_state (+ jobs.status when the state is a valid
       job status) and any queue_records rows for the job
    3. Writes a decision_results audit row — action 'accept_node' for
       awaiting_review → complete, 'manual_status_change' otherwise

Output is TTY-aware: colour and glyphs on an interactive terminal, plain
text when piped or when NO_COLOR is set — so grep/pipes and tests stay stable.
"""

import argparse
import json
import os
import sqlite3
import sys
import termios
import tty
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Same-dir imports (node_status_history) when run as scripts/node_status.py
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

# Design language: airy tables (heavy header rule, no vertical clutter) for
# lists, rounded cards for single-record detail. Keeps a cohesive look.
_TABLE_BOX = box.SIMPLE_HEAVY
_CARD_BOX = box.ROUNDED

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"

# Canon queue states — keep in sync with gddp-config schemas/v1/queue_record.yaml
QUEUE_STATES = [
    "intake", "classified", "blocked", "ready", "running",
    "awaiting_result", "awaiting_review", "complete", "failed",
    "deferred", "cancelled",
]
# jobs.status is a narrower enum; only mirror queue_state into it when valid
JOB_STATUSES = {"ready", "running", "awaiting_result", "awaiting_review", "complete", "failed"}

# soft_wrap keeps detail lines intact (no reflow) so piped output and the
# substring-asserting tests see exactly what a human sees, minus styling.
# Console auto-disables colour when stdout is not a TTY and honours NO_COLOR.
# When not a terminal (piped to a file / grep / tests), rich would otherwise
# clamp to 80 cols and truncate job_ids and paths — so we hand it a wide width
# and keep identifiers copy/grep-able. Interactive terminals keep their size.
_PIPE_WIDTH = None if sys.stdout.isatty() else 200
console = Console(soft_wrap=True, highlight=False, width=_PIPE_WIDTH)
err_console = Console(stderr=True, soft_wrap=True, highlight=False)


# --- presentation helpers --------------------------------------------------

# Colour + glyph vocabulary shared by queue states and evaluator verdicts, so
# "failed", "fail", and a red integrity finding all read the same at a glance.
_GREEN  = "bold green"
_RED    = "bold red"
_YELLOW = "bold yellow"
_CYAN   = "bold cyan"
_DIM    = "dim"

_STATE_STYLE = {
    "complete": _GREEN,
    "running": _CYAN,
    "ready": _CYAN,
    "awaiting_review": _YELLOW,
    "awaiting_result": _YELLOW,
    "blocked": _YELLOW,
    "deferred": _DIM,
    "cancelled": _DIM,
    "failed": _RED,
    "intake": _DIM,
    "classified": _DIM,
}

_VERDICT_STYLE = {
    "pass": _GREEN,
    "judged_pass": _GREEN,
    "complete": _GREEN,
    "fail": _RED,
    "failed": _RED,
    "reject": _RED,
    "needs-human-review": _YELLOW,
    "needs_human_review": _YELLOW,
    "review": _YELLOW,
    "unknown": _DIM,
    "indeterminate": _DIM,
}

_SEVERITY_STYLE = {
    "critical": _RED, "high": _RED, "error": _RED,
    "medium": _YELLOW, "warning": _YELLOW, "warn": _YELLOW,
    "low": _CYAN, "info": _DIM,
}


def _state_style(state) -> str:
    return _STATE_STYLE.get((state or "").lower(), "")


def _verdict_style(verdict) -> str:
    return _VERDICT_STYLE.get((verdict or "").lower().strip(), "")


def _glyph(verdict) -> str:
    """A leading status glyph for a verdict/state (blank if unknown)."""
    style = _verdict_style(verdict) or _state_style(verdict)
    if style == _GREEN:
        return "✔"
    if style == _RED:
        return "✖"
    if style == _YELLOW:
        return "▲"
    if style == _CYAN:
        return "●"
    return "·"


def fail(msg: str, code: int = 1):
    """Print an error to stderr with weight, then exit."""
    err_console.print(Text(f"✖ {msg}", style=_RED))
    raise SystemExit(code)


def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def resolve_job(con, ref: str):
    """Accept a job_id or node_id; node_id must match exactly one job."""
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (ref,)).fetchone()
    if job:
        return job
    rows = con.execute(
        "SELECT * FROM jobs WHERE node_id = ? ORDER BY created_at DESC", (ref,)
    ).fetchall()
    if not rows:
        fail(f"No job found for '{ref}' (tried job_id, then node_id).")
    if len(rows) > 1:
        console.print(Text(f"'{ref}' matches {len(rows)} jobs — use a job_id:", style=_YELLOW))
        table = Table(box=_TABLE_BOX, show_edge=False, pad_edge=False)
        table.add_column("job_id", style="bold")
        table.add_column("state")
        table.add_column("created")
        for r in rows:
            table.add_row(
                r["job_id"],
                Text(r["queue_state"], style=_state_style(r["queue_state"])),
                str(r["created_at"]),
            )
        console.print(table)
        raise SystemExit(1)
    return rows[0]


def cmd_list(args):
    con = connect()
    q = "SELECT job_id, node_id, queue_state, attempt, max_attempts, created_at FROM jobs"
    params = ()
    if args.state:
        q += " WHERE queue_state = ?"
        params = (args.state,)
    q += " ORDER BY created_at DESC"
    rows = con.execute(q, params).fetchall()
    if not rows:
        console.print(Text("No jobs." + (f" (state={args.state})" if args.state else ""), style=_DIM))
        return

    title = "jobs" + (f"  ·  state={args.state}" if args.state else "")
    table = Table(
        title=title, box=_TABLE_BOX, title_justify="left", title_style="bold",
        caption=f"{len(rows)} job(s)", caption_justify="left", caption_style=_DIM,
        padding=(0, 2, 0, 0), pad_edge=False,
    )
    table.add_column("", width=1, no_wrap=True)  # glyph
    table.add_column("state", no_wrap=True)
    table.add_column("job_id", style="bold", no_wrap=True)
    table.add_column("node", no_wrap=True)
    table.add_column("attempt", justify="right", no_wrap=True)
    table.add_column("created", style=_DIM, no_wrap=True)
    for r in rows:
        style = _state_style(r["queue_state"])
        table.add_row(
            Text(_glyph(r["queue_state"]), style=style),
            Text(r["queue_state"], style=style),
            r["job_id"],
            r["node_id"] or "-",
            f"{r['attempt']}/{r['max_attempts']}",
            (r["created_at"] or "")[:10],
        )
    console.print(table)


def parse_check(row):
    try:
        return json.loads(row["acceptance_check"]) if row["acceptance_check"] else {}
    except json.JSONDecodeError:
        return {}


def _kv(label: str, value, value_style: str = "") -> Text:
    """A right-aligned 'label: value' detail line, label dimmed, value styled.

    Substrings (e.g. 'coverage: criteria=medium ...') stay contiguous so
    piped/captured output remains stable for greps and tests.
    """
    text = Text(label, style=_DIM)
    text.append(value if isinstance(value, str) else str(value), style=value_style)
    return text


def print_evaluation(check, full=False):
    """Print the evaluator's output for one result row — the thing under review."""
    if not check:
        console.print(Text("          (no evaluator output on this result)", style=_DIM))
        return
    integrity = check.get("integrity") or {}
    verdict = check.get("verdict")
    header = Text("         verdict: ", style=_DIM)
    header.append(f"{_glyph(verdict)} {verdict}", style=_verdict_style(verdict))
    header.append(
        f"  (criteria: {check.get('criteria_verdict')} @ {check.get('criteria_confidence')}, "
        f"integrity: {integrity.get('verdict')} @ {integrity.get('confidence')})",
        style=_DIM,
    )
    console.print(header)
    for f in check.get("criteria_findings") or []:
        line = Text("       criterion: ", style=_DIM)
        line.append(str(f.get("criterion_id")))
        line.append("  ->  ", style=_DIM)
        line.append(str(f.get("judgment")), style=_verdict_style(f.get("judgment")))
        console.print(line)
        for ev in f.get("evidence") or []:
            console.print(Text(f"                  evidence: {ev}", style=_DIM))
    for f in integrity.get("findings") or []:
        sev = f.get("severity")
        line = Text("       integrity: ", style=_DIM)
        line.append(f"[{sev}] ", style=_SEVERITY_STYLE.get((sev or "").lower(), ""))
        line.append(str(f.get("summary")))
        console.print(line)
    # Phase 3: graph observations (forward-looking, do not affect verdict)
    for o in integrity.get("graph_observations") or []:
        sev = o.get("severity")
        line = Text("       graph obs: ", style=_DIM)
        line.append(f"[{sev}] ", style=_SEVERITY_STYLE.get((sev or "").lower(), ""))
        line.append(str(o.get("summary")))
        console.print(line)
    if check.get("required_next_action"):
        console.print(_kv(
            "     next action: ",
            f"{check['required_next_action']}  (evaluator template, not a decision)",
        ))
    # Phase 1 provenance: show the exact tree the evaluator judged.
    tree_sha = check.get("evaluated_tree_sha")
    commit_sha = check.get("evaluated_commit_sha")
    merge_sha = check.get("merge_commit_sha")
    if commit_sha or tree_sha or merge_sha:
        if commit_sha:
            matched = bool(merge_sha and commit_sha == merge_sha)
            match = "  (match)" if matched else "  (mismatch)" if merge_sha else ""
            line = Text("      provenance: ", style=_DIM)
            line.append(f"commit={commit_sha}  merge={merge_sha or 'n/a'}")
            line.append(match, style=_GREEN if matched else (_RED if merge_sha else ""))
            console.print(line)
        else:
            console.print(_kv(
                "      provenance: ",
                f"tree={tree_sha or 'n/a'}  merge={merge_sha or 'n/a'}  (different SHA types; not compared)",
            ))
    if check.get("pr_ref"):
        console.print(_kv("            PR: ", str(check["pr_ref"]), _CYAN))
    # Phase 2 coverage: quick signal for the operator
    cov = check.get("context_coverage")
    if cov:
        crit_raw = cov.get("criteria", "n/a")
        crit = crit_raw.get("rating", "n/a") if isinstance(crit_raw, dict) else crit_raw
        integ = cov.get("integrity", {}).get("rating", "n/a") if isinstance(cov.get("integrity"), dict) else "n/a"
        console.print(_kv(
            "       coverage: ",
            f"criteria={crit}  integrity={integ}  overall={cov.get('overall', 'n/a')}",
        ))
    lane_status = check.get("lane_status") or {}
    harness_error = check.get("harness_error") or {}
    if lane_status:
        console.print(_kv(
            "    lane status: ",
            f"criteria={lane_status.get('criteria', 'n/a')}  integrity={lane_status.get('integrity', 'n/a')}",
        ))
    for lane in ("criteria", "integrity"):
        if harness_error.get(lane):
            line = Text("  harness error: ", style=_DIM)
            line.append(f"{lane}={harness_error[lane]}", style=_RED)
            console.print(line)
    if check.get("receipt_path"):
        console.print(_kv("         receipt: ", str(check["receipt_path"]), _DIM))
    if full and integrity.get("reasoning"):
        console.print(_kv("       reasoning: ", str(integrity["reasoning"])))


def cmd_show(args):
    con = connect()
    job = resolve_job(con, args.ref)

    fields = Table.grid(padding=(0, 2))
    fields.add_column(justify="right", style=_DIM, no_wrap=True)
    fields.add_column()
    for key in ("job_id", "node_id", "title", "queue_state", "status", "executor",
                "job_type", "attempt", "max_attempts", "created_at", "artifacts_dir"):
        value = job[key]
        style = _state_style(value) if key in ("queue_state", "status") else "bold" if key == "job_id" else ""
        fields.add_row(f"{key}", Text(str(value), style=style))
    console.print(Panel(
        fields,
        title=Text(f"{_glyph(job['queue_state'])} {job['node_id']}", style=_state_style(job["queue_state"])),
        title_align="left",
        box=_CARD_BOX,
        padding=(1, 2),
    ))

    results = con.execute(
        "SELECT received_at, outcome, status, acceptance_check "
        "FROM results WHERE job_id = ? ORDER BY received_at",
        (job["job_id"],),
    ).fetchall()
    if results:
        console.print(Text("\nresults", style="bold"))
    for r in results:
        line = Text("          result: ", style=_DIM)
        line.append(f"{r['received_at']}  ")
        line.append(f"{r['outcome']}/{r['status']}", style=_verdict_style(r["outcome"]))
        console.print(line)
        print_evaluation(parse_check(r), full=args.full)
    decisions = con.execute(
        "SELECT created_at, action, reason FROM decision_results WHERE node_id = ? ORDER BY created_at",
        (job["node_id"],),
    ).fetchall()
    if decisions:
        console.print(Text("\ndecisions", style="bold"))
    for d in decisions:
        line = Text("        decision: ", style=_DIM)
        line.append(f"{d['created_at']}  ")
        line.append(str(d["action"]), style=_CYAN)
        line.append(f"  {d['reason'] or ''}", style=_DIM)
        console.print(line)


def config_root():
    return Path(os.environ.get("GDDP_CONFIG_PATH", str(RUNTIME_ROOT.parent / "gddp-config")))


def cmd_results(args):
    con = connect()
    rows = con.execute(
        "SELECT r.received_at, r.acceptance_check, j.node_id, j.project_id, r.job_id "
        "FROM results r JOIN jobs j ON j.job_id = r.job_id ORDER BY r.received_at",
    ).fetchall()
    if not rows:
        console.print(Text("No evaluator results.", style=_DIM))
        return

    if args.all:
        nodes = set()
        table = Table(
            title="evaluator results", box=_TABLE_BOX, title_justify="left", title_style="bold",
            padding=(0, 2, 0, 0), pad_edge=False,
        )
        table.add_column("", width=1, no_wrap=True)
        table.add_column("received", style=_DIM, no_wrap=True)
        table.add_column("verdict", no_wrap=True)
        table.add_column("project", no_wrap=True)
        table.add_column("node", no_wrap=True)
        table.add_column("job_id", style="bold", no_wrap=True)
        receipts = []
        for r in rows:
            check = parse_check(r)
            verdict = check.get("verdict") or "-"
            nodes.add((r["project_id"], r["node_id"]))
            table.add_row(
                Text(_glyph(verdict), style=_verdict_style(verdict)),
                (r["received_at"] or "")[:19],
                Text(verdict, style=_verdict_style(verdict)),
                r["project_id"] or "-",
                r["node_id"] or "-",
                r["job_id"],
            )
            if check.get("receipt_path"):
                receipts.append((r["job_id"], check["receipt_path"]))
        table.caption = f"{len(rows)} result row(s) across {len(nodes)} node(s)"
        table.caption_justify = "left"
        table.caption_style = _DIM
        console.print(table)
        for job_id, path in receipts:
            console.print(_kv(f"  receipt {job_id}: ", str(path), _DIM))
        return

    # Default: per-project summary — counts plus where the files live, so the
    # answer to "how many rows/receipts exist?" doesn't grow with each result.
    projects = {}
    for r in rows:
        p = projects.setdefault(r["project_id"] or "-", {"rows": 0, "nodes": set(), "latest": r})
        p["rows"] += 1
        p["nodes"].add(r["node_id"])
        p["latest"] = r  # rows are ordered by received_at

    live_root = config_root() / "verification-runtime-live"
    total_nodes = {(pid, n) for pid, p in projects.items() for n in p["nodes"]}
    table = Table(
        title="results by project", box=_TABLE_BOX, title_justify="left", title_style="bold",
        caption=f"{len(rows)} result row(s), {len(total_nodes)} node(s), {len(projects)} project(s)  ·  --all for every row",
        caption_justify="left", caption_style=_DIM, padding=(0, 2, 0, 0), pad_edge=False,
    )
    table.add_column("project", style="bold", no_wrap=True)
    table.add_column("nodes", justify="right", no_wrap=True)
    table.add_column("rows", justify="right", no_wrap=True)
    table.add_column("latest verdict", no_wrap=True)
    table.add_column("latest node", no_wrap=True)
    table.add_column("when", style=_DIM, no_wrap=True)
    # Collect the "where the files live" lines to print under the table, so long
    # receipt/export paths render in full instead of a truncated table column.
    artifact_lines = []
    for project_id in sorted(projects):
        p = projects[project_id]
        latest_check = parse_check(p["latest"])
        latest_verdict = latest_check.get("verdict") or "-"
        proj_dir = live_root / project_id
        receipts = sorted(proj_dir.glob("*.json")) if proj_dir.exists() else []
        table.add_row(
            project_id,
            str(len(p["nodes"])),
            str(p["rows"]),
            Text(f"{_glyph(latest_verdict)} {latest_verdict}", style=_verdict_style(latest_verdict)),
            p["latest"]["node_id"] or "-",
            (p["latest"]["received_at"] or "")[:10],
        )
        artifact_lines.append(_kv(f"  {project_id}: ", f"{len(receipts)} receipt(s) in {proj_dir}", _DIM))
        if (proj_dir / "evaluations.yaml").exists():
            artifact_lines.append(_kv(f"  {'':{len(project_id)}}  export: ", str(proj_dir / "evaluations.yaml"), _DIM))
    console.print(table)
    for line in artifact_lines:
        console.print(line)


def cmd_set(args):
    if args.state not in QUEUE_STATES:
        fail(f"Invalid state '{args.state}'. Valid: {' '.join(QUEUE_STATES)}")
    con = connect()
    job = resolve_job(con, args.ref)
    old = job["queue_state"]
    if old == args.state:
        console.print(Text(f"{job['job_id']} already '{old}' — nothing to do.", style=_DIM))
        return

    transition = Text(job["job_id"], style="bold")
    transition.append(f"  ({job['node_id']})\n", style=_DIM)
    transition.append(f"{_glyph(old)} {old}", style=_state_style(old))
    transition.append("  →  ", style=_DIM)
    transition.append(f"{_glyph(args.state)} {args.state}", style=_state_style(args.state))
    console.print(Panel(transition, title="state change", title_align="left", box=_CARD_BOX, padding=(1, 2)))

    if not args.yes:
        if input("Proceed? [y/N] ").strip().lower() != "y":
            fail("Aborted.")

    con.execute("UPDATE jobs SET queue_state = ? WHERE job_id = ?",
                (args.state, job["job_id"]))
    if args.state in JOB_STATUSES:
        con.execute("UPDATE jobs SET status = ? WHERE job_id = ?",
                    (args.state, job["job_id"]))
    con.execute("UPDATE queue_records SET queue = ? WHERE job_id = ?",
                (args.state, job["job_id"]))

    action = "accept_node" if (old == "awaiting_review" and args.state == "complete") \
             else "manual_status_change"
    con.execute(
        "INSERT INTO decision_results (result_id, action, node_id, project_id, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"dec_{uuid.uuid4().hex[:12]}", action, job["node_id"], job["project_id"],
         args.reason, now()),
    )
    # Persist reason history before commit so a history failure rolls back queue state.
    try:
        from node_status_history import append_status_change

        hist = append_status_change(
            project_id=job["project_id"] or "unknown",
            node_id=job["node_id"],
            from_status=old,
            to_status=args.state,
            reason=args.reason,
            kind="queue",
            source="gddp jobs set",
            runtime_root=RUNTIME_ROOT,
            extra={"job_id": job["job_id"], "action": action},
        )
    except Exception as exc:  # noqa: BLE001
        con.rollback()
        fail(f"history write failed ({exc}); queue state not committed.")
    con.commit()
    done = Text("✔ Done: ", style=_GREEN)
    done.append(f"{job['job_id']} → {args.state}")
    done.append(f"  (audit: {action})", style=_DIM)
    done.append(f"  (history: {hist})", style=_DIM)
    console.print(done)


def _glance() -> Text | None:
    """A one-line status glance for the landing screen — safe if the DB is absent."""
    try:
        con = connect()
        total = con.execute("SELECT count(*) FROM jobs").fetchone()[0]
        review = con.execute(
            "SELECT count(*) FROM jobs WHERE queue_state = 'awaiting_review'"
        ).fetchone()[0]
    except sqlite3.Error:
        return None
    line = Text("  ", style=_DIM)
    line.append(f"{total}", style="bold")
    line.append(" job(s)", style=_DIM)
    if review:
        line.append("   ")
        line.append(f"{_glyph('awaiting_review')} {review} awaiting review", style=_YELLOW)
    return line


def _static_overview():
    """Non-interactive landing — commands + a status glance, safe to pipe."""
    console.print(Text("gddp jobs", style="bold").append("  ·  runtime operator CLI", style=_DIM))
    glance = _glance()
    if glance is not None:
        console.print(glance)

    table = Table(box=None, padding=(0, 3, 0, 2), pad_edge=False, show_header=False)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(style=_DIM)
    table.add_row("list", "[--state S]", "jobs and their queue states")
    table.add_row("show", "<job|node> [--full]", "one job: fields, results, decisions")
    table.add_row("results", "[--all]", "evaluator output per project")
    table.add_row("set", "<job|node> <state> --reason", "change queue state (asks first)")
    console.print(Panel(table, title="commands", title_align="left", box=_CARD_BOX, padding=(1, 1)))
    console.print(Text("  gddp jobs <command> -h  ·  run `gddp jobs` in a terminal for the menu", style=_DIM))


def cmd_overview(_args):
    """Bare jobs entry: interactive menu on a terminal, static help when piped."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        interactive_menu()
    else:
        _static_overview()


# --- interactive menu ------------------------------------------------------

def _read_key() -> str:
    """Read one terminal keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, old)


def _menu_choice(actions, default: str) -> str:
    """Read one valid menu action key, preserving Enter as the default."""
    while True:
        console.print(Text("select", style=_CYAN), end=" ")
        choice = _read_key()
        if choice == "\x03":
            raise KeyboardInterrupt
        if choice in {"\r", "\n"}:
            choice = default
        choice = choice.lower()
        if choice in actions:
            console.print(choice)
            return choice
        console.print(Text(f"{choice!r} is not an option", style=_YELLOW))


def _pick_job(con, prompt: str = "job number (Enter to cancel)"):
    """Show a numbered job list and return the chosen job Row, or None."""
    rows = con.execute(
        "SELECT job_id, node_id, queue_state, attempt, max_attempts "
        "FROM jobs ORDER BY created_at DESC"
    ).fetchall()
    if not rows:
        console.print(Text("No jobs.", style=_DIM))
        return None
    table = Table(box=_TABLE_BOX, padding=(0, 2, 0, 0), pad_edge=False)
    table.add_column("#", justify="right", style="bold", no_wrap=True)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("state", no_wrap=True)
    table.add_column("node", no_wrap=True)
    table.add_column("job_id", style=_DIM, no_wrap=True)
    for i, r in enumerate(rows, 1):
        style = _state_style(r["queue_state"])
        table.add_row(
            str(i), Text(_glyph(r["queue_state"]), style=style),
            Text(r["queue_state"], style=style), r["node_id"] or "-", r["job_id"],
        )
    console.print(table)
    raw = Prompt.ask(Text(prompt, style=_CYAN), default="", show_default=False).strip()
    if not raw:
        return None
    if not raw.isdigit() or not (1 <= int(raw) <= len(rows)):
        console.print(Text(f"'{raw}' is not a listed number.", style=_YELLOW))
        return None
    return rows[int(raw) - 1]


def _menu_set(con, job):
    """Guided state change from inside the menu (own confirm, no double prompt)."""
    console.print(Text(f"current: ", style=_DIM).append(
        f"{_glyph(job['queue_state'])} {job['queue_state']}", style=_state_style(job["queue_state"])))
    state = Prompt.ask(Text("new state", style=_CYAN), choices=QUEUE_STATES, show_choices=False)
    if state == job["queue_state"]:
        console.print(Text(f"already '{state}' — nothing to do.", style=_DIM))
        return
    reason = Prompt.ask(Text("reason", style=_CYAN), default="").strip()
    if not reason:
        console.print(Text("reason required — aborted.", style=_YELLOW))
        return
    cmd_set(argparse.Namespace(ref=job["job_id"], state=state, reason=reason, yes=False))


def interactive_menu():
    """A stay-a-while loop: browse jobs, open one, change state — no re-running."""
    console.print(Text("gddp jobs", style="bold").append("  ·  runtime operator CLI", style=_DIM))
    actions = {
        "l": ("list", "jobs and their queue states"),
        "o": ("open", "pick a job → fields, results, decisions"),
        "r": ("results", "evaluator output per project"),
        "s": ("set", "pick a job → change its queue state"),
        "q": ("quit", ""),
    }
    while True:
        glance = _glance()
        if glance is not None:
            console.print()
            console.print(glance)
        menu = Table(box=None, padding=(0, 2, 0, 1), pad_edge=False, show_header=False)
        menu.add_column(style="bold cyan", no_wrap=True)
        menu.add_column(style="bold", no_wrap=True)
        menu.add_column(style=_DIM)
        for key, (name, desc) in actions.items():
            menu.add_row(key, name, desc)
        console.print(menu)
        try:
            choice = _menu_choice(actions, default="l")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        console.rule(style=_DIM)
        try:
            if choice == "q":
                break
            con = connect()
            if choice == "l":
                cmd_list(argparse.Namespace(state=None))
            elif choice == "r":
                cmd_results(argparse.Namespace(all=False))
            elif choice == "o":
                job = _pick_job(con)
                if job:
                    console.rule(style=_DIM)
                    cmd_show(argparse.Namespace(ref=job["job_id"], full=False))
            elif choice == "s":
                job = _pick_job(con)
                if job:
                    console.rule(style=_DIM)
                    _menu_set(con, job)
        except (EOFError, KeyboardInterrupt):
            console.print(Text("\n(cancelled)", style=_DIM))
        except SystemExit:
            # cmd_set/resolve_job abort via SystemExit; in the menu that's just
            # a cancelled action, not a reason to quit the whole session.
            pass
        console.rule(style=_DIM)
    console.print(Text("bye.", style=_DIM))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(fn=cmd_overview)  # bare jobs entry → landing screen, not an argparse error
    sub = p.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="list jobs and states")
    p_list.add_argument("--state", help="filter by queue_state")
    p_list.set_defaults(fn=cmd_list)

    p_show = sub.add_parser("show", help="show one job (accepts job_id or node_id)")
    p_show.add_argument("ref")
    p_show.add_argument("--full", action="store_true", help="include full integrity reasoning")
    p_show.set_defaults(fn=cmd_show)

    p_results = sub.add_parser("results", help="evaluator output summary: counts + paths per project")
    p_results.add_argument("--all", action="store_true", help="list every result row instead of the summary")
    p_results.set_defaults(fn=cmd_results)

    p_set = sub.add_parser("set", help="set queue state (accepts job_id or node_id)")
    p_set.add_argument("ref")
    p_set.add_argument("state")
    p_set.add_argument("--reason", required=True, help="why — stored in the audit row")
    p_set.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    p_set.set_defaults(fn=cmd_set)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
