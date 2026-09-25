import uuid
from decimal import Decimal

from sqlmodel import Session, func, select

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
    statement = select(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0"))).where(
        LedgerEntry.contract_id == contract_id,
        LedgerEntry.account == account,
    )
    result = session.exec(statement).one()
    return Decimal(result)


def get_balance_for_update(session: Session, contract_id: uuid.UUID, account: LedgerAccount) -> Decimal:
    # Lock the ledger rows for this contract and account before computing balance
    lock_stmt = (
        select(LedgerEntry.id)
        .where(
            LedgerEntry.contract_id == contract_id,
            LedgerEntry.account == account,
        )
        .with_for_update()
    )
    session.exec(lock_stmt).all()
    return get_balance(session, contract_id, account)


def list_entries_for_contract(
    session: Session, contract_id: uuid.UUID, limit: int | None = None, offset: int = 0
) -> list[LedgerEntry]:
    statement = (
        select(LedgerEntry)
        .where(LedgerEntry.contract_id == contract_id)
        .order_by(LedgerEntry.created_at)
        .offset(offset)
    )
    if limit is not None:
        statement = statement.limit(limit)
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