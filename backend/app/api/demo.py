from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.knowledge import service
from datetime import date, datetime, timedelta, timezone

from app.models import BusinessProfile, Faq, Order, Product

router = APIRouter(prefix="/demo", tags=["demo"])

PRODUCTS = [
    ("StartBook 14", "SB14", "Laptops", "Entry level 14 inch laptop for everyday office work.", 31999, 100, {"CPU": "Core i3", "RAM": "8GB", "Storage": "256GB SSD", "Display": "14 inch FHD"}),
    ("WorkBook 15", "WB15", "Laptops", "Reliable 15 inch business laptop for teams.", 48999, 60, {"CPU": "Core i5", "RAM": "16GB", "Storage": "512GB SSD", "Display": "15.6 inch FHD"}),
    ("DevBook 14", "DB14", "Laptops", "14 inch developer laptop, great for coding, containers and builds.", 54999, 40, {"CPU": "Ryzen 7", "RAM": "16GB", "Storage": "512GB SSD", "Display": "14 inch 2.8K"}),
    ("WorkBook 15 Plus", "WB15P", "Laptops", "Faster 15 inch business laptop with a large SSD.", 62999, 25, {"CPU": "Core i7", "RAM": "16GB", "Storage": "1TB SSD", "Display": "15.6 inch FHD"}),
    ("DevBook 14 Pro", "DB14P", "Laptops", "Developer laptop with 32GB RAM for heavy workloads and local AI.", 74999, 18, {"CPU": "Ryzen 7", "RAM": "32GB", "Storage": "1TB SSD", "Display": "14 inch 2.8K"}),
    ("ProBook Studio 16", "PBS16", "Laptops", "High end 16 inch laptop with dedicated graphics for design and ML.", 129999, 6, {"CPU": "Core i9", "RAM": "32GB", "GPU": "RTX 4060", "Storage": "1TB SSD"}),
    ("24 inch Monitor", "MON24", "Accessories", "24 inch full HD IPS monitor.", 5999, 150, {"Resolution": "1920x1080", "Panel": "IPS"}),
    ("Wireless Keyboard and Mouse Combo", "KBM1", "Accessories", "Quiet wireless keyboard and mouse set.", 1299, 300, {"Connectivity": "2.4GHz USB receiver"}),
    ("USB-C Docking Station", "DOCK1", "Accessories", "9 in 1 USB-C dock with HDMI, Ethernet and card reader.", 6499, 80, {"Ports": "HDMI, Ethernet, 3x USB-A, SD, USB-C PD"}),
]

FAQS = [
    ("What warranty do your laptops come with?", "All laptops come with a 1 year on-site warranty. Accessories have a 6 month warranty."),
    ("What is your return policy?", "You can return a product within 7 days if it is dead on arrival or has a manufacturing defect. Opened products without a defect cannot be returned."),
    ("How long does delivery take?", "Delivery takes 3 to 5 business days in metro cities and 5 to 8 business days elsewhere in India. Shipping is free on orders above Rs 50,000."),
    ("Do you provide GST invoices?", "Yes. Every order comes with a GST invoice. Please share your GSTIN when ordering."),
    ("Do you offer bulk order pricing?", "Yes. Orders of 10 or more units get a custom quote. A discount of up to 5% is available on 10 or more units. Any higher discount needs owner approval."),
    ("What payment methods do you accept?", "We accept bank transfer, UPI and credit or debit cards. Business customers can pay by bank transfer against a proforma invoice."),
    ("Do you set up the laptops before delivery?", "Yes. For orders of 10 or more laptops we can pre-install standard software and apply your company image at no extra charge."),
]


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_demo(background: BackgroundTasks, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Load a sample laptop store into an EMPTY workspace so the Sales Agent has something to sell."""
    have_products = db.scalar(select(func.count()).select_from(Product).where(Product.org_id == auth.org_id))
    have_faqs = db.scalar(select(func.count()).select_from(Faq).where(Faq.org_id == auth.org_id))
    if have_products or have_faqs:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workspace already has products or FAQs. Demo data only loads into an empty workspace.")

    for name, sku, cat, desc, price, stock, specs in PRODUCTS:
        db.add(Product(org_id=auth.org_id, name=name, sku=sku, category=cat, description=desc, price=price, currency="INR", stock=stock, specs=specs))
    faqs = [Faq(org_id=auth.org_id, question=q, answer=a, category="Demo") for q, a in FAQS]
    db.add_all(faqs)

    # Two sample orders under the signed-in user's email, so the support chat can be tried: use that email in the chat form.
    now = datetime.now(timezone.utc)
    db.add(Order(
        org_id=auth.org_id, order_ref="ORD-1001", customer_name=auth.user.full_name, customer_email=auth.user.email.lower(), status="shipped",
        carrier="BlueDart", tracking_id="BD123456789", tracking_url="https://www.bluedart.com/", placed_at=now - timedelta(days=2),
        expected_delivery=date.today() + timedelta(days=2), items=[{"name": "DevBook 14", "quantity": 2}], total=109998, currency="INR",
    ))
    db.add(Order(
        org_id=auth.org_id, order_ref="ORD-1002", customer_name=auth.user.full_name, customer_email=auth.user.email.lower(), status="delivered",
        carrier="Delhivery", tracking_id="DL555", placed_at=now - timedelta(days=9), items=[{"name": "Wireless Keyboard and Mouse Combo", "quantity": 3}], total=2700, currency="INR",
    ))
    auth.org.industry = auth.org.industry or "IT hardware reseller"
    prof = db.get(BusinessProfile, auth.org_id) or BusinessProfile(org_id=auth.org_id)
    prof.description = prof.description or "We sell business laptops and accessories to startups and companies across India."
    prof.target_customers = prof.target_customers or "Startups and small to medium businesses buying laptops for their teams."
    prof.tone = prof.tone or "friendly, professional"
    prof.discount_policy = prof.discount_policy or "Up to 5% on orders of 10 or more units. Anything higher needs owner approval. No discounts under 10 units."
    db.add(prof)
    db.commit()

    for f in faqs:
        background.add_task(service.index_faq, f.id)
    return {"products": len(PRODUCTS), "faqs": len(FAQS)}
