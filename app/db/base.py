import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IDMixin(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=utcnow, nullable=False)


class UpdatedAtMixin(SQLModel):
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

