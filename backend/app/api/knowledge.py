from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.knowledge import service
from app.models import Document, Faq

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHitOut(BaseModel):
    chunk_id: str
    source_type: str
    source_id: str
    title: str
    content: str
    score: float


@router.post("/search", response_model=list[SearchHitOut])
def search_knowledge(body: SearchRequest, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return [h.__dict__ for h in service.search(db, auth.org_id, body.query, body.top_k)]


@router.post("/reindex")
def reindex(background: BackgroundTasks, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Re-process every document and FAQ of this organization."""
    doc_ids = db.scalars(select(Document.id).where(Document.org_id == auth.org_id)).all()
    faq_ids = db.scalars(select(Faq.id).where(Faq.org_id == auth.org_id)).all()
    for d in doc_ids:
        background.add_task(service.ingest_document, d)
    for f in faq_ids:
        background.add_task(service.index_faq, f)
    return {"documents": len(doc_ids), "faqs": len(faq_ids)}
