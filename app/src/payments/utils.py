from sqlmodel import Session, select

from app.src.payments.models import PaymentTransactionStatus, PaymentTransaction, ProcessedEvent


def get_transaction_by_reference(session: Session, reference: str) -> PaymentTransaction | None:
    statement = select(PaymentTransaction).where(PaymentTransaction.reference == reference)
    return session.exec(statement).first()


def save_transaction(session: Session, transaction: PaymentTransaction) -> PaymentTransaction:
    session.add(transaction)
    session.flush()
    return transaction


def mark_transaction_status(
    session: Session, transaction: PaymentTransaction, status: PaymentTransactionStatus
) -> None:
    transaction.status = status
    session.add(transaction)


def get_processed_event(session: Session, event_id: str) -> ProcessedEvent | None:
    return session.get(ProcessedEvent, event_id)