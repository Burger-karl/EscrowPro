import uuid

from sqlmodel import Session, select

from app.src.contracts.models import Contract, Milestone


def get_contract_by_id(session: Session, contract_id: uuid.UUID) -> Contract | None:
    return session.get(Contract, contract_id)


def create_contract_with_milestones(
    session: Session,
    contract: Contract,
    milestones: list[Milestone],
) -> Contract:
    session.add(contract)
    session.flush()  # assigns contract.id before milestones reference it

    for milestone in milestones:
        milestone.contract_id = contract.id
        session.add(milestone)

    session.commit()
    session.refresh(contract)
    return contract


def get_milestone_by_id(session: Session, milestone_id: uuid.UUID) -> Milestone | None:
    return session.get(Milestone, milestone_id)


def list_milestones_for_contract(session: Session, contract_id: uuid.UUID) -> list[Milestone]:
    statement = (
        select(Milestone)
        .where(Milestone.contract_id == contract_id)
        .order_by(Milestone.sequence)
    )
    return list(session.exec(statement).all())


def save_milestone(session: Session, milestone: Milestone) -> Milestone:
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return milestone