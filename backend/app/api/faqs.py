from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.knowledge import service
from app.models import Faq
from app.schemas_workspace import FaqIn, FaqOut

router = APIRouter(prefix="/faqs", tags=["faqs"])


def _get_owned(db: Session, faq_id: str, org_id: str) -> Faq:
    f = db.scalar(select(Faq).where(Faq.id == faq_id, Faq.org_id == org_id))
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FAQ not found")
    return f


@router.get("", response_model=list[FaqOut])
def list_faqs(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return db.scalars(select(Faq).where(Faq.org_id == auth.org_id).order_by(Faq.created_at.desc())).all()


@router.post("", response_model=FaqOut, status_code=status.HTTP_201_CREATED)
def create_faq(
    body: FaqIn, background: BackgroundTasks, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    f = Faq(org_id=auth.org_id, **body.model_dump())
    db.add(f)
    db.commit()
    background.add_task(service.index_faq, f.id)
    return f


@router.put("/{faq_id}", response_model=FaqOut)
def update_faq(
    faq_id: str,
    body: FaqIn,
    background: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    f = _get_owned(db, faq_id, auth.org_id)
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    db.commit()
    background.add_task(service.index_faq, f.id)
    return f


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(faq_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    f = _get_owned(db, faq_id, auth.org_id)
    service.delete_source_chunks(db, auth.org_id, "faq", f.id)
    db.delete(f)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
