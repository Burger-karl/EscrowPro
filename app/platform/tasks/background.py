import logging

logger = logging.getLogger(__name__)

def send_email(to: str, subject: str, body: str) -> None:
    logger.info("EMAIL to=%s subject=%r body=%r", to, subject, body)


def notify_milestone_submitted(client_email: str, milestone_title: str) -> None:
    send_email(
        to=client_email,
        subject=f"Milestone submitted: {milestone_title}",
        body=f"Your freelancer has submitted '{milestone_title}' for your review.",
    )


def notify_milestone_approved(freelancer_email: str, milestone_title: str, amount_minor: int) -> None:
    send_email(
        to=freelancer_email,
        subject=f"Milestone approved: {milestone_title}",
        body=f"'{milestone_title}' was approved and {amount_minor} was released to your escrow balance.",
    )


def notify_dispute_opened(client_email: str, freelancer_email: str, contract_title: str) -> None:
    for recipient in (client_email, freelancer_email):
        send_email(
            to=recipient,
            subject=f"Dispute opened on {contract_title}",
            body=f"A dispute has been opened on '{contract_title}'. An arbiter will review it.",
        )


def notify_dispute_resolved(client_email: str, freelancer_email: str, contract_title: str) -> None:
    for recipient in (client_email, freelancer_email):
        send_email(
            to=recipient,
            subject=f"Dispute resolved on {contract_title}",
            body=f"The arbiter has resolved the dispute on '{contract_title}'.",
        )


def notify_payout_sent(freelancer_email: str, amount_minor: int) -> None:
    send_email(
        to=freelancer_email,
        subject="Payout sent",
        body=f"A payout of {amount_minor} has been sent to you.",
    )


def generate_receipt(contract_id: str, amount_minor: int, reference: str) -> str:
    """Returns a plain-text receipt — a stand-in for a real PDF/HTML template.
    Swap the body for a real generator later without changing any call site."""
    receipt = (
        f"PayWork Receipt\n"
        f"Contract: {contract_id}\n"
        f"Reference: {reference}\n"
        f"Amount: {amount_minor}\n"
    )
    logger.info("RECEIPT generated for contract=%s reference=%s", contract_id, reference)
    return receipt