/**
 * gddp_tracer.ts — Non-blocking audit trail for the GDDP evaluator.
 *
 * This extension only logs tool calls and results to $GDDP_TOOL_TRACE (JSONL).
 * It does NOT block any tools. Enforcement of the read-only invariant is
 * handled by the runner via pi's --exclude-tools flag.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { env } from "node:process";
import { appendFileSync, writeFileSync } from "node:fs";

function traceLine(entry: Record<string, unknown>) {
  const tracePath = env.GDDP_TOOL_TRACE;
  if (!tracePath) return;
  try {
    appendFileSync(tracePath, JSON.stringify(entry) + "\n", { encoding: "utf8" });
  } catch {
    // tracing is best-effort
  }
}

export default function (pi: ExtensionAPI) {
  // Log every tool call.
  pi.on("tool_call", async (event, _ctx) => {
    const e = event as { toolName?: string; input?: Record<string, unknown> };
    traceLine({
      ts: new Date().toISOString(),
      event: "tool_call",
      tool: e.toolName,
      input: e.input,
    });
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

  // Ensure the trace file exists at start.
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
