"""Orders the business enters or imports so the support agent can answer "where is my order"."""

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.models import Order
from app.models.order import ORDER_STATUSES
from app.orders_lookup import normalize

router = APIRouter(prefix="/orders", tags=["orders"])
MAX_IMPORT_ROWS = 1000


class OrderItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=100000)


class OrderIn(BaseModel):
    order_ref: str = Field(min_length=1, max_length=60)
    customer_name: str | None = Field(default=None, max_length=200)
    customer_email: EmailStr
    status: str = "placed"
    carrier: str | None = Field(default=None, max_length=100)
    tracking_id: str | None = Field(default=None, max_length=100)
    tracking_url: str | None = Field(default=None, max_length=500)
    items: list[OrderItem] = Field(default_factory=list, max_length=50)
    total: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    placed_at: datetime | None = None
    expected_delivery: date | None = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ORDER_STATUSES:
            raise ValueError("status must be one of: " + ", ".join(ORDER_STATUSES))
        return v

    @field_validator("tracking_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("tracking_url must start with http:// or https://")
        return v


class OrderOut(BaseModel):
    id: str
    order_ref: str
    customer_name: str | None
    customer_email: str
    status: str
    carrier: str | None
    tracking_id: str | None
    tracking_url: str | None
    items: list[dict]
    total: float | None
    currency: str
    placed_at: datetime | None
    expected_delivery: date | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


def _get(db: Session, auth: AuthContext, order_id: str) -> Order:
    o = db.scalar(select(Order).where(Order.id == order_id, Order.org_id == auth.org_id))
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return o


def _apply(o: Order, b: OrderIn) -> None:
    o.order_ref = normalize(b.order_ref)
    o.customer_name = (b.customer_name or "").strip() or None
    o.customer_email = str(b.customer_email).lower()
    o.status = b.status
    o.carrier, o.tracking_id, o.tracking_url = (b.carrier or "").strip() or None, (b.tracking_id or "").strip() or None, b.tracking_url
    o.items = [i.model_dump() for i in b.items]
    o.total, o.currency, o.placed_at, o.expected_delivery = b.total, b.currency.upper(), b.placed_at, b.expected_delivery


@router.get("", response_model=list[OrderOut])
def list_orders(
    q: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    stmt = select(Order).where(Order.org_id == auth.org_id).order_by(Order.updated_at.desc()).limit(300)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Order.order_ref.ilike(like), Order.customer_email.ilike(like), Order.customer_name.ilike(like)))
    if status_:
        stmt = stmt.where(Order.status == status_)
    return db.scalars(stmt).all()


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(body: OrderIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    ref = normalize(body.order_ref)
    if db.scalar(select(Order).where(Order.org_id == auth.org_id, Order.order_ref == ref)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order {ref} already exists")
    o = Order(org_id=auth.org_id)
    _apply(o, body)
    db.add(o)
    db.commit()
    return o


@router.put("/{order_id}", response_model=OrderOut)
def update_order(order_id: str, body: OrderIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    o = _get(db, auth, order_id)
    ref = normalize(body.order_ref)
    if ref != o.order_ref and db.scalar(select(Order).where(Order.org_id == auth.org_id, Order.order_ref == ref)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order {ref} already exists")
    _apply(o, body)
    db.commit()
    return o


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    db.delete(_get(db, auth, order_id))
    db.commit()


def _parse_items(raw: str) -> list[dict]:
    """'2 x Laptop; Mouse' -> [{name: Laptop, quantity: 2}, {name: Mouse, quantity: 1}]"""
    out = []
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part:
            continue
        qty, name = 1, part
        for sep in (" x ", " X ", "x "):
            head, _, tail = part.partition(sep)
            if tail and head.strip().isdigit():
                qty, name = int(head), tail.strip()
                break
        out.append({"name": name[:200], "quantity": max(1, min(qty, 100000))})
    return out[:50]


@router.post("/import")
def import_orders(body: ImportIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """CSV columns: order_ref, customer_email (required); customer_name, status, carrier, tracking_id, tracking_url, items, total, currency,
    expected_delivery (YYYY-MM-DD). Existing order numbers are updated. Bad rows are reported, good rows are still saved."""
    reader = csv.DictReader(io.StringIO(body.csv.lstrip("﻿")))
    cols = {(c or "").strip().lower() for c in (reader.fieldnames or [])}
    if not {"order_ref", "customer_email"} <= cols:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The CSV needs at least the columns order_ref and customer_email")
    created = updated = 0
    errors: list[str] = []
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT_ROWS:
            errors.append(f"Stopped at {MAX_IMPORT_ROWS} rows")
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            total = Decimal(row["total"].replace(",", "")) if row.get("total") else None
            data = OrderIn(
                order_ref=row.get("order_ref", ""), customer_email=row.get("customer_email", ""), customer_name=row.get("customer_name") or None,
                status=(row.get("status") or "placed").lower().replace(" ", "_"), carrier=row.get("carrier") or None,
                tracking_id=row.get("tracking_id") or None, tracking_url=row.get("tracking_url") or None,
                items=_parse_items(row.get("items", "")), total=total, currency=(row.get("currency") or "INR"),
                expected_delivery=date.fromisoformat(row["expected_delivery"]) if row.get("expected_delivery") else None,
                placed_at=datetime.now(timezone.utc),
            )
        except (ValueError, InvalidOperation) as e:
            errors.append(f"Row {n}: {str(e).splitlines()[0][:120]}")
            continue
        ref = normalize(data.order_ref)
        existing = db.scalar(select(Order).where(Order.org_id == auth.org_id, Order.order_ref == ref))
        if existing is None:
            existing = Order(org_id=auth.org_id)
            db.add(existing)
            created += 1
        else:
            data.placed_at = existing.placed_at
            updated += 1
        _apply(existing, data)
        db.flush()
    db.commit()
    return {"created": created, "updated": updated, "errors": errors[:20]}
