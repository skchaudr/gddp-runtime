# Zed Python debugging — first session (this repo)

Companion visual: [`docs/artifacts/zed-debugging-visual-guide.html`](../artifacts/zed-debugging-visual-guide.html)

Shortest path in current Zed: select the project `.venv`, set one breakpoint, press **F4**, pick a Python/pytest target. A `.zed/debug.json` profile is only required for repeatable arguments (`PYTHONPATH`, a single pytest node, pytest `--lf`). Action names and default F-keys below are **documented**. Icons, colors, panel order, exact picker strings, and exception-checkbox wording are **inferred** unless a source is cited.

## 1. First successful five minutes

Do one UI action, then look. Re-check line numbers immediately before repeating; insertions above either target shift them.

| Field | Value |
|---|---|
| **Profile** | `GDDP: five-minute debugger tour` in [`.zed/debug.json`](../../.zed/debug.json). Args pin **one** pytest node. `GDDP: current pytest file` is a different profile: it runs the whole `$ZED_RELATIVE_FILE`. |
| **Breakpoint** | `scripts/runtime/verification/retry_budget.py:96` — `has_evidence = has_evidence_references(integrity) or has_criteria_evidence(criteria_findings)` |
| **Trigger** | `scripts/runtime/verification/test_retry_budget.py::TestShouldRetry::test_non_pass_with_evidence_and_budget_and_room_returns_true` (lines 120–128). This tour profile runs **only that node**, so line 96 is hit once, by that test. |
| **Watches** | `verdict` · `integrity["findings"][0]["summary"]` · `job["attempt"]` · `project_yaml["execution_policy"]["retry_budget"]` · `has_evidence` |
| **Expected stop** | `retry_budget.py:96` in `should_retry`. Locals: `verdict = "needs-human-review"`; `integrity = {"findings": [{"severity": "high", "summary": "src/foo.py has a bug"}], "reasoning": ""}`; `job = {"attempt": 0, "max_attempts": 3}`; `project_yaml = {"execution_policy": {"retry_budget": 2}}`; `criteria_findings = None`. `has_evidence` does not exist until line 96 runs. |
| **Recovery** | Stop, remove extra breakpoints, confirm **`GDDP: five-minute debugger tour`**, Start again. |

