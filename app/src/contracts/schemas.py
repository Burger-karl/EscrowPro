import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.src.contracts.models import ContractStatus, MilestoneStatus


class MilestoneCreateIn(BaseModel):
    """One milestone as supplied when creating a contract."""
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, description="What counts as this milestone being done")
    amount_minor: int = Field(gt=0, description="Amount in the smallest currency unit (e.g. kobo)")


class ContractCreateIn(BaseModel):
    freelancer_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    milestones: list[MilestoneCreateIn] = Field(min_length=1)

    @field_validator("milestones")
    @classmethod
    def at_least_one_milestone(cls, v: list[MilestoneCreateIn]) -> list[MilestoneCreateIn]:
        if not v:
            raise ValueError("a contract must have at least one milestone")
        return v


class MilestoneOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    title: str
    description: str
    amount_minor: int
    sequence: int
    status: MilestoneStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContractOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    freelancer_id: uuid.UUID
    title: str
    description: str
    status: ContractStatus
    milestones: list[MilestoneOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}