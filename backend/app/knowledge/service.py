import logging
import math
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.knowledge.chunking import chunk_text
from app.knowledge.embeddings import get_embedder
from app.knowledge.parsing import extract_text
from app.models import Chunk, Document, Faq

log = logging.getLogger("bizos.knowledge")


@dataclass
class SearchHit:
    chunk_id: str
    source_type: str
    source_id: str
    title: str
    content: str
    score: float


def delete_source_chunks(db: Session, org_id: str, source_type: str, source_id: str) -> None:
    db.execute(
        delete(Chunk).where(
            Chunk.org_id == org_id, Chunk.source_type == source_type, Chunk.source_id == source_id
        )
    )


def ingest_document(doc_id: str) -> None:
    """Parse -> chunk -> embed -> store. Runs in a background task with its own session."""
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        doc.status = "processing"
        db.commit()
        try:
            text = extract_text(Path(doc.storage_path), doc.filename)
            pieces = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
            if not pieces:
                raise ValueError("No text chunks produced")
            vectors = get_embedder().embed_documents(pieces)
            delete_source_chunks(db, doc.org_id, "document", doc.id)
            db.add_all(
                Chunk(
                    org_id=doc.org_id,
                    source_type="document",
                    source_id=doc.id,
                    document_id=doc.id,
                    title=doc.filename,
                    chunk_index=i,
                    content=piece,
                    embedding=vec,
                )
                for i, (piece, vec) in enumerate(zip(pieces, vectors))
            )
            doc.status = "ready"
            db.commit()
        except Exception:
            log.exception("Ingestion failed for document %s", doc_id)
            db.rollback()
            doc = db.get(Document, doc_id)
            if doc is not None:
                doc.status = "failed"
                db.commit()
    finally:
        db.close()


def index_faq(faq_id: str) -> None:
    db = SessionLocal()
    try:
        faq = db.get(Faq, faq_id)
        if faq is None:
            return
        try:
            text = f"Q: {faq.question}\nA: {faq.answer}"
            vec = get_embedder().embed_documents([text])[0]
            delete_source_chunks(db, faq.org_id, "faq", faq.id)
            db.add(
                Chunk(
                    org_id=faq.org_id,
                    source_type="faq",
                    source_id=faq.id,
                    title=faq.question[:300],
                    chunk_index=0,
                    content=text,
                    embedding=vec,
                )
            )
            db.commit()
        except Exception:
            log.exception("FAQ indexing failed for %s", faq_id)
            db.rollback()
    finally:
        db.close()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(db: Session, org_id: str, query: str, top_k: int = 5) -> list[SearchHit]:
    """Semantic search over ONE organization's knowledge. org_id is mandatory and always filtered."""
    qvec = get_embedder().embed_query(query)

    if db.get_bind().dialect.name == "postgresql":
        dist = Chunk.embedding.cosine_distance(qvec)
        rows = db.execute(
            select(Chunk, dist.label("dist")).where(Chunk.org_id == org_id).order_by(dist).limit(top_k)
        ).all()
        scored = [(c, 1.0 - float(d)) for c, d in rows]
    else:  # SQLite (tests): brute force
        chunks = db.scalars(select(Chunk).where(Chunk.org_id == org_id)).all()
        scored = sorted(((c, _cosine(qvec, c.embedding)) for c in chunks), key=lambda t: -t[1])[:top_k]

    return [
        SearchHit(
            chunk_id=c.id,
            source_type=c.source_type,
            source_id=c.source_id,
            title=c.title,
            content=c.content,
            score=round(score, 4),
        )
        for c, score in scored
    ]
