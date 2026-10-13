from datetime import datetime

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    industry: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=300)
    description: str | None = None
    target_customers: str | None = None
    tone: str | None = Field(default=None, max_length=100)
    discount_policy: str | None = None
    support_email: str | None = Field(default=None, max_length=320)


class ProfileOut(ProfileIn):
    name: str


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    price: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    stock: int | None = Field(default=None, ge=0)
    specs: dict[str, str] = Field(default_factory=dict)
    is_active: bool = True


class ProductOut(ProductIn):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FaqIn(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=100)


class FaqOut(FaqIn):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    chunk_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
