"""Pure verdict decision engine — deterministic + semantic -> verdict."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .schemas import (
    CriterionCheck,
    CriterionJudgment,
    DeterministicResult,
    SemanticOutput,
    Verdict,
)

DEPS_CONFIDENCE = 1.0


@dataclass(frozen=True)
class _DecisionContext:
    deterministic: DeterministicResult
    semantic: SemanticOutput | None

    @property
    def deps_incomplete(self) -> bool:
        return any(status != "complete" for status in self.deterministic.deps_status.values())

    @property
    def constraint_violated(self) -> bool:
        return any(c.status == "violated" for c in self.deterministic.constraints)

    @property
    def any_fail(self) -> bool:
        return any(c.status == "fail" for c in self.deterministic.criteria)

    @property
    def all_pass(self) -> bool:
        return bool(self.deterministic.criteria) and all(
            c.status == "pass" for c in self.deterministic.criteria
        )

    @property
    def indeterminate_only(self) -> bool:
        if self.any_fail or self.all_pass:
            return False
        return any(c.status == "indeterminate" for c in self.deterministic.criteria)

    @property
    def artifacts_missing(self) -> bool:
        return any(not present for present in self.deterministic.artifacts_present.values())

    @property
    def artifacts_present(self) -> bool:
        return not self.artifacts_missing

    @property
    def indeterminate_criteria(self) -> list[CriterionCheck]:
        return [c for c in self.deterministic.criteria if c.status == "indeterminate"]

    @property
    def fail_criteria(self) -> list[CriterionCheck]:
        return [c for c in self.deterministic.criteria if c.status == "fail"]

    @property
    def violated_constraints(self) -> list:
        return [c for c in self.deterministic.constraints if c.status == "violated"]

    @property
    def judgments(self) -> list[CriterionJudgment]:
        if self.semantic is None:
            return []
        return self.semantic.judgments

    @property
    def any_judged_fail(self) -> bool:
        return any(j.judgment == "judged_fail" for j in self.judgments)

    @property
    def all_judged_pass(self) -> bool:
        return bool(self.judgments) and all(
            j.judgment == "judged_pass" for j in self.judgments
        )

    @property
    def any_judgment_indeterminate(self) -> bool:
        return any(j.judgment == "indeterminate" for j in self.judgments)

    @property
    def budget_exhausted(self) -> bool:
        return self.semantic is not None and self.semantic.budget_exhausted

    @property
    def judgments_empty(self) -> bool:
        return not self.judgments

    def deterministic_floor_confidence(self) -> float:
        indeterminate = self.indeterminate_criteria
        if indeterminate:
            return _mean(c.confidence for c in indeterminate)
        return _mean(c.confidence for c in self.deterministic.criteria)


@dataclass(frozen=True)
class _MatrixRow:
    number: int
    matches: Callable[[_DecisionContext], bool]
    verdict: Verdict
    confidence: Callable[[_DecisionContext], float]
    required_next_action: str
    reasoning: str


def _mean(values) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _confidence_blocked(_ctx: _DecisionContext) -> float:
    return DEPS_CONFIDENCE


def _confidence_constraint_violation(ctx: _DecisionContext) -> float:
    return _mean(c.confidence for c in ctx.violated_constraints)


def _confidence_fail_criteria(ctx: _DecisionContext) -> float:
    return _mean(c.confidence for c in ctx.fail_criteria)


def _confidence_all_criteria(ctx: _DecisionContext) -> float:
    return _mean(c.confidence for c in ctx.deterministic.criteria)


def _confidence_semantic_blend(
    ctx: _DecisionContext,
    judgments: list[CriterionJudgment],
    *,
    cap_at_half: bool = False,
) -> float:
    floor = ctx.deterministic_floor_confidence()
    if not judgments:
        blended = floor
    else:
        semantic = _mean(j.confidence for j in judgments)
        blended = min(floor, semantic)
    if cap_at_half:
        return min(blended, 0.5)
    return blended


def _row1(ctx: _DecisionContext) -> bool:
    return ctx.deps_incomplete


def _row2(ctx: _DecisionContext) -> bool:
    return not ctx.deps_incomplete and ctx.constraint_violated


def _row3(ctx: _DecisionContext) -> bool:
    return not ctx.deps_incomplete and not ctx.constraint_violated and ctx.any_fail


def _row4(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.any_judged_fail
    )


def _row5(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.all_pass
        and ctx.artifacts_missing
    )


def _row6(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.all_judged_pass
        and ctx.artifacts_missing
    )


def _row7(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.any_judgment_indeterminate
        and ctx.artifacts_missing
        and not ctx.budget_exhausted
    )


def _row8(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.budget_exhausted
    )


def _row9(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.judgments_empty
    )


def _row10(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.any_judgment_indeterminate
        and ctx.artifacts_present
    )


def _row11(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.indeterminate_only
        and ctx.all_judged_pass
        and ctx.artifacts_present
    )


def _row12(ctx: _DecisionContext) -> bool:
    return (
        not ctx.deps_incomplete
        and not ctx.constraint_violated
        and not ctx.any_fail
        and ctx.all_pass
        and ctx.artifacts_present
    )


MATRIX: list[_MatrixRow] = [
    _MatrixRow(
        1,
        _row1,
        Verdict.BLOCKED,
        _confidence_blocked,
        "Complete dependency nodes before re-verification.",
        "Matrix row 1: dependencies incomplete.",
    ),
    _MatrixRow(
        2,
        _row2,
        Verdict.OUT_OF_SCOPE_CHANGE_DETECTED,
        _confidence_constraint_violation,
        "Revert out-of-scope changes and re-submit for verification.",
        "Matrix row 2: constraint violation detected.",
    ),
    _MatrixRow(
        3,
        _row3,
        Verdict.FAIL,
        _confidence_fail_criteria,
        "Fix failing acceptance criteria and re-submit.",
        "Matrix row 3: deterministic hard fail.",
    ),
    _MatrixRow(
        4,
        _row4,
        Verdict.FAIL,
        lambda ctx: _confidence_semantic_blend(
            ctx, [j for j in ctx.judgments if j.judgment == "judged_fail"]
        ),
        "Address semantic failures and re-submit.",
        "Matrix row 4: semantic judged_fail on indeterminate criteria.",
    ),
    _MatrixRow(
        5,
        _row5,
        Verdict.NEEDS_MORE_EVIDENCE,
        _confidence_all_criteria,
        "Provide missing required artifacts and re-submit.",
        "Matrix row 5: all criteria pass but required artifacts missing.",
    ),
    _MatrixRow(
        6,
        _row6,
        Verdict.NEEDS_MORE_EVIDENCE,
        lambda ctx: _confidence_semantic_blend(ctx, ctx.judgments),
        "Provide missing required artifacts and re-submit.",
        "Matrix row 6: semantic pass but required artifacts missing.",
    ),
    _MatrixRow(
        7,
        _row7,
        Verdict.NEEDS_MORE_EVIDENCE,
        lambda ctx: _confidence_semantic_blend(
            ctx, [j for j in ctx.judgments if j.judgment == "indeterminate"]
        ),
        "Provide missing required artifacts and re-run semantic investigation.",
        "Matrix row 7: semantic indeterminate and required artifacts missing.",
    ),
    _MatrixRow(
        8,
        _row8,
        Verdict.NEEDS_MORE_EVIDENCE,
        lambda ctx: _confidence_semantic_blend(ctx, ctx.judgments, cap_at_half=True),
        "Re-run semantic investigation with sufficient budget.",
        "Matrix row 8: semantic budget exhausted.",
    ),
    _MatrixRow(
        9,
        _row9,
        Verdict.NEEDS_MORE_EVIDENCE,
        lambda ctx: _confidence_semantic_blend(ctx, []),
        "Re-run semantic investigation to produce judgments.",
        "Matrix row 9: semantic produced no judgments.",
    ),
    _MatrixRow(
        10,
        _row10,
        Verdict.NEEDS_HUMAN_REVIEW,
        lambda ctx: _confidence_semantic_blend(
            ctx, [j for j in ctx.judgments if j.judgment == "indeterminate"]
        ),
        "Human review required for unresolved semantic judgments.",
        "Matrix row 10: semantic indeterminate with artifacts present.",
    ),
    _MatrixRow(
        11,
        _row11,
        Verdict.PASS,
        lambda ctx: _confidence_semantic_blend(ctx, ctx.judgments),
        "Proceed to accept_node (open evidence PR).",
        "Matrix row 11: semantic pass on indeterminate criteria.",
    ),
    _MatrixRow(
        12,
        _row12,
        Verdict.PASS,
        _confidence_all_criteria,
        "Proceed to accept_node (open evidence PR).",
        "Matrix row 12: deterministic clean pass.",
    ),
]


def decide(
    deterministic: DeterministicResult,
    semantic: SemanticOutput | None,
) -> tuple[Verdict, float, str]:
    """Pure function. No I/O, no LLM, no side effects."""
    ctx = _DecisionContext(deterministic=deterministic, semantic=semantic)
    for row in MATRIX:
        if row.matches(ctx):
            return row.verdict, row.confidence(ctx), row.required_next_action
    raise RuntimeError("decision matrix exhausted without a match")
