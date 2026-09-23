import uuid
from enum import StrEnum

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin



class DisputeStatus(StrEnum):
    OPEN = "open"         # client/freelancer disagree on milestone completion
    RESOLVED = "resolved" # dispute resolved, milestone completed

class DisputeScope(StrEnum):
    MILESTONE = "milestone"         # dispute is about a single milestone
    CONTRACT = "contract"           # dispute is about a contract


class Dispute(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "disputes"

    contract_id: uuid.UUID = Field(foreign_key="contracts.id", nullable=False, index=True)

    milestone_id: uuid.UUID | None= Field(default=None, foreign_key="milestones.id", nullable=True, index=True)

    opened_by: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)

    status: DisputeStatus = Field(default=DisputeStatus.OPEN, nullable=False)

    # The artbiter's ruling, filled in on resolve
    resolution_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))