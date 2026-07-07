/**
 * gddp_integrity.ts — Pi extension for evaluator lane 2: intent + graph-integrity
 * evaluation. Registers `submit_integrity_verdict` — the ONLY custom tool,
 * terminal, mirroring IntegrityOutput in scripts/runtime/verification/schemas.py.
 *
 * Vocabulary comes from the evaluator-intent-integrity-verdict node YAML in
 * gddp-config, not from this repo — the graph is the source of the language.
 *
 * Same contract as gddp_verifier.ts: read-only investigation via built-in
 * tools, guard applies identically, payload written to $GDDP_INTEGRITY_OUT,
 * terminate: true. Separate extension file, not a fork of gddp_verifier.ts.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type, type Static } from "typebox";
import { writeFileSync } from "node:fs";
import { env } from "node:process";

const IntegrityFindingSchema = Type.Object({
  severity: Type.Union([
    Type.Literal("low"),
    Type.Literal("medium"),
    Type.Literal("high"),
  ]),
  summary: Type.String(),
  affected_node_ids: Type.Array(Type.String()),
});

const SubmitIntegrityVerdictParams = Type.Object({
  verdict: Type.Union([
    Type.Literal("pass"),
    Type.Literal("block"),
    Type.Literal("drift"),
    Type.Literal("insufficient"),
    Type.Literal("contradicted"),
    Type.Literal("unknown"),
  ]),
  intent_preserved: Type.Boolean(),
  graph_integrity_preserved: Type.Boolean(),
  required_human_review: Type.Boolean(),
  confidence: Type.Number({ minimum: 0, maximum: 1 }),
  findings: Type.Array(IntegrityFindingSchema),
  reasoning: Type.String(),
});

export type SubmitIntegrityVerdictArgs = Static<typeof SubmitIntegrityVerdictParams>;

function asText(text: string) {
  return { type: "text" as const, text };
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "submit_integrity_verdict",
    label: "Submit Integrity Verdict",
    description:
      "Terminal tool. Call this exactly once when your fresh-eyes integrity " +
      "review is complete. Arguments must match IntegrityOutput: verdict, " +
      "intent_preserved, graph_integrity_preserved, required_human_review, " +
      "confidence, findings, and reasoning. After you call this, the run ends.",
    promptSnippet:
      "submit_integrity_verdict: terminal tool. Call once with your final IntegrityOutput payload.",
    parameters: SubmitIntegrityVerdictParams,
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const args = params as SubmitIntegrityVerdictArgs;
      const outPath = env.GDDP_INTEGRITY_OUT;
      if (!outPath) {
        return {
          content: [asText("GDDP_INTEGRITY_OUT env var is not set; cannot record integrity verdict.")],
          details: { ok: false, reason: "missing_env" },
          terminate: true,
        };
      }

      // Node constraint (evaluator-intent-integrity-verdict node YAML): any
      // non-pass verdict forces required_human_review=true. The model may set
      // it but the harness enforces it regardless.
      const nonPass = args.verdict !== "pass";
      const effectiveHumanReview = nonPass || Boolean(args.required_human_review);

      const payload = {
        verdict: args.verdict,
        intent_preserved: Boolean(args.intent_preserved),
        graph_integrity_preserved: Boolean(args.graph_integrity_preserved),
        required_human_review: effectiveHumanReview,
        confidence: args.confidence,
        findings: args.findings,
        reasoning: args.reasoning,
      };
      try {
        writeFileSync(outPath, JSON.stringify(payload), { encoding: "utf8" });
      } catch (err) {
        return {
          content: [asText(`Failed to write integrity verdict: ${(err as Error).message}`)],
          details: { ok: false, reason: "write_failed" },
          terminate: true,
        };
      }
      return {
        content: [asText("Integrity verdict recorded. Ending investigation.")],
        details: { ok: true, verdict: payload.verdict },
        terminate: true,
      };
    },
  });
}
