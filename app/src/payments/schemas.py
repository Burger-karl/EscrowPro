import uuid
from decimal import Decimal

from pydantic import BaseModel


class InitiateFundingOut(BaseModel):
    contract_id: uuid.UUID
    reference: str
    checkout_url: str
    amount: Decimal