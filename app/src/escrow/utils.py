import uuid
from decimal import Decimal

from sqlmodel import Session, select

from app.src.contracts.models import Contract
from app.src.escrow.models import IdempotencyKey, LedgerAccount, LedgerEntry


def get_contract_for_update(session: Session, contract_id: uuid.UUID) -> Contract | None:
    statement = select(Contract).where(Contract.id == contract_id).with_for_update()
    return session.exec(statement).first()


def add_ledger_entries(session: Session, entries: list[LedgerEntry]) -> list[LedgerEntry]:
    for entry in entries:
        session.add(entry)
    session.flush()
    for entry in entries:
        session.refresh(entry)
    return entries


def get_balance(session: Session, contract_id: uuid.UUID, account: LedgerAccount) -> Decimal:
    statement = select(LedgerEntry).where(
        LedgerEntry.contract_id == contract_id,
        LedgerEntry.account == account,
    )
    entries = session.exec(statement).all()
    return sum((e.amount for e in entries), Decimal("0"))


def list_entries_for_contract(session: Session, contract_id: uuid.UUID) -> list[LedgerEntry]:
    statement = (
        select(LedgerEntry)
        .where(LedgerEntry.contract_id == contract_id)
        .order_by(LedgerEntry.created_at)
    )
    return list(session.exec(statement).all())


def get_idempotency_key(session: Session, key: str) -> IdempotencyKey | None:
    return session.get(IdempotencyKey, key)


def save_idempotency_key(
    session: Session, key: str, endpoint: str, response_json: str, status_code: int
) -> IdempotencyKey:
    record = IdempotencyKey(
        key=key, endpoint=endpoint, response_json=response_json, status_code=status_code
    )
    session.add(record)
    session.flush()
    return record