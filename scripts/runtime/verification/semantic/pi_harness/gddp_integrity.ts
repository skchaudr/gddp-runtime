/**
 * gddp_integrity.ts — SKELETON (integrity-lane-draft; not loaded anywhere yet).
 *
 * Pi extension for evaluator lane 2: intent + graph-integrity evaluation.
 * Registers `submit_integrity_verdict` — the ONLY custom tool, terminal,
 * mirroring IntegrityOutput in scripts/runtime/verification/schemas.py.
 * Vocabulary comes from the evaluator-intent-integrity-verdict node YAML.
 *
 * Same contract as gddp_verifier.ts: read-only investigation via built-in
 * tools, guard applies identically, payload written to $GDDP_INTEGRITY_OUT,
 * terminate: true. Separate extension file, not a fork of gddp_verifier.ts.
 */

import { Type, type Static } from "typebox";

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

// TODO(implementation): register the tool exactly like gddp_verifier.ts does —
// validate payload, force required_human_review=true for any non-pass verdict
// (node constraint), writeFileSync($GDDP_INTEGRITY_OUT), terminate: true.
