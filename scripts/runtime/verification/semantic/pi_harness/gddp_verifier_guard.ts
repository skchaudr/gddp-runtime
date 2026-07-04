/**
 * gddp_verifier_guard.ts — Mechanistic enforcement layer for the GDDP evaluator.
 *
 * Philosophy: broad inputs, enforced outputs. The evaluator gets wide tool
 * access (read, grep, find, ls, bash, even edit/write/multi_edit are
 * available to call), but this guard mechanistically blocks anything that
 * would violate the verifier contract:
 *
 *   - No mutation of the target repo or anything outside the verdict-out path.
 *     edit/write/multi_edit are hard-blocked; bash write/destructive/git-
 *     mutation/network commands are hard-blocked. (pi.on("tool_call") block.)
 *   - Every tool call is logged to $GDDP_TOOL_TRACE (JSONL) so the receipt's
 *     budget_trace is ground-truth evidence, not the model's claim.
 *
 * This is the protected-paths.ts + permission-gate.ts + audit-log.ts patterns
 * from the pi docs, specialized for GDDP. The model is not asked to behave;
 * the harness refuses.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { env } from "node:process";
import { appendFileSync, writeFileSync } from "node:fs";

// bash command prefixes/substrings that are hard-blocked.
const BLOCKED_BASH_PATTERNS: RegExp[] = [
  /(?:^|\s|&&|\|\|)\s*(?:rm|rmdir)\s/,
  /(?:^|\s|&&|\|\|)\s*mv\s/,
  /(?:^|\s|&&|\|\|)\s*cp\s.*\s+\S+/, // cp with dest
  /(?:^|\s|&&|\|\|)\s*mkdir\s/,
  /(?:^|\s|&&|\|\|)\s*tee\s/,
  /(?:^|\s|&&|\|\|)\s*chmod\s/,
  /(?:^|\s|&&|\|\|)\s*chown\s/,
  /\b(?:curl|wget|ssh|scp|sftp|rsync|nc|netcat|telnet|ftp|pip|npm|pnpm|yarn|brew)\b/,
  /\bgit\s+(?:commit|push|reset|checkout|switch|merge|rebase|clean|add|restore|stash|cherry-pick|revert)\b/,
  /(?:>\s*|>>\s*|2>\s*)/, // shell redirection to a file
  /\bpip3?\s+install\b/,
  /\bpython3?\s+-m\s+pip\b/,
];

const WRITE_TOOLS = new Set(["edit", "write", "multi_edit", "create"]);

function asText(text: string) {
  return { type: "text" as const, text };
}

function traceLine(entry: Record<string, unknown>) {
  const tracePath = env.GDDP_TOOL_TRACE;
  if (!tracePath) return;
  try {
    appendFileSync(tracePath, JSON.stringify(entry) + "\n", { encoding: "utf8" });
  } catch {
    // tracing is best-effort; never let it break the run
  }
}

function extractPath(input: Record<string, unknown> | undefined): string | undefined {
  if (!input) return undefined;
  for (const key of ["path", "file_path", "filePath", "target", "file"]) {
    const v = (input as Record<string, unknown>)[key];
    if (typeof v === "string") return v;
  }
  return undefined;
}

export default function (pi: ExtensionAPI) {
  // Block mutations and dangerous commands BEFORE execution.
  pi.on("tool_call", async (event, _ctx) => {
    const toolName = (event as { toolName?: string }).toolName ?? "";
    const input = ((event as { input?: Record<string, unknown> }).input) ?? {};

    // 1. Hard-block all write/edit/create tools. The evaluator is read-only;
    //    it never needs to mutate the target repo. The only write in the whole
    //    run is the submit_verdict tool writing to $GDDP_VERDICT_OUT, which is
    //    a custom tool, not a built-in write tool.
    if (WRITE_TOOLS.has(toolName)) {
      const path = extractPath(input);
      traceLine({
        ts: new Date().toISOString(),
        tool: toolName,
        blocked: true,
        reason: "write tool hard-blocked (evaluator is read-only)",
        path,
      });
      return {
        block: true,
        reason: `GDDP guard: '${toolName}' is blocked. The evaluator is read-only and may not mutate the target repo. Path: ${path ?? "(unknown)"}`,
      };
    }

    // 2. Block dangerous bash commands.
    if (toolName === "bash") {
      const command = typeof input.command === "string" ? input.command : "";
      for (const pattern of BLOCKED_BASH_PATTERNS) {
        if (pattern.test(command)) {
          traceLine({
            ts: new Date().toISOString(),
            tool: "bash",
            blocked: true,
            reason: "command matched blocked pattern",
            command,
            pattern: pattern.source,
          });
          return {
            block: true,
            reason: `GDDP guard: bash command refused (matches blocked pattern: ${pattern.source}). Read-only inspection only; no writes, no git mutation, no network, no destructive verbs.`,
          };
        }
      }
      // Allowed read-only bash: log it.
      traceLine({
        ts: new Date().toISOString(),
        tool: "bash",
        blocked: false,
        command,
      });
      return undefined;
    }

    // 3. Read-only tools (read, grep, find, ls, submit_verdict): allow.
    return undefined;
  });

  // Log every tool result to the trace (ground-truth evidence for the receipt).
  pi.on("tool_execution_end", async (event, _ctx) => {
    const e = event as {
      toolCallId?: string;
      toolName?: string;
      isError?: boolean;
    };
    traceLine({
      ts: new Date().toISOString(),
      event: "tool_execution_end",
      toolCallId: e.toolCallId,
      tool: e.toolName,
      ok: !e.isError,
    });
    return undefined;
  });

  // Ensure the trace file exists at start (so the runner can find it even if
  // no tools were called).
  pi.on("session_start", async (_event, _ctx) => {
    const tracePath = env.GDDP_TOOL_TRACE;
    if (tracePath) {
      try {
        writeFileSync(tracePath, "", { encoding: "utf8" });
      } catch {
        // best-effort
      }
    }
    return undefined;
  });
}
