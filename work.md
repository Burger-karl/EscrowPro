# PayWork — Project Status & Handoff

For: **Team Sapphire Hawks** — this doc is to get you up to speed on what's
built, how it fits together, and exactly what's left for the `payouts`
domain.

---

## 1. What PayWork is

An escrow backend for freelance work. A client funds a contract, the
money sits in escrow (not with the freelancer yet), work happens in
milestones, and each milestone's payment is released only once the
client approves it. Full flow:

```
client creates contract (with milestones)
  → client funds the contract (money: client → escrow)
    → freelancer submits a milestone
      → client approves the milestone (money: escrow → freelancer)
        → [YOUR PART] finance pays the freelancer out (money: leaves the system)
```

---

## 2. Tech stack

- **FastAPI** + **SQLModel** (SQLAlchemy 2.x under the hood)
- **PostgreSQL** — all core data
- **Alembic** — migrations
- **Redis** — idempotency/cache support, rate limiting
- **JWT** — auth (access + refresh tokens)
- **uv** — dependency management (`pyproject.toml` + `uv.lock` — run `uv sync`, not `pip install`)
- **Docker Compose** — Postgres + Redis (+ optionally the API) run in containers

---

## 3. Project structure

```
EscrowProj/
├── alembic.ini
├── alembic/env.py           # imports every domain's models — add yours here
├── pyproject.toml / uv.lock
├── Dockerfile
├── docker-compose.yaml
├── .env.example
└── app/
    ├── main.py                # registers every domain's router — add yours here
    ├── core/
    │   ├── config.py            # settings from .env
    │   ├── security.py           # JWT + password hashing
    │   ├── dependencies.py        # get_db, get_current_user, require_role
    │   ├── errors.py               # shared error response shape
    │   ├── middleware.py             # request-id/logging
    │   └── rate_limit.py               # slowapi limiter
    ├── db/
    │   ├── session.py                   # engine/session
    │   └── base.py                       # IDMixin, TimestampMixin, UpdatedAtMixin
    └── src/
        ├── accounts/    ✅ done — users, JWT auth
        ├── contracts/   ✅ done — contracts, milestones
        ├── escrow/      ✅ done — the ledger, funding, releases
        ├── payouts/     🚧 YOUR PART — see section 6
        ├── payments/    ⏳ not started — inbound payment webhooks
        └── disputes/    ⏳ not started — dispute resolution (Firestore)
```

Every domain follows the same five-file pattern:
`models.py` → `schemas.py` → `utils.py` (repository/DB queries) →
`services.py` (business logic + authorization) → `router.py` (HTTP layer).
**Authorization lives in `services.py`, never in `router.py`.**

---

## 4. Auth — how every endpoint is protected

Every endpoint except `/auth/register` and `/auth/login` requires a
JWT in the `Authorization: Bearer <token>` header. Get one:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@paywork.dev","password":"..."}'
```

Four roles exist, each user has exactly one:
`client`, `freelancer`, `finance`, `arbiter`. You'll need the
**`finance`** role for one of your two endpoints.

In your router, use these two dependencies from `app.core.dependencies`:

```python
from app.core.dependencies import CurrentUser, DbSession
from app.core.dependencies import require_role
from app.src.accounts.models import UserRole

# any authenticated user:
def my_endpoint(session: DbSession, user: CurrentUser): ...

# only finance:
def my_endpoint(
    session: DbSession,
    user: Annotated[User, Depends(require_role(UserRole.FINANCE))],
): ...
```

---

## 5. What's already built

### `accounts` — users & JWT auth

**Model:** `User` — `id`, `email` (unique), `password_hash`, `full_name`, `role`, `is_active`, timestamps.

**Endpoints:**
| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | `/api/v1/auth/register` | anyone | 201 | 409 (email taken), 422 |
| POST | `/api/v1/auth/login` | anyone | 200 | 401 (bad credentials), 429 (rate-limited, 5/min) |
| POST | `/api/v1/auth/refresh` | anyone (valid refresh token) | 200 | 401 |

### `contracts` — agreements & milestones

**Models:**
- `Contract` — `id`, `client_id → User`, `freelancer_id → User`, `title`, `description`, `status` (`draft`/`active`/`completed`/`cancelled`)
- `Milestone` — `id`, `contract_id → Contract`, `title`, `description`, `amount_minor` (int, smallest currency unit — e.g. kobo), `sequence`, `status` (`pending`/`submitted`/`approved`/`rejected`)

**Endpoints:**
| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | `/api/v1/contracts` | client | 201 | 401, 403, 422 |
| GET | `/api/v1/contracts/{id}` | party or arbiter | 200 | 403, 404 |
| POST | `/api/v1/milestones/{id}/submit` | assigned freelancer | 200 | 403, 404, 409 |
| POST | `/api/v1/milestones/{id}/approve` | contract's client | 200 | 403, 404, 409 |

Approving a milestone **triggers an escrow release** (see below) in
the same DB transaction — approval and the money movement always
succeed or fail together.

### `escrow` — the ledger (the hardest part of this project)

**Models:**
- `LedgerEntry` — **append-only, never updated or deleted.** `id`, `contract_id → Contract`, `account` (`client`/`escrow`/`freelancer`), `amount` (signed `Decimal`), `created_at`. Money movement is always a *balanced pair* of rows (one account debited, another credited by the same amount) — they always sum to zero for a given contract.
- `IdempotencyKey` — `key` (the client's `Idempotency-Key` header value **is** the primary key), `endpoint`, `response_json`, `status_code`. Lets a retried request return the original result instead of double-processing.

**A balance is never stored — it's always computed:**
```sql
SELECT SUM(amount) FROM ledger_entries
WHERE contract_id = :id AND account = :account
```

**Endpoints:**
| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | `/api/v1/contracts/{id}/fund` | contract's client (requires `Idempotency-Key` header) | 201 (first time) / 200 (replay) | 403, 404, 409 (already funded / no milestones), 422 (missing header) |
| GET | `/api/v1/contracts/{id}/statement` | party or arbiter | 200 | 403, 404 |

**How funding and release actually work:**
- `fund_contract`: locks the contract row (`SELECT ... FOR UPDATE`), checks it's still `draft`, sums all milestone amounts, writes `client: -total` / `escrow: +total`, flips contract to `active`.
- `release_milestone`: called from `contracts.services.approve_milestone`, writes `escrow: -amount` / `freelancer: +amount` for that one milestone. **This is the function your `payouts` domain builds on top of.**

---

## 6. Your part — `payouts` domain

Per the design doc, your two endpoints:

```
POST /payouts                 freelancer   → 201 | 401, 409
POST /payouts/{id}/mark-sent  finance      → 200 | 403, 404, 409
```

### What a payout represents

Once milestones are approved, a freelancer has money sitting in the
`freelancer` account of the ledger (per contract). A payout is the
**freelancer requesting that money actually be sent to them** — the
final leg of the flow. `mark-sent` is finance confirming the transfer
actually happened (e.g. after sending it via bank transfer/Paystack/whatever
manually or via a provider).

### The freelancer's available balance

This is the number that decides whether `POST /payouts` can succeed.
Since the ledger is scoped **per contract**, a freelancer's *overall*
available balance is the sum across every contract they're on:

```python
# pseudo-code — you'll want something like this in escrow/utils.py
# or a new function you add there, then call from payouts/services.py
from sqlmodel import select
from app.src.contracts.models import Contract
from app.src.escrow.models import LedgerEntry, LedgerAccount

