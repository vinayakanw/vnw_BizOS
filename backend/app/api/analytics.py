from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.analytics.agent import ask
from app.agents.analytics.metrics import run_metric
from app.core import ratelimit
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.llm.base import LLMError, LLMUnavailable

router = APIRouter(prefix="/agents/analytics", tags=["analytics agent"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/ask", dependencies=[Depends(ratelimit.by_org("llm", 30, 60))])
def ask_question(body: AskIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    try:
        return ask(db, auth.org, body.question.strip())
    except LLMUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI model returned an unusable answer. Please try again.")


@router.get("/overview")
def overview(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Fixed dashboard numbers. No AI involved, so it is instant and free."""
    return {
        "pipeline": run_metric(db, auth.org_id, "pipeline_summary"),
        "leads_over_time": run_metric(db, auth.org_id, "leads_over_time", days=14),
        "stale": run_metric(db, auth.org_id, "stale_leads", days=3),
        "tasks": run_metric(db, auth.org_id, "tasks_summary"),
    }
