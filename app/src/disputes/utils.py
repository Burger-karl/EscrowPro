import uuid

from sqlmodel import Session, select

from app.src.disputes.models import Dispute


def get_dispute_by_id(session: Session, dispute_id: uuid.UUID) -> Dispute | None:
    return session.get(Dispute, dispute_id)


def get_dispute_for_update(session: Session, dispute_id: uuid.UUID) -> Dispute | None:
    """Row-locks the dispute so two resolve requests can't both settle it"""
    statement = select(Dispute).where(Dispute.id == dispute_id).with_for_update()
    return session.exec(statement).first()


def get_latest_dispute_for_milestone(session: Session, milestone_id: uuid.UUID) -> Dispute | None:
    statement = select(Dispute).where(Dispute.milestone_id == milestone_id).order_by(Dispute.created_at.desc())

    return session.exec(statement).first()


def add_dispute(session: Session, dispute: Dispute) -> Dispute:
    session.add(dispute)
    session.flush()
    return dispute