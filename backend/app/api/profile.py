from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.models import BusinessProfile
from app.schemas_workspace import ProfileIn, ProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])


def _out(auth: AuthContext, prof: BusinessProfile | None) -> ProfileOut:
    return ProfileOut(
        name=auth.org.name,
        industry=auth.org.industry,
        website=auth.org.website,
        description=prof.description if prof else None,
        target_customers=prof.target_customers if prof else None,
        tone=prof.tone if prof else None,
        discount_policy=prof.discount_policy if prof else None,
        support_email=prof.support_email if prof else None,
    )


@router.get("", response_model=ProfileOut)
def get_profile(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> ProfileOut:
    return _out(auth, db.get(BusinessProfile, auth.org_id))


@router.put("", response_model=ProfileOut)
def update_profile(
    body: ProfileIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> ProfileOut:
    auth.org.industry = body.industry
    auth.org.website = body.website
    db.add(auth.org)

    prof = db.get(BusinessProfile, auth.org_id)
    if prof is None:
        prof = BusinessProfile(org_id=auth.org_id)
        db.add(prof)
    prof.description = body.description
    prof.target_customers = body.target_customers
    prof.tone = body.tone
    prof.discount_policy = body.discount_policy
    prof.support_email = body.support_email
    db.commit()
    return _out(auth, prof)
