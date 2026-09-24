"""
get_user_by_email(), create_user(), get_user_by_id(), list_freelancers()
— the only place accounts issues DB queries. Services call through here.
"""
import uuid

from sqlmodel import Session, select

from app.src.accounts.models import User, UserRole


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def create_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def list_freelancers(session: Session) -> list[User]:
    statement = select(User).where(User.role == UserRole.FREELANCER, User.is_active == True)  # noqa: E712
    return list(session.exec(statement).all())