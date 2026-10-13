import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.config import settings
from app.core.db import get_db
from app.knowledge import service
from app.models import Chunk, Document
from app.schemas_workspace import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx", ".csv"}
CHUNK = 1024 * 1024


def _get_owned(db: Session, doc_id: str, org_id: str) -> Document:
    d = db.scalar(select(Document).where(Document.id == doc_id, Document.org_id == org_id))
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return d


def _out(doc: Document, chunk_count: int = 0) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.chunk_count = chunk_count
    return out


@router.get("", response_model=list[DocumentOut])
def list_documents(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    docs = db.scalars(
        select(Document).where(Document.org_id == auth.org_id).order_by(Document.created_at.desc())
    ).all()
    counts = dict(
        db.execute(
            select(Chunk.document_id, func.count())
            .where(Chunk.org_id == auth.org_id, Chunk.document_id.is_not(None))
            .group_by(Chunk.document_id)
        ).all()
    )
    return [_out(d, counts.get(d.id, 0)) for d in docs]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    filename = os.path.basename(file.filename or "").strip()
    ext = Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_EXT:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Allowed types: {', '.join(sorted(ALLOWED_EXT))}",
        )

    # Stored under org folder with a random name, never the client-supplied name.
    org_dir = Path(settings.upload_dir) / auth.org_id
    org_dir.mkdir(parents=True, exist_ok=True)
    stored = org_dir / f"{uuid.uuid4()}{ext}"

    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with stored.open("wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"File exceeds {settings.max_upload_mb} MB",
                    )
                out.write(chunk)
    except HTTPException:
        stored.unlink(missing_ok=True)
        raise

    if size == 0:
        stored.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

    doc = Document(
        org_id=auth.org_id,
        filename=filename,
        content_type=file.content_type,
        size_bytes=size,
        storage_path=str(stored),
    )
    db.add(doc)
    db.commit()
    background.add_task(service.ingest_document, doc.id)
    return _out(doc)


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    doc_id: str,
    background: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    doc = _get_owned(db, doc_id, auth.org_id)
    doc.status = "uploaded"
    db.commit()
    background.add_task(service.ingest_document, doc.id)
    return _out(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    doc = _get_owned(db, doc_id, auth.org_id)
    service.delete_source_chunks(db, auth.org_id, "document", doc.id)
    Path(doc.storage_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