1. Select the project `.venv` at the right of the status bar (or run `toolchain: select`). **Expected (documented):** the chosen toolchain remains named at the right of the status bar. If absent, **Add toolchain** accepts a path. That toolchain supplies the interpreter and can supply debugpy ([Zed Python toolchains](https://zed.dev/docs/languages/python#how-zed-uses-python-toolchains)).
2. Open `scripts/runtime/verification/test_retry_budget.py` so you can see the trigger (this profile does not use `$ZED_RELATIVE_FILE`).
3. Open `scripts/runtime/verification/retry_budget.py` in a split or tab.
4. Click the gutter beside line 96, or press **F9** (`editor::ToggleBreakpoint`). **Expected (documented):** a breakpoint marker beside the line number. Zed saves breakpoints across sessions by default.
5. Press **F4** (`debugger: start`). In the new-process modal, choose **`GDDP: five-minute debugger tour`**. **Expected (documented):** a picker of contextual targets plus `.zed/debug.json` profiles, then the Debug panel. Exact picker layout is inferred.
6. Wait for the breakpoint. **Expected (documented):** the paused source line is highlighted; inline variable values are on by default; the Debug panel exposes threads, Variables, breakpoints, and call-stack Frames.
7. Compare Locals to the expected stop. In the Debug Console, type a watch expression and press **Alt-Enter** (`console::WatchExpression`). **Expected (documented keymap):** the watch appears in the Variables list. A separately labeled Watch pane is not specified. Enter in the console evaluates; Alt-Enter watches.
8. **Step Over** once (**F7** or **F10**, `debugger: step over`). Execution stays in `should_retry`; `has_evidence` becomes `True`; the instruction marker moves to line 97. Marker color is inferred.
9. **Restart** (`debugger: restart` / `debugger: rerun session`; **Cmd-Shift-F5** macOS, **Ctrl-Shift-F5** Linux for rerun-session). Same first stop at line 96.
10. **Step Into** once (**F11** or **Ctrl-F11**, `debugger: step into`). **Expected executable stop (adapter-inferred):** `retry_budget.py:30` — `if integrity_output is None:`. Line 23 is only the function declaration (`def has_evidence_references…`), not the pause line. Caller-frame watches (`verdict`, `has_evidence`, …) are unavailable until you select the `should_retry` frame.
11. **Stop** (**Shift-F5**, `debugger: stop`). Press **F9** on line 96, or select the breakpoint in the Breakpoints list and press Backspace, to remove it.

After Continue from the line-96 stop, the test assertion receives `True` and that single node finishes.

## 2. Live-code recipe

Use when the thing under the cursor is a script, not a test.

1. Confirm the status-bar toolchain is `.venv`.
2. Breakpoint on an executable line (**F9**).
3. **F4** → **`GDDP: current Python file`** (`program: $ZED_FILE`, `cwd: $ZED_WORKTREE_ROOT`, `PYTHONPATH` set).
4. Inspect Variables / Frames. Evaluate in the Debug Console, or select source text and run `debugger: evaluate selected text`.
5. Stop (**Shift-F5**).

Zed also auto-detects Python scripts, modules, and pytest tests with no `debug.json` ([start debugging with no setup](https://zed.dev/docs/languages/python#start-debugging-with-no-setup)). This repo’s saved profiles keep `PYTHONPATH`, `justMyCode`, and `showReturnValue` repeatable.

`GDDP: current pytest file` runs **every test in the active file** (`$ZED_RELATIVE_FILE`). Use it for a whole-file session, not for the five-minute tour.

## 3. Post-failure recipe

Use after a pytest failure, when only the last failed node should run.

1. Confirm the status-bar toolchain is `.venv`.
2. Breakpoint on the suspected executable line in project code.
3. **F4** → **`GDDP: last failed test`**. Args: `-q -s --lf --last-failed-no-failures=none --maxfail=1`. `--lf` is pytest cache behavior, not a Zed UI action ([pytest cache](https://docs.pytest.org/en/stable/how-to/cache.html#rerunning-only-failures-or-failures-first)).
4. If the pytest cache is empty, `--lf --last-failed-no-failures=none` runs **no tests** and pytest exits **status 5** (`no tests collected`). That is pytest behavior, not a debugger failure. Recovery: run the failing file once without the debugger so pytest records the failure, then Start again.

For a first pytest bug hunt without a line breakpoint, open the Debug panel **Breakpoints** item and enable the adapter exception choice **User Uncaught Exceptions** — debugpy meaning: stop when an exception crosses from user code into library code, which a test framework will often catch ([debugpy FAQ](https://github.com/microsoft/debugpy/wiki/FAQ#a-handled-exception-is-causing-the-debugger-to-break-execution-or-an-exception-is-not-causing-the-debugger-to-break-execution)). **Raised Exceptions** stops on every raise/reraise in user code when `justMyCode: true`. Zed’s checkbox wording is adapter-supplied and not specified.

## 4. Debugger controls

Documented actions. Default macOS/Linux bindings while applicable; laptops may need **Fn**. **F5 outside a running session is `debugger: rerun`**. Confirm bindings with `zed: open keymap` if a physical key does something else.

| Intent | Documented action | Default binding while applicable |
|---|---|---|
| Start / new session | `debugger: start` | **F4** |
| Continue to next breakpoint | `debugger: continue` | **F5** while stopped |
| Pause a running program | `debugger: pause` | **F6** during a live session |
| Step over (finish this line, do not enter the call) | `debugger: step over` | **F7** or **F10** while stopped |
| Step into the next function call | `debugger: step into` | **F11** or **Ctrl-F11** while stopped |
| Step out of the current function | `debugger: step out` | **Shift-F11** while stopped |
| Restart same live session | `debugger: restart` / `debugger: rerun session` | **Cmd-Shift-F5** macOS; **Ctrl-Shift-F5** Linux for rerun-session |
| Stop | `debugger: stop` | **Shift-F5** |
| Toggle breakpoint | `editor::ToggleBreakpoint` | **F9** |
| Focus variables | `debugger: focus variables` | — |
| Focus frames (call stack) | `debugger: focus frames` | — |
| Focus console | `debugger: focus console` | — |
| Evaluate selection | `debugger: evaluate selected text` | — |
| Add watch | `console::WatchExpression` | **Alt-Enter** in Debug Console or Variables |

This repo’s Debugpy profiles set `"justMyCode": true` and `"showReturnValue": true`. `"stopOnEntry": true` pauses at the first user-code line if you add it ([debugpy settings](https://github.com/microsoft/debugpy/wiki/Debug-configuration-settings)).

## 5. Observation worksheet

Copy and fill while paused. On mismatch, stop advancing and recover.

```
profile:
breakpoint (path:line + source):
trigger (exact test/node; does the profile run more than that node?):
watches:
expected stop — file / line / function:
expected locals:
seen stop — file / line / function:
seen locals:
seen watches:
next command and expected change (marker / stack / local):
recovery:
```

## 6. Troubleshooting (official order)

1. Status-bar toolchain is the project `.venv`. It drives Python/pytest tasks and can supply debugpy ([how Zed uses Python toolchains](https://zed.dev/docs/languages/python#how-zed-uses-python-toolchains)).
2. With a debug session present: `dev: copy debug adapter arguments` (JSON Zed used to initialize it).
3. `dev: open debug adapter logs` — recent Zed↔adapter traffic; this is what a Zed issue asks for ([debugger troubleshooting](https://zed.dev/docs/debugger#troubleshooting)).
4. Language-server/import trouble: `zed: open log`, then `dev: open language server logs` (Server Logs and Server Info). Restart with `editor: restart language server`.
5. If function keys differ: `zed: open keymap` (default Cmd/Ctrl-K, Cmd/Ctrl-S) and search the **action name**.

This-repo recovery:

- Tour profile never hits line 96 → an insertion shifted the breakpoint. Re-read `retry_budget.py`, move the breakpoint onto the `has_evidence = …` assignment, confirm **`GDDP: five-minute debugger tour`**, Start.
- `GDDP: current pytest file` ran extra tests or a non-test file → that profile expands `$ZED_RELATIVE_FILE`. Use the tour profile for the single node, or focus the intended test file for a whole-file run.
- Last-failed collects nothing and the process exits 5 → empty pytest cache plus `--last-failed-no-failures=none`. Not a debugger failure. Run the failing file once without the debugger, then Start.
- Intake profile `GDDP: intake server` is frozen infrastructure; skip it for this exercise.
- Never invoke the heartbeat runner directly. Use `deploy/mini-heartbeat/bin/` (`arm.sh`, `smoke.sh`, launchd) only.

## 7. Sources

- [Debugger — Zed](https://zed.dev/docs/debugger) — workflow, configuration, breakpoints, inline values, diagnostics
- [Python — Zed](https://zed.dev/docs/languages/python) — toolchain, auto-targets, debugpy profiles
- [Toolchains — Zed](https://zed.dev/docs/toolchains) — selector location and `toolchain: select`
- [All Actions — Zed](https://zed.dev/docs/all-actions) — current action names
- [Default macOS keymap](https://github.com/zed-industries/zed/blob/main/assets/keymaps/default-macos.json) · [Linux keymap](https://github.com/zed-industries/zed/blob/main/assets/keymaps/default-linux.json)
- [debugpy configuration](https://github.com/microsoft/debugpy/wiki/Debug-configuration-settings) · [debugpy FAQ](https://github.com/microsoft/debugpy/wiki/FAQ)
- [pytest cache / last-failed](https://docs.pytest.org/en/stable/how-to/cache.html#rerunning-only-failures-or-failures-first)
- Live profiles: [`.zed/debug.json`](../../.zed/debug.json)
