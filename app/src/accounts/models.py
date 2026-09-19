
from enum import StrEnum

from sqlmodel import Field

from app.db.base import IDMixin, TimestampMixin, UpdatedAtMixin


class UserRole(StrEnum):
    CLIENT = "client"
    FREELANCER = "freelancer"
    FINANCE = "finance"
    ARBITER = "arbiter"


class User(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "users"

    email: str = Field(unique=True, index=True, nullable=False)
    password_hash: str = Field(nullable=False)
    full_name: str = Field(nullable=False)
    role: UserRole = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)