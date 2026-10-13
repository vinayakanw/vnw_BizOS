"""Deterministic lead scoring. Rules, not model opinion, so scores are explainable and repeatable."""

from dataclasses import dataclass, field

STAGE_RANK = {"browsing": 0, "evaluating": 1, "ready_to_buy": 2}


@dataclass
class ScoreInput:
    quantity: int | None = None
    budget_per_unit: float | None = None
    requirement: str | None = None
    use_case: str | None = None
    timeline: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    purchase_stage: str = "browsing"
    product_match: bool = False


@dataclass
class ScoreResult:
    score: int
    intent: str
    status: str
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def score_lead(s: ScoreInput) -> ScoreResult:
    score = 0
    reasons: list[str] = []
    missing: list[str] = []

    if s.quantity:
        score += 15
        reasons.append(f"Specific quantity ({s.quantity} units)")
        if s.quantity >= 10:
            score += 5
            reasons.append("Bulk order (10+ units)")
    else:
        missing.append("quantity")

    if s.budget_per_unit:
        score += 15
        reasons.append("Defined budget")
    else:
        missing.append("budget")

    if s.use_case or s.requirement:
        score += 10
        reasons.append("Clear requirement or use case")

    if s.purchase_stage == "ready_to_buy":
        score += 25
        reasons.append("Asked about purchasing")
    elif s.purchase_stage == "evaluating":
        score += 12
        reasons.append("Actively evaluating options")

    if s.timeline:
        score += 10
        reasons.append(f"Has a timeline ({s.timeline})")
    else:
        missing.append("timeline")

    if s.email or s.phone:
        score += 10
        reasons.append("Shared contact details")
    else:
        missing.append("contact details")

    if s.product_match:
        score += 10
        reasons.append("We have matching products")

    if s.company:
        score += 5
        reasons.append("Business customer")

    score = min(score, 100)
    intent = {"ready_to_buy": "HIGH", "evaluating": "MEDIUM"}.get(s.purchase_stage, "LOW")
    return ScoreResult(score=score, intent=intent, status=status_for_score(score), reasons=reasons, missing=missing)


def status_for_score(score: int) -> str:
    if score >= 75:
        return "HOT"
    if score >= 50:
        return "WARM"
    if score >= 25:
        return "QUALIFYING"
    return "NEW"


def recommend_next_action(result: ScoreResult, escalation_reason: str | None) -> str:
    if escalation_reason:
        return f"Human review needed: {escalation_reason}"
    if result.status == "HOT":
        return "Contact within 15 minutes"
    if result.status == "WARM":
        return "Follow up within 24 hours"
    if result.status == "QUALIFYING":
        ask = ", ".join(result.missing[:3]) or "more detail"
        return f"Qualify further: ask for {ask}"
    return "Nurture. No action needed yet"
