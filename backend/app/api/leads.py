from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.sales.scoring import status_for_score
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from datetime import datetime, timedelta, timezone

from app.models import Conversation, Lead, LeadNote, LeadTask, Message, Quote, ToolCall
from app.schemas_agent import (
    ConversationOut,
    LeadDetail,
    LeadOut,
    LeadPatch,
    MessageOut,
    NoteIn,
    NoteOut,
    PipelineSummary,
    QuoteOut,
    TaskIn,
    TaskOut,
    TaskPatch,
    ToolCallOut,
)

router = APIRouter(prefix="/leads", tags=["leads"])

OPEN_STATUSES = ("NEW", "QUALIFYING", "WARM", "HOT")
ALL_STATUSES = OPEN_STATUSES + ("CONVERTED", "LOST")


def _get_lead(db: Session, auth: AuthContext, lead_id: str) -> Lead:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.org_id == auth.org_id))
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


@router.get("", response_model=list[LeadOut])
def list_leads(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    stmt = select(Lead).where(Lead.org_id == auth.org_id)
    if status_filter:
        if status_filter not in ALL_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status")
        stmt = stmt.where(Lead.status == status_filter)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Lead.name.ilike(like), Lead.company.ilike(like), Lead.email.ilike(like), Lead.requirement.ilike(like))
        )
    return db.scalars(stmt.order_by(Lead.score.desc(), Lead.created_at.desc())).all()


@router.get("/summary", response_model=PipelineSummary)
def pipeline_summary(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).where(Lead.org_id == auth.org_id)).all()
    counts = {s: 0 for s in ALL_STATUSES}
    open_value = won_value = lost_value = 0.0
    for l in leads:
        counts[l.status] = counts.get(l.status, 0) + 1
        v = float(l.potential_value or 0)
        if l.status == "CONVERTED":
            won_value += v
        elif l.status == "LOST":
            lost_value += v
        else:
            open_value += v
    closed = counts["CONVERTED"] + counts["LOST"]
    return PipelineSummary(
        counts=counts,
        open_value=open_value,
        won_value=won_value,
        lost_value=lost_value,
        total=len(leads),
        conversion_rate=round(counts["CONVERTED"] / closed, 3) if closed else 0.0,
    )


@router.get("/{lead_id}", response_model=LeadDetail)
def lead_detail(lead_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    notes = db.scalars(
        select(LeadNote).where(LeadNote.lead_id == lead.id, LeadNote.org_id == auth.org_id).order_by(LeadNote.created_at.desc())
    ).all()
    convs = db.scalars(
        select(Conversation)
        .where(Conversation.org_id == auth.org_id, or_(Conversation.lead_id == lead.id, Conversation.id == lead.conversation_id))
        .order_by(Conversation.created_at.asc())
    ).all()
    out: list[ConversationOut] = []
    for c in convs:
        msgs = db.scalars(
            select(Message).where(Message.conversation_id == c.id, Message.org_id == auth.org_id).order_by(Message.seq.asc())
        ).all()
        out.append(
            ConversationOut(
                id=c.id,
                escalated=c.escalated,
                escalation_reason=c.escalation_reason,
                created_at=c.created_at,
                messages=[MessageOut.model_validate(m) for m in msgs],
            )
        )
    quotes = db.scalars(select(Quote).where(Quote.lead_id == lead.id, Quote.org_id == auth.org_id).order_by(Quote.created_at.desc())).all()
    tasks = db.scalars(select(LeadTask).where(LeadTask.lead_id == lead.id, LeadTask.org_id == auth.org_id).order_by(LeadTask.status.desc(), LeadTask.due_at.asc())).all()
    calls = db.scalars(select(ToolCall).where(ToolCall.lead_id == lead.id, ToolCall.org_id == auth.org_id).order_by(ToolCall.created_at.desc())).all()
    return LeadDetail(
        lead=LeadOut.model_validate(lead),
        notes=[NoteOut.model_validate(n) for n in notes],
        conversations=out,
        quotes=[QuoteOut.model_validate(q) for q in quotes],
        tasks=[TaskOut.model_validate(t) for t in tasks],
        tool_calls=[ToolCallOut.model_validate(c) for c in calls],
    )


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: str, body: LeadPatch, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    data = body.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    for field, value in data.items():
        setattr(lead, field, value.strip() or None if isinstance(value, str) else value)
    if new_status == "OPEN":
        lead.status = status_for_score(lead.score)
    elif new_status:
        lead.status = new_status
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def add_note(lead_id: str, body: NoteIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    note = LeadNote(org_id=auth.org_id, lead_id=lead.id, author_name=auth.user.full_name, body=body.body.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{lead_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(lead_id: str, note_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    note = db.scalar(
        select(LeadNote).where(LeadNote.id == note_id, LeadNote.lead_id == lead.id, LeadNote.org_id == auth.org_id)
    )
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{lead_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def add_task(lead_id: str, body: TaskIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    t = LeadTask(
        org_id=auth.org_id,
        lead_id=lead.id,
        title=body.title.strip(),
        due_at=datetime.now(timezone.utc) + timedelta(days=body.due_in_days),
        created_by=auth.user.full_name,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/{lead_id}/tasks/{task_id}", response_model=TaskOut)
def update_task(lead_id: str, task_id: str, body: TaskPatch, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    lead = _get_lead(db, auth, lead_id)
    t = db.scalar(select(LeadTask).where(LeadTask.id == task_id, LeadTask.lead_id == lead.id, LeadTask.org_id == auth.org_id))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    t.status = body.status
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Removes the lead with its notes, tasks and quotes (database cascade) and its conversations."""
    lead = _get_lead(db, auth, lead_id)
    convs = db.scalars(
        select(Conversation).where(Conversation.org_id == auth.org_id, or_(Conversation.lead_id == lead.id, Conversation.id == lead.conversation_id))
    ).all()
    for c in convs:
        db.delete(c)
    db.delete(lead)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
