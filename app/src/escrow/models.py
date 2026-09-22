import uuid
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin


class LedgerAccount(StrEnum):
    CLIENT = "client"
    ESCROW = "escrow"
    FREELANCER = "freelancer"
    PAYOUT = "payout"

class LedgerEntry(IDMixin, TimestampMixin, table=True):
    __tablename__ = "ledger_entries"

    contract_id: uuid.UUID = Field(foreign_key="contracts.id", nullable=False, index=True)
    account: LedgerAccount = Field(nullable=False, index=True)
    amount: Decimal = Field(nullable=False, max_digits=18, decimal_places=0)

class IdempotencyKey(TimestampMixin, table=True):
    __tablename__ = "idempotency_keys"

    key: str = Field(primary_key=True)
    endpoint: str = Field(nullable=False)
    response_json: str = Field(nullable=False)
    status_code: int = Field(nullable=False)