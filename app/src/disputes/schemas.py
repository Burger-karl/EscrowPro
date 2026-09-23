import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.src.disputes.models import DisputeStatus


class DisputeOpenIn(BaseModel):
    contract_id: uuid.UUID
    milestone_id: uuid.UUID | None = None


class DisputeResolveIn(BaseModel):
    freelancer_percent: int = Field(ge=0, le=100)
    note: str | None = Field(default=None, max_length=1000)


class MessageIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    dispute_id: uuid.UUID
    author_id: uuid.UUID
    author_role: str  # 'client' or 'freelancer' or 'arbiter'
    body: str
    created_at: datetime


class DisputeOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    milestone_id: uuid.UUID | None
    opened_by: uuid.UUID
    status: DisputeStatus
    resolution_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

