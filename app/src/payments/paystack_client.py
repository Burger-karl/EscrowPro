"""
One shared PaystackEase client, built from settings, imported by the
payments domain instead of each call site constructing its own.

IMPORTANT: PayStackBase() takes NO constructor arguments — it reads
PAYSTACK_SECRET_KEY via python-decouple, which looks at the OS
environment (and/or a .env file it discovers itself). Since our app
already loads secrets through pydantic-settings rather than relying
on python-decouple's own .env discovery, we explicitly copy the value
into os.environ here so PayStackBase sees it regardless of working
directory or how the process was started (plain uvicorn vs Docker).
"""
import os

from paystackease import PayStackBase

from app.core.config import settings

os.environ.setdefault("PAYSTACK_SECRET_KEY", settings.PAYSTACK_SECRET_KEY)

paystack_client = PayStackBase()
# Access sub-clients as attributes, e.g.:
#   paystack_client.transactions.initialize(...)
#   paystack_client.transactions.verify_transaction(reference)
#   paystack_client.transfer_recipients / paystack_client.transfers — for later, real payouts