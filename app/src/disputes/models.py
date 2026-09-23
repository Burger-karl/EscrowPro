import uuid
from enum import StrEnum

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin



class DisputeStatus(StrEnum):
    OPEN = "open"         # client/freelancer disagree on milestone completion
    RESOLVED = "resolved" # dispute resolved, milestone completed


class Dispute(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "disputes"

    milestone_id: uuid.UUID = Field(foreign_key="milestones.id", nullable=False, index=True)
    status: DisputeStatus = Field(default=DisputeStatus.OPEN, nullable=False)

    # The artbiter's ruling, filled in on resolve
    resolution_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))