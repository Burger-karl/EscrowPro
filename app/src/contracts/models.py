import uuid
from enum import StrEnum

from sqlmodel import Field, Relationship

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin


class ContractStatus(StrEnum):
    DRAFT = "draft"           # created, not yet funded
    ACTIVE = "active"          # funded, milestones in progress
    COMPLETED = "completed"     # all milestones approved and paid out
    CANCELLED = "cancelled"      # terminated before completion


class MilestoneStatus(StrEnum):
    PENDING = "pending"         # not yet submitted by freelancer
    SUBMITTED = "submitted"      # freelancer says work is done, awaiting client
    APPROVED = "approved"         # client approved — triggers escrow release
    REJECTED = "rejected"          # client rejected — sent back to freelancer


class Contract(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "contracts"

    client_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    freelancer_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)

    title: str = Field(nullable=False)
    description: str = Field(nullable=False)
    status: ContractStatus = Field(default=ContractStatus.DRAFT, nullable=False)

    milestones: list["Milestone"] = Relationship(back_populates="contract")


class Milestone(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "milestones"

    contract_id: uuid.UUID = Field(foreign_key="contracts.id", nullable=False, index=True)

    title: str = Field(nullable=False)
    description: str = Field(nullable=False)
    # Stored as an integer count of the smallest currency unit (e.g. kobo/cents)
    # — never a float, to avoid rounding errors touching real money.
    amount_minor: int = Field(nullable=False, gt=0)
    sequence: int = Field(nullable=False)  # display/processing order within the contract
    status: MilestoneStatus = Field(default=MilestoneStatus.PENDING, nullable=False)

    contract: Contract = Relationship(back_populates="milestones")