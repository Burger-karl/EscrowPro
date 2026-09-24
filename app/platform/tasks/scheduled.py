import asyncio
import logging
from datetime import timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.db.base import utcnow
from app.db.session import engine
from app.src.escrow import services as escrow_services
from app.src.payments import utils as payments_utils
from app.src.payments.models import PaymentTransaction, PaymentTransactionStatus
from app.src.payments.paystack_client import paystack_client


logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300            # how often the sweep runs
STALE_AFTER = timedelta(minutes=15)     # only reconcile transactions at least this old


def _find_stale_pending(session: Session) -> list[PaymentTransaction]:
    cutoff = utcnow() - STALE_AFTER
    statement = select(PaymentTransaction).where(
        PaymentTransaction.status == PaymentTransactionStatus.PENDING,
        PaymentTransaction.created_at <= cutoff,
    )
    return list(session.exec(statement).all())


def _reconcile_one(session: Session, transaction: PaymentTransaction) -> None:
    """Mirrors the charge.success branch in payments.services.handle_webhook —
    this is the fallback path for exactly the case that handler exists for,
    just triggered by time instead of by Paystack calling us."""
    try:
        verify_response = paystack_client.transactions.verify_transaction(transaction.reference)
    except Exception:
        logger.exception("sweep: could not verify %s with Paystack", transaction.reference)
        return

    verified_amount = verify_response.data.get("amount")
    verified_status = verify_response.data.get("status")

    if verified_status == "success" and verified_amount == transaction.amount_minor:
        escrow_services.confirm_funding(
            session, transaction.contract_id, Decimal(transaction.amount_minor)
        )
        payments_utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.SUCCESS)
        session.commit()
        logger.info(
            "sweep: reconciled %s as SUCCESS (webhook must have been missed)",
            transaction.reference,
        )
    elif verified_status in ("failed", "abandoned"):
        payments_utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.FAILED)
        session.commit()
        logger.info("sweep: reconciled %s as FAILED", transaction.reference)
    else:
        # Still genuinely pending on Paystack's side — leave it, try again next sweep.
        logger.info("sweep: %s still pending on Paystack, leaving as is", transaction.reference)


def run_sweep_once() -> None:
    with Session(engine) as session:
        stale = _find_stale_pending(session)
        if not stale:
            logger.info("sweep: no stale pending transactions")
            return
        logger.info("sweep: reconciling %d stale pending transaction(s)", len(stale))
        for transaction in stale:
            _reconcile_one(session, transaction)


async def _sweep_loop() -> None:
    while True:
        try:
            # run_sweep_once is sync (plain SQLModel Session + a sync Paystack
            # call) — to_thread keeps it off the event loop, same idea as
            # run_in_threadpool used for sync service calls in async routes.
            await asyncio.to_thread(run_sweep_once)
        except Exception:
            logger.exception("sweep: unexpected error, will retry next interval")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


def start_scheduler() -> asyncio.Task:
    """Call once from main.py's lifespan startup; cancel the returned task on
    shutdown. See the wiring note for the exact snippet."""
    return asyncio.create_task(_sweep_loop())
