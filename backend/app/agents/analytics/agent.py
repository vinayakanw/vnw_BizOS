"""Analytics agent: plan (model picks reports) -> run reports (code, this org only) -> answer (model, grounded on results).

The model never touches the database and never produces numbers that are not in the report results.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.analytics import prompts
from app.agents.analytics.metrics import CATALOG, run_metric
from app.agents.analytics.schemas import Answer, Plan
from app.llm.base import LLMError
from app.llm.factory import get_llm
from app.llm.structured import generate_structured
from app.models import AgentRun, Organization

log = logging.getLogger("bizos.analytics")

MAX_DAYS, MAX_N, MAX_REPORTS = 365, 50, 3


def _clamp(v: int | None, hi: int) -> int | None:
    return None if v is None else max(1, min(v, hi))


def _describe(m) -> str:
    bits = [f"{k}={v}" for k, v in (("days", m.days), ("n", m.n), ("order_by", m.order_by)) if v is not None]
    return f"{m.metric}({', '.join(bits)})"


def ask(db: Session, org: Organization, question: str) -> dict:
    started = time.monotonic()
    steps: list[dict] = []

    def add(step: str, detail: str = "") -> None:
        steps.append({"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "step": step, "detail": detail})

    run = AgentRun(org_id=org.id, agent="analytics", status="running")
    db.add(run)
    add("Received question", question[:200])
    db.commit()

    def finish(status: str, summary: str | None, error: str | None = None) -> None:
        run.status, run.summary, run.error = status, summary, error
        run.steps = list(steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()

    try:
        llm = get_llm()
        plan = generate_structured(llm, prompts.plan_system(), prompts.plan_prompt(question), Plan)

        if plan.out_of_scope or not plan.metrics:
            add("Out of scope", "No prepared report answers this question")
            answer = "I can't answer that from the data I have. I can report on: " + "; ".join(
                f"{name.replace('_', ' ')}" for name in CATALOG
            ) + ". Try asking about one of those."
            finish("completed", f"out of scope: {question[:80]}")
            return {"answer": answer, "results": [], "run_id": run.id, "steps": steps, "out_of_scope": True}

        results = []
        for m in plan.metrics[:MAX_REPORTS]:
            r = run_metric(db, org.id, m.metric, days=_clamp(m.days, MAX_DAYS), n=_clamp(m.n, MAX_N), order_by=m.order_by)
            results.append(r)
            add("Ran report", f"{_describe(m)}: {len(r['rows'])} row(s)")

        out = generate_structured(llm, prompts.ANSWER_SYSTEM, prompts.answer_prompt(question, results), Answer)
        add("Wrote answer", f"{len(out.answer)} characters")
        add("Completed")
        finish("completed", f"{len(results)} report(s): " + ", ".join(r["metric"] for r in results))
        return {"answer": out.answer, "results": results, "run_id": run.id, "steps": steps, "out_of_scope": False}
    except LLMError as e:
        db.rollback()
        run = db.get(AgentRun, run.id)
        add("Failed", str(e)[:300])
        finish("failed", None, str(e)[:500])
        raise
    except Exception as e:
        log.exception("Analytics agent crashed")
        db.rollback()
        run = db.get(AgentRun, run.id)
        add("Failed", str(e)[:300])
        finish("failed", None, str(e)[:500])
        raise
