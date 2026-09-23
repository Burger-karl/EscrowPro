import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaymentTransactionStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentTransaction(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "payment_transactions"

    contract_id = uuid.UUID = Field(foreign_key="contracts_id", nullable=False, index=True)
    reference: str = Field(nullable=False, unique=True, index=True)
    amount_minor: int = Field(nullable=False, gt=0)
    status: PaymentTransactionStatus = Field(default=PaymentTransactionStatus, nullable=False)


class ProcessedEvent(table=True):
    __tablename__ = "processed_events"

    event_id: str = Field(primary_key=True)
    reference: str = Field(nullable=False, index=True)
    processed_at: datetime = Field(default_factory=utcnow, nullable=False)

