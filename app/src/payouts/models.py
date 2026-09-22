import uuid
from enum import StrEnum

from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin


class PayoutStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"


class Payout(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "payouts"

    freelancer_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)

    milestone_id: uuid.UUID = Field(foreign_key="milestones.id", nullable=False, unique=True, index=True)

    amount_minor: int = Field(nullable=False, gt=0)
    status: PayoutStatus = Field(default=PayoutStatus.PENDING, nullable=False)