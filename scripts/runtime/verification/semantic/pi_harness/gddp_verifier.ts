/**
 * gddp_verifier.ts — Pi extension that registers the typed `submit_verdict`
 * terminal tool for the GDDP semantic verifier.
 *
 * Design:
 *   - Evidence investigation uses pi's BUILT-IN read-only tools (read, grep,
 *     find, ls). The Python runner excludes edit/write/multi_edit/bash so the
 *     harness is read-only, matching the gddp-runtime verifier contract.
 *   - `submit_verdict` is the ONLY custom tool. Its parameters mirror
 *     SemanticOutput in scripts/runtime/verification/schemas.py. When the model
 *     calls it, the payload is validated, written to the path in
 *     $GDDP_VERDICT_OUT, and `terminate: true` stops the agent loop.
 *   - No graph mutation, no network, no repo writes. The extension only reads
 *     $GDDP_VERDICT_OUT (env, set by the Python runner) and writes the verdict
 *     JSON there.
 *
 * Load with:  pi -e gddp_verifier.ts --tools read,grep,find,ls,submit_verdict
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type, type Static } from "typebox";
import { writeFileSync } from "node:fs";
import { env } from "node:process";

const JudgmentSchema = Type.Object({
  criterion_id: Type.String(),
  judgment: Type.Union([
    Type.Literal("judged_pass"),
    Type.Literal("judged_fail"),
    Type.Literal("indeterminate"),
  ]),
  confidence: Type.Number({ minimum: 0, maximum: 1 }),
  evidence: Type.Array(Type.String()),
  reasoning: Type.String(),
});

const SubmitVerdictParams = Type.Object({
  judgments: Type.Array(JudgmentSchema),
  overall_reasoning: Type.String(),
  risks: Type.Union([Type.String(), Type.Null()]),
  followup_candidates: Type.Union([Type.String(), Type.Null()]),
  budget_exhausted: Type.Boolean(),
  budget_trace: Type.Optional(Type.Any()),
});

type SubmitVerdictArgs = Static<typeof SubmitVerdictParams>;

function asText(text: string) {
  return { type: "text" as const, text };
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "submit_verdict",
    label: "Submit Verdict",
    description:
      "Terminal tool. Call this exactly once when your investigation is complete. " +
      "Arguments must match SemanticOutput: per-criterion judgments, overall_reasoning, " +
      "risks, followup_candidates, and budget_exhausted. After you call this, the run ends.",
    promptSnippet:
      "submit_verdict: terminal tool. Call once with your final SemanticOutput payload.",
    parameters: SubmitVerdictParams,
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const args = params as SubmitVerdictArgs;
      const outPath = env.GDDP_VERDICT_OUT;
      if (!outPath) {
        return {
          content: [asText("GDDP_VERDICT_OUT env var is not set; cannot record verdict.")],
          details: { ok: false, reason: "missing_env" },
          terminate: true,
        };
      }
      const payload = {
        judgments: args.judgments,
        overall_reasoning: args.overall_reasoning,
        risks: args.risks ?? null,
        followup_candidates: args.followup_candidates ?? null,
        budget_exhausted: Boolean(args.budget_exhausted),
        budget_trace: args.budget_trace ?? null,
      };
      try {
        writeFileSync(outPath, JSON.stringify(payload), { encoding: "utf8" });
      } catch (err) {
        return {
          content: [asText(`Failed to write verdict: ${(err as Error).message}`)],
          details: { ok: false, reason: "write_failed" },
          terminate: true,
        };
      }
      return {
        content: [asText("Verdict recorded. Ending investigation.")],
        details: { ok: true, judgments: payload.judgments.length },
        terminate: true,
      };
    },
  });
}
