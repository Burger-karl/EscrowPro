import uuid
from decimal import Decimal

from sqlmodel import Session, func, select

from app.src.contracts.models import Milestone
from app.src.payouts.models import Payout, PayoutStatus


def get_payout_by_milestone_id(session: Session, milestone_id: uuid.UUID) -> Payout | None:
    statement = select(Payout).where(Payout.milestone_id == milestone_id)
    return session.exec(statement).first()


def get_payout_for_update(session: Session, payout_id: uuid.UUID) -> Payout | None:
    """Row-locks the payout so two finance users can't mark it sent at the same time."""
    statement = select(Payout).where(Payout.id == payout_id).with_for_update()
    return session.exec(statement).first()


def sum_pending_for_contract(session: Session, contract_id: uuid.UUID) -> Decimal:
    """Money already requested but not yet sent, for one contract."""
    statement = (
        select(func.coalesce(func.sum(Payout.amount_minor), 0))
        .select_from(Payout)
        .join(Milestone, Milestone.id == Payout.milestone_id)
        .where(
            Milestone.contract_id == contract_id,
            Payout.status == PayoutStatus.PENDING,
        )
    )
    return Decimal(session.exec(statement).one())


def add_payout(session: Session, payout: Payout) -> Payout:
    session.add(payout)
    session.flush()
    return payout