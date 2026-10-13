"""Order lookup for the support agent. Code decides what the model may say; the model never sees an order it was not given."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order

STATUS_TEXT = {
    "placed": "order placed, not packed yet",
    "packed": "packed, waiting for the courier",
    "shipped": "shipped, on the way",
    "out_for_delivery": "out for delivery today",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "returned": "returned",
}


def squash(ref: str) -> str:
    """ORD-1042, ord 1042 and #1042 compare on letters and digits only."""
    return re.sub(r"[^A-Z0-9]", "", (ref or "").upper())


def normalize(ref: str) -> str:
    return re.sub(r"\s+", "", (ref or "").upper()).lstrip("#")


def find_order(db: Session, org_id: str, ref: str, email: str | None) -> Order | None:
    """Both the order number AND the email must match, so an order number alone reveals nothing.

    The caller gets None for 'no such order' and 'wrong email' alike.
    """
    want = squash(ref)
    if not want or not email:
        return None
    rows = db.scalars(select(Order).where(Order.org_id == org_id, func.lower(Order.customer_email) == email.strip().lower())).all()
    exact = [o for o in rows if squash(o.order_ref) == want]
    if exact:
        return exact[0]
    # "1042" for "ORD-1042": only a digits-only reference, and only among this customer's own orders.
    if want.isdigit() and len(want) >= 3:
        tail = [o for o in rows if squash(o.order_ref).endswith(want)]
        if len(tail) == 1:
            return tail[0]
    return None


def order_facts(o: Order) -> str:
    """What the model may tell the customer. No address, no payment details, no price."""
    lines = [
        f"order: {o.order_ref}",
        f"status: {STATUS_TEXT.get(o.status, o.status)}",
    ]
    if o.carrier:
        lines.append(f"carrier: {o.carrier}")
    if o.tracking_id:
        lines.append(f"tracking id: {o.tracking_id}")
    if o.tracking_url:
        lines.append(f"tracking link: {o.tracking_url}")
    if o.expected_delivery and o.status in ("placed", "packed", "shipped", "out_for_delivery"):
        lines.append(f"expected delivery: {o.expected_delivery.isoformat()}")
    if o.items:
        lines.append("items: " + ", ".join(f"{i.get('quantity', 1)} x {i.get('name', '')}" for i in o.items[:10]))
    return "\n".join(lines)
