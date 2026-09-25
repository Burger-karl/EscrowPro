import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.src.contracts.models import ContractStatus
from app.src.escrow.models import LedgerAccount


class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    account: LedgerAccount
    amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class StatementOut(BaseModel):
    contract_id: uuid.UUID
    client_balance: Decimal
    escrow_balance: Decimal
    entries: list[LedgerEntryOut]
    freelancer_balance: Decimal
    payout_balance: Decimal
    total_entries: int = 0
    limit: int = 50
    offset: int = 0


class FundContractOut(BaseModel):
    contract_id: uuid.UUID
    status: ContractStatus
    funded_amount: Decimal

    model_config = {"from_attributes": True}