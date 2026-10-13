import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge import service as knowledge
from app.models import Product


def _words(terms: list[str]) -> list[str]:
    seen: list[str] = []
    for t in terms:
        for w in re.findall(r"[A-Za-z0-9+\-]{3,}", t.lower()):
            if w not in seen:
                seen.append(w)
    return seen[:10]


def find_products(db: Session, org_id: str, terms: list[str], budget: float | None, limit: int = 6) -> list[dict]:
    """Active products of THIS org, best fit first: within budget, most keyword matches, closest to budget."""
    base = select(Product).where(Product.org_id == org_id, Product.is_active.is_(True))
    words = _words(terms)
    candidates: list[Product] = []
    if words:
        conds = []
        for w in words:
            like = f"%{w}%"
            conds += [Product.name.ilike(like), Product.category.ilike(like), Product.description.ilike(like), Product.sku.ilike(like)]
        candidates = list(db.scalars(base.where(or_(*conds)).limit(200)).all())
    if not candidates:  # nothing matched the words: fall back to the catalog
        candidates = list(db.scalars(base.limit(200)).all())

    def matches(p: Product) -> int:
        hay = " ".join(filter(None, [p.name, p.category, p.description, p.sku])).lower()
        return sum(1 for w in words if w in hay)

    def key(p: Product):
        price = float(p.price)
        if budget:
            over = price > budget
            return (over, -matches(p), abs(budget - price))
        return (False, -matches(p), price)

    out = []
    for p in sorted(candidates, key=key)[:limit]:
        price = float(p.price)
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "price": price,
                "currency": p.currency,
                "stock": p.stock,
                "specs": p.specs or {},
                "description": (p.description or "")[:300],
                "within_budget": (price <= budget) if budget else None,
            }
        )
    return out


def search_knowledge(db: Session, org_id: str, query: str, top_k: int = 4) -> list[dict]:
    hits = knowledge.search(db, org_id, query, top_k)
    return [
        {"title": h.title, "source_type": h.source_type, "content": h.content, "score": h.score}
        for h in hits
        if h.score >= settings.knowledge_min_score
    ]
