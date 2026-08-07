# Mission: Factory mission-mode external surface investigation

Research mission. Produce one report: docs/mission-hooks-investigation.md. Read-only
everywhere except this repository.

## Context
GDDP (~/repos/gddp-runtime) is integrating droid mission mode as an executor.
Before building, we must know what an EXTERNAL process can do with a running
mission. Answer from evidence, not speculation: local artifacts under
~/.factory/, the installed droid binary's own help/behavior, official docs
(docs.factory.ai — fetch llms.txt for the full page index), and Factory's
public SDK repos (github.com/Factory-AI/droid-sdk-typescript and
droid-sdk-python).

## Questions (answer each: yes / no / partial + evidence path or URL + confidence)
1. Submission: can an external process submit new work to an ALREADY-RUNNING
   mission? (CLI resume, daemon IPC/websocket, filesystem inbox, SDK call?)
2. Status: can an external caller read per-assignment/per-feature status of a
   running mission without attaching to its TTY?
3. Cancellation: can one assignment/feature be cancelled without ending the
   mission?
4. Identity: which identifier survives restart as canonical — mission dir
   name (session uuid), state.json missionId (mis_*), or something else?
5. Terminal artifacts: which files under ~/.factory/missions/<id>/ are stable
   and terminal (safe to hash as evidence), and what event makes them safe?
6. Commit mapping: how do mission worktrees/branches/commits map to features?
   Can a base→result boundary per feature be reconstructed from git history?
7. Crash/replay: after killing a mission process, what does resume look like,
   and how would an external watcher avoid treating resumed work as duplicate?
8. Isolation: what state is mission-wide vs per-worker? Can one mission run
   sequential external assignments?

## Bottom line
Verdict: is per-node external assignment admission (a) supported, (b) possible
with documented workarounds, or (c) not exposed — and therefore which authority
model GDDP should build: per-node admission leases, or one mission-level lease
authorizing the whole graph with post-hoc evidence slicing.

## Constraints
- Read-only against ~/.factory and any system state; fetch SDK repos read-only
- Do not launch another mission, do not modify any existing mission files
- Web fetches bounded to official Factory docs + Factory-AI GitHub org
- Commit the report on this repo's current branch when done
