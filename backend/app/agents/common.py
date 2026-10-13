from sqlalchemy.orm import Session

from app.models import BusinessProfile, Organization


def business_context(db: Session, org: Organization) -> dict:
    """Facts about the business that agents may mention. Only what the owner filled in."""
    prof = db.get(BusinessProfile, org.id)
    ctx = {
        "name": org.name,
        "industry": org.industry,
        "description": prof.description if prof else None,
        "tone": (prof.tone if prof else None) or "friendly and professional",
        "discount_policy": prof.discount_policy if prof else None,
        "support_email": prof.support_email if prof else None,
    }
    return {k: v for k, v in ctx.items() if v}
