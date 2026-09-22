import uuid
from datetime import datetime

from pydantic import BaseModel

from app.src.payouts.models import PayoutStatus


class PayoutCreateIn(BaseModel):
    milestone_id: uuid.UUID


class PayoutOut(BaseModel):
    id: uuid.UUID
    freelancer_id: uuid.UUID
    milestone_id: uuid.UUID
    amount_minor: int
    status: PayoutStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


