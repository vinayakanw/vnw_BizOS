from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import customer_comms as comms
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.models import Quote

router = APIRouter(tags=["quotes"])


@router.post("/quotes/{quote_id}/deliver")
def deliver(quote_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Send a quote to the customer: a message in their chat, and an email if they have left the page. Can be repeated to resend."""
    if auth.user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and admins can send quotes")
    q = db.scalar(select(Quote).where(Quote.id == quote_id, Quote.org_id == auth.org_id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found")
    if q.customer_response is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The customer already responded to this quote")
    return comms.deliver_quote(db, auth.org, q)
