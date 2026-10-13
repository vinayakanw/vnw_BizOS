from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.sales.agent import ConversationNotFound, run_sales_agent
from app.core import ratelimit
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.llm.base import LLMError, LLMUnavailable
from app.models import AgentRun
from app.schemas_agent import ChatIn, ChatOut, LeadOut, RunOut

router = APIRouter(tags=["sales agent"])


@router.post("/agents/sales/chat", response_model=ChatOut, dependencies=[Depends(ratelimit.by_org("llm", 30, 60))])
def sales_chat(body: ChatIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    try:
        r = run_sales_agent(db, auth.org, body.conversation_id, body.message.strip(), body.customer_name)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    except LLMUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI model returned an unusable answer. Please try again.")
    return ChatOut(
        conversation_id=r.conversation_id,
        reply=r.reply,
        escalated=r.escalated,
        escalation_reason=r.escalation_reason,
        lead=LeadOut.model_validate(r.lead) if r.lead else None,
        run_id=r.run_id,
        actions=r.actions,
        steps=r.steps,
        products=[
            {"name": p["name"], "price": p["price"], "currency": p["currency"], "stock": p["stock"], "within_budget": p["within_budget"]}
            for p in r.products
        ],
    )


@router.get("/agents/runs", response_model=list[RunOut])
def list_runs(limit: int = 30, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 100))
    return db.scalars(
        select(AgentRun).where(AgentRun.org_id == auth.org_id).order_by(AgentRun.created_at.desc()).limit(limit)
    ).all()
