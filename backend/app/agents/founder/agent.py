"""Founder agent: snapshot (code) -> rank and word (model) -> validate against the snapshot -> save.

If the model is unavailable the briefing is still produced from the snapshot alone, marked as not AI written.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.founder import prompts
from app.agents.founder.schemas import BriefingWrite
from app.agents.founder.snapshot import build_snapshot
from app.llm.base import LLMError, LLMUnavailable
from app.llm.factory import get_llm
from app.llm.structured import generate_structured
from app.models import AgentRun, Briefing, Organization

log = logging.getLogger("bizos.founder")


def _fallback(snapshot: dict) -> tuple[str, str, list[dict]]:
    items, f = snapshot["items"], snapshot["facts"]
    headline = f"{len(items)} thing(s) need your attention." if items else "Nothing needs your attention right now."
    summary = (
        f"In the last {f['period_days']} day(s): {f['new_leads']} new lead(s), {f['quotes_created']} quote(s). "
        f"{f['open_leads']} open lead(s) worth Rs {f['open_pipeline_value']:,.0f}."
    )
    return headline, summary, [{"item_id": i["id"], "why": i["detail"]} for i in items[:5]]


def make_briefing(db: Session, org: Organization, days: int = 7) -> Briefing:
    started = time.monotonic()
    steps: list[dict] = []

    def add(step: str, detail: str = "") -> None:
        steps.append({"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "step": step, "detail": detail})

    run = AgentRun(org_id=org.id, agent="founder", status="running")
    db.add(run)
    db.commit()
    try:
        snap = build_snapshot(db, org.id, days)
        by_id = {i["id"]: i for i in snap["items"]}
        add("Built snapshot", f"{len(snap['items'])} attention item(s)")

        ai = True
        try:
            out = generate_structured(get_llm(), prompts.SYSTEM, prompts.prompt(snap), BriefingWrite)
            headline, summary = out.headline, out.summary
            picks, seen = [], set()
            for p in out.priorities:
                if p.item_id in by_id and p.item_id not in seen:  # drop anything the model made up
                    seen.add(p.item_id)
                    picks.append({"item_id": p.item_id, "why": p.why})
            dropped = len(out.priorities) - len(picks)
            add("Model ranked items", f"{len(picks)} kept" + (f", {dropped} dropped (unknown or duplicate)" if dropped else ""))
            if not picks and by_id:  # model skipped everything: fall back to code order for high severity
                picks = [{"item_id": i["id"], "why": i["detail"]} for i in snap["items"] if i["severity"] == "high"][:5]
                add("No valid picks", "used high severity items in code order")
        except (LLMUnavailable, LLMError) as e:
            ai = False
            headline, summary, picks = _fallback(snap)
            add("Model unavailable", f"{str(e)[:200]}. Built the briefing from the snapshot only")

        b = Briefing(
            org_id=org.id, period_days=days, headline=headline[:300], summary=summary, ai_written=ai,
            facts=snap["facts"], priorities=[{"item": by_id[p["item_id"]], "why": p["why"]} for p in picks], run_id=run.id,
        )
        db.add(b)
        add("Saved briefing")
        add("Completed")
        run.status, run.summary, run.steps = "completed", headline[:200], list(steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        db.refresh(b)
        return b
    except Exception as e:
        log.exception("Founder agent crashed")
        db.rollback()
        run = db.get(AgentRun, run.id)
        add("Failed", str(e)[:300])
        run.status, run.error, run.steps = "failed", str(e)[:500], list(steps)
        db.commit()
        raise
