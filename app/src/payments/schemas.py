import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.src.contracts.models import ContractStatus


class InitiateFundingOut(BaseModel):
    contract_id: uuid.UUID
    reference: str
    checkout_url: str
    amount: Decimal


class FundContractOut(BaseModel):
    contract_id: uuid.UUID
    status: ContractStatus
    funded_amount: Decimal
    reference: str | None = None
    checkout_url: str | None = None

    model_config = {"from_attributes": True}