def get_freelancer_available_balance(session, freelancer_id) -> Decimal:
    statement = (
        select(LedgerEntry)
        .join(Contract, Contract.id == LedgerEntry.contract_id)
        .where(
            Contract.freelancer_id == freelancer_id,
            LedgerEntry.account == LedgerAccount.FREELANCER,
        )
    )
    entries = session.exec(statement).all()
    return sum((e.amount for e in entries), Decimal("0"))
```

**Important:** once a payout is created and money is considered "on
its way out," it needs to stop counting toward the *available*
balance for a second payout request — otherwise the same funds could
be paid out twice. Two common ways to handle this (worth discussing
with me or deciding together before you build):
1. When a `Payout` is created, immediately write a `freelancer: -amount`
   ledger entry too (a fourth account role, or reuse `freelancer` as
   "money leaving"), so the balance calculation naturally excludes it.
2. Or: available balance = `freelancer` balance minus the sum of all
   non-cancelled `Payout.amount` for that freelancer.

Given the project's existing pattern (money movement = ledger entries,
never a separate mutable counter), **option 1 is more consistent** with
how `escrow` already works — I'd lean that way, but flag it for
discussion since it affects your `Payout` model design.

### Suggested `Payout` model shape

```python
class PayoutStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"

class Payout(IDMixin, TimestampMixin, UpdatedAtMixin, table=True):
    __tablename__ = "payouts"

    freelancer_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    amount_minor: int = Field(nullable=False, gt=0)
    status: PayoutStatus = Field(default=PayoutStatus.PENDING, nullable=False)
```

### Follow the same 5-file pattern as the other domains

`app/src/payouts/{models.py, schemas.py, utils.py, services.py, router.py}`

- `POST /payouts` — role: `freelancer`. Validates requested amount
  against their available balance (see above). 201 on success, 409 if
  insufficient balance or another payout is already pending, 401 if
  unauthenticated.
- `POST /payouts/{id}/mark-sent` — role: `finance`. Flips status
  `pending → sent`. 200 on success, 403 if not finance, 404 if not
  found, 409 if not currently `pending`.

### Once you're building

1. Add your model import to `alembic/env.py`:
   `from app.src.payouts import models as payouts_models  # noqa: F401`
2. Add your router include to `app/main.py`
3. `alembic revision --autogenerate -m "create payouts table"` — **always
   check the generated file before applying it**, especially foreign keys
   and any `Numeric`/`Decimal` columns
4. `alembic upgrade head`

---

## 7. Local setup (if you haven't already)

```bash
git clone <repo-url>
cd EscrowProj
uv sync
cp .env.example .env   # fill in your own JWT_SECRET_KEY, WEBHOOK_SECRET, DB creds
docker-compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs` — useful for testing your
endpoints interactively without curl.

---

## 8. Conventions to follow (so things stay consistent)

- **Money is always an integer/Decimal in minor units** (kobo/cents),
  never a float — avoids rounding errors.
- **Authorization checks live in `services.py`**, raising `ForbiddenError`,
  `NotFoundError`, `ConflictError`, or `UnauthorizedError` from
  `app.core.errors` — the router never contains `if user.role != ...` logic.
- **The router only translates HTTP ↔ service calls** — no business
  logic there.
- **`utils.py` is the only place that writes raw SQLModel queries** for
  its domain — services call into utils, never `session.exec()` directly.
- Every error is returned in one shape:
  ```json
  {"error": {"code": "...", "message": "...", "request_id": "..."}}
  ```
- Branch off `main` for your work: `git checkout -b feature/payouts`,
  merge back once tested locally.

---

## 9. Still not started (for later, not your immediate scope)

- **`payments`** — inbound payment provider webhook (`POST /webhooks/payment`),
  backed by a `ProcessedEvent` table for idempotent webhook retries, calling
  into `escrow.fund_contract()`.
- **`disputes`** — dispute threads (Firestore-backed for messages), resolution
  by an arbiter, `GET /disputes/{id}/stream` (SSE).