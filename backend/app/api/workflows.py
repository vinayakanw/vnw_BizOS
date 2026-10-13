from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.automation import scheduler
from app.core.config import settings
from app.core.db import get_db
from app.models import Lead, Workflow, WorkflowRun
from app.workflows.definitions import DEFAULT_WORKFLOWS, TRIGGER_LABELS, WorkflowDef
from app.workflows.engine import run_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowOut(BaseModel):
    id: str
    name: str
    description: str | None
    trigger: str
    trigger_label: str
    enabled: bool
    conditions: list[dict]
    steps: list[dict]
    run_count: int = 0
    last_run_at: datetime | None = None
    created_at: datetime


class WorkflowPatch(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)


class RunOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str | None = None
    lead_id: str | None
    lead_name: str | None = None
    trigger: str
    status: str
    steps: list[dict]
    error: str | None
    created_at: datetime


class ManualRunIn(BaseModel):
    lead_id: str


def _wf_out(wf: Workflow, count: int = 0, last: datetime | None = None) -> WorkflowOut:
    return WorkflowOut(
        id=wf.id, name=wf.name, description=wf.description, trigger=wf.trigger,
        trigger_label=TRIGGER_LABELS.get(wf.trigger, wf.trigger), enabled=wf.enabled,
        conditions=wf.conditions, steps=wf.steps, run_count=count, last_run_at=last, created_at=wf.created_at,
    )


def _get(db: Session, auth: AuthContext, wf_id: str) -> Workflow:
    wf = db.scalar(select(Workflow).where(Workflow.id == wf_id, Workflow.org_id == auth.org_id))
    if wf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    return wf


def _runs_out(db: Session, org_id: str, runs: list[WorkflowRun]) -> list[RunOut]:
    wf_names = {w.id: w.name for w in db.scalars(select(Workflow).where(Workflow.org_id == org_id)).all()}
    lead_ids = {r.lead_id for r in runs if r.lead_id}
    leads = {}
    if lead_ids:
        for l in db.scalars(select(Lead).where(Lead.id.in_(lead_ids), Lead.org_id == org_id)).all():
            leads[l.id] = l.name or l.email or "Unknown customer"
    return [
        RunOut(
            id=r.id, workflow_id=r.workflow_id, workflow_name=wf_names.get(r.workflow_id), lead_id=r.lead_id,
            lead_name=leads.get(r.lead_id) if r.lead_id else None, trigger=r.trigger, status=r.status,
            steps=r.steps, error=r.error, created_at=r.created_at,
        )
        for r in runs
    ]


@router.get("", response_model=list[WorkflowOut])
def list_workflows(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    wfs = db.scalars(select(Workflow).where(Workflow.org_id == auth.org_id).order_by(Workflow.created_at)).all()
    stats = {
        wid: (n, last)
        for wid, n, last in db.execute(
            select(WorkflowRun.workflow_id, func.count(), func.max(WorkflowRun.created_at))
            .where(WorkflowRun.org_id == auth.org_id)
            .group_by(WorkflowRun.workflow_id)
        ).all()
    }
    return [_wf_out(w, *stats.get(w.id, (0, None))) for w in wfs]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(body: WorkflowDef, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    d = body.model_dump(mode="json")
    wf = Workflow(
        org_id=auth.org_id, name=d["name"].strip(), description=d["description"], trigger=d["trigger"],
        enabled=d["enabled"], conditions=d["conditions"], steps=d["steps"],
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return _wf_out(wf)


@router.post("/install-defaults", response_model=list[WorkflowOut])
def install_defaults(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Adds the recommended workflows this org does not have yet (matched by name)."""
    have = set(db.scalars(select(Workflow.name).where(Workflow.org_id == auth.org_id)).all())
    for raw in DEFAULT_WORKFLOWS:
        if raw["name"] in have:
            continue
        d = WorkflowDef.model_validate(raw).model_dump(mode="json")
        db.add(
            Workflow(
                org_id=auth.org_id, name=d["name"], description=d["description"], trigger=d["trigger"],
                enabled=True, conditions=d["conditions"], steps=d["steps"],
            )
        )
    db.commit()
    return list_workflows(auth, db)


@router.patch("/{wf_id}", response_model=WorkflowOut)
def update_workflow(wf_id: str, body: WorkflowPatch, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    wf = _get(db, auth, wf_id)
    if body.enabled is not None:
        wf.enabled = body.enabled
    if body.name is not None:
        wf.name = body.name.strip()
    db.commit()
    db.refresh(wf)
    return _wf_out(wf)


@router.delete("/{wf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(wf_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    db.delete(_get(db, auth, wf_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{wf_id}/run", response_model=RunOut)
def run_manually(wf_id: str, body: ManualRunIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Test a workflow on a lead. Ignores trigger and conditions; logged as a manual run."""
    wf = _get(db, auth, wf_id)
    lead = db.scalar(select(Lead).where(Lead.id == body.lead_id, Lead.org_id == auth.org_id))
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    run = run_workflow(db, wf, lead, "manual")
    db.commit()
    db.refresh(run)
    return _runs_out(db, auth.org_id, [run])[0]


@router.get("/runs", response_model=list[RunOut])
def list_runs(limit: int = Query(default=30, ge=1, le=100), auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.org_id == auth.org_id).order_by(WorkflowRun.created_at.desc()).limit(limit)).all()
    return _runs_out(db, auth.org_id, list(runs))


@router.get("/scheduler/status")
def scheduler_status(auth: AuthContext = Depends(get_auth)):
    return {
        "enabled": settings.scheduler_interval_seconds > 0,
        "interval_seconds": settings.scheduler_interval_seconds,
        "last_tick_at": scheduler.state["last_tick_at"],
    }


@router.post("/check-inactive")
def check_inactive_now(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Run the quiet-lead check for this org right now instead of waiting for the timer."""
    return {"runs": scheduler.check_inactive(db, auth.org_id)}
