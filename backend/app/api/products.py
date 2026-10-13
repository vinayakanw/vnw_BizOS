from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.models import Product
from app.schemas_workspace import ProductIn, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


def _get_owned(db: Session, product_id: str, org_id: str) -> Product:
    # org_id in the WHERE clause: another tenant's id looks identical to a missing one.
    p = db.scalar(select(Product).where(Product.id == product_id, Product.org_id == org_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return p


@router.get("", response_model=list[ProductOut])
def list_products(
    q: str | None = None,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    stmt = select(Product).where(Product.org_id == auth.org_id).order_by(Product.created_at.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Product.name.ilike(like), Product.description.ilike(like), Product.category.ilike(like))
        )
    return db.scalars(stmt).all()


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    p = Product(org_id=auth.org_id, **body.model_dump())
    p.currency = p.currency.upper()
    db.add(p)
    db.commit()
    return p


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str, body: ProductIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    p = _get_owned(db, product_id, auth.org_id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    p.currency = p.currency.upper()
    db.commit()
    return p


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    db.delete(_get_owned(db, product_id, auth.org_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
