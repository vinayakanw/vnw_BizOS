from pydantic import BaseModel, Field


class PriorityPick(BaseModel):
    item_id: str
    why: str = Field(min_length=1, max_length=300)


class BriefingWrite(BaseModel):
    """The model ranks existing attention items and words the summary. It cannot add items or numbers."""

    headline: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1200)
    priorities: list[PriorityPick] = Field(default_factory=list, max_length=5)
