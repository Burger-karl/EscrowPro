import uuid

from sqlmodel import Session, select

from app.src.disputes.models import Dispute, DisputeStatus


def get_dispute_by_id(session: Session, dispute_id: uuid.UUID) -> Dispute | None:
    return session.get(Dispute, dispute_id)


def get_dispute_for_update(session: Session, dispute_id: uuid.UUID) -> Dispute | None:
    """Row-locks the dispute so two resolve requests can't both settle it"""
    statement = select(Dispute).where(Dispute.id == dispute_id).with_for_update()
    return session.exec(statement).first()



def get_open_dispute_for_contract(session: Session, contract_id: uuid.UUID) -> Dispute | None:
    """Any open dispute on this contract — milestone-scoped or contract-scoped. Used to enforce "only one dispute open on a contract at a time," so a contract-level dispute and a milestone-level one can never both be live
    and racing to move the same money.
    """
    statement = select(Dispute).where(
        Dispute.contract_id == contract_id, Dispute.status == DisputeStatus.OPEN
    )
    return session.exec(statement).first()



def get_resolution_for_milestone(
    session: Session, contract_id: uuid.UUID, milestone_id: uuid.UUID
) -> dict | None:
    """The arbiter's ruling for one milestone, from whichever dispute paid it out — a dispute opened directly on that milestone, or a contract-level dispute whose payout covered it. Used by payouts to know what a freelancer is owed for a RESOLVED milestone.
    """
    statement = (
        select(Dispute)
        .where(Dispute.contract_id == contract_id, Dispute.status == DisputeStatus.RESOLVED)
        .order_by(Dispute.updated_at.desc())
    )
    for dispute in session.exec(statement).all():
        for entry in (dispute.resolution_json or {}).get("milestones", []):
            if entry["milestone_id"] == str(milestone_id):
                return entry
    return None


def add_dispute(session: Session, dispute: Dispute) -> Dispute:
    session.add(dispute)
    session.flush()
    return dispute