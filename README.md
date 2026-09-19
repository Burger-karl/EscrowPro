# PayWork — Freelance Escrow Backend

PayWork is a backend API that holds a client's payment in escrow until
freelance work is approved, then releases it to the freelancer. It
exists to solve the trust problem in freelance work: clients don't want
to pay upfront with no guarantee of delivery, and freelancers don't want
to deliver work with no guarantee of payment. PayWork sits between them
as the neutral holder of funds.

Built as a capstone project by **Team Sapphire Hawks**.

---

## Core concepts

- **Escrow** — when a client funds a contract, the money is held by
  PayWork, not released to the freelancer immediately.
- **Milestones** — contracts are broken into milestones; each is
  approved (and paid out) independently rather than all-or-nothing.
- **Ledger** — every movement of money is recorded as an append-only
  row in a `ledger_entries` table. A balance is always the *sum* of
  entries, never a mutable counter — rows are never updated or
  deleted, so the full history of every cent is always reconstructable
  and auditable.
- **Disputes** — if a client and freelancer disagree on whether work
  was delivered, either party can raise a dispute, and an arbiter
  role resolves it.
- **Idempotency** — payment webhooks and retried requests must never
  double-charge or double-pay. This is handled at three levels:
  a client-supplied `Idempotency-Key` header, DB row locks
  (`SELECT ... FOR UPDATE`) around milestone approvals, and a
  `processed_events` table that deduplicates webhook retries.

## Tech stack

| Concern              | Technology                              |
|-----------------------|------------------------------------------|
| API framework          | FastAPI                                 |
| ORM                    | SQLModel (built on SQLAlchemy 2.x)      |
| Primary database        | PostgreSQL — contracts, escrow, ledger  |
| Migrations              | Alembic                                 |
| Cache / idempotency      | Redis                                   |
| Dispute threads / activity feed | Google Firestore                |
| Auth                     | JWT (access + refresh tokens)           |
| Password hashing         | bcrypt via passlib                      |
| Rate limiting             | slowapi                                 |
| Dependency management      | uv (`pyproject.toml` + `uv.lock`)     |
| Containerization           | Docker / docker-compose               |

## Roles

Every user has exactly one role, which gates what they can do:

- **client** — funds contracts, approves milestones
- **freelancer** — delivers work, receives payouts
- **finance** — internal role for payout/reconciliation operations
- **arbiter** — resolves disputes between clients and freelancers

---

## Project structure

```
EscrowProj/
├── alembic.ini              # Alembic config (DB URL is set from .env at runtime)
├── alembic/
│   ├── env.py                # wires Alembic to app settings + SQLModel metadata
│   ├── script.py.mako        # migration file template
│   └── versions/              # generated migration files
├── pyproject.toml            # project dependencies (used by `uv sync`)
├── uv.lock                   # locked dependency versions — commit this
├── Dockerfile                 # container build (uses uv)
├── docker-compose.yaml           # api + postgres + redis services
├── .env                       # local secrets — NEVER commit (see .gitignore)
├── .env.example                # template showing which vars are needed
└── app/
    ├── main.py                 # FastAPI app: router includes, middleware, lifespan
    ├── seed.py                    # optional: seed dev data
    ├── core/                       # cross-cutting infrastructure
    │   ├── config.py                 # pydantic-settings — reads .env
    │   ├── security.py                # JWT encode/decode, password hashing
    │   ├── dependencies.py             # get_db, get_current_user, require_role
    │   ├── errors.py                    # single error response shape
    │   ├── middleware.py                 # request-id + timing/logging
    │   └── rate_limit.py                   # slowapi limiter
    ├── db/
    │   ├── session.py                      # SQLModel engine/session
    │   └── base.py                          # shared id/timestamp mixins
    ├── platform/                             # external service clients
    │   ├── cache/redis_client.py
    │   ├── events/broadcaster.py
    │   ├── firestore/client.py
    │   └── tasks/{background,scheduled}.py
    ├── src/                                    # domain-first business logic
    │   ├── accounts/     # users, registration, login, JWT issuance
    │   ├── contracts/    # client ↔ freelancer agreements, milestones
    │   ├── escrow/        # holding + releasing funds, the ledger
    │   ├── disputes/       # dispute threads (Firestore-backed)
    │   ├── payments/        # inbound payment webhook handling
    │   └── payouts/          # outbound payouts to freelancers
    │       # each domain follows: models.py, schemas.py, repository.py
    │       # (or utils.py), services.py, router.py
    └── tests/
        └── domains/       # one test module per domain
```

**Why domain-first, not layer-first:** everything related to one
business concept (e.g. `contracts`) lives together in one folder,
rather than being scattered across separate `models/`, `views/`,
`serializers/` top-level folders. This keeps related code close
together as the project grows across five-plus domains.

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — dependency manager
- Docker Desktop (for Postgres + Redis, and optionally the API itself)
- Git

## Setup

**1. Clone and enter the project:**

```bash
git clone <repo-url>
cd EscrowProj
```

**2. Install dependencies:**

```bash
uv sync
```

This reads `pyproject.toml` + `uv.lock` and creates a `.venv/`
automatically with exact locked versions.

**3. Configure environment variables:**

```bash
cp .env.example .env
```

Then open `.env` and fill in real values for:

- `JWT_SECRET_KEY` and `WEBHOOK_SECRET` — generate with:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
  (run twice, once per secret)
- `DATABASE_URL` — must match the Postgres credentials in
  `docker-compose.yaml`
- Firestore credentials, if you're working on the disputes domain

**Never commit `.env`** — it's already in `.gitignore`. Only
`.env.example` (with placeholder values) is tracked.

**4. Start Postgres and Redis:**

```bash
docker-compose up -d postgres redis
```

Confirm both are healthy:

```bash
docker-compose ps
```

**5. Run database migrations:**

From the project root (`EscrowProj/`, same level as `alembic.ini`):

```bash
alembic upgrade head
```

**6. Run the API:**

```bash
uvicorn app.main:app --reload
```

The API is now available at `http://localhost:8000`, with interactive
docs at `http://localhost:8000/docs`.

### Running everything in Docker instead

If you'd rather not run Postgres/Redis/the API separately:

```bash
docker-compose up -d
```

This brings up all three services together, with the API
hot-reloading against your local `app/` folder.

---

## Working with migrations

Whenever you add or change a model in any `src/<domain>/models.py`:

```bash
alembic revision --autogenerate -m "short description of the change"
```

**Always open the generated file in `alembic/versions/` and check it**
before applying — autogenerate is a helpful first draft, not
guaranteed correct (for example, it can miss the `import sqlmodel`
line needed for `AutoString` columns; the `script.py.mako` template
already accounts for this going forward).

Apply the migration:

```bash
alembic upgrade head
```

Roll back the most recent migration if needed:

```bash
alembic downgrade -1
```

---

## Running tests

```bash
uv run pytest
```

---

## Authentication

PayWork uses JWT for authentication — a short-lived **access token**
(sent as a `Bearer` token on every authenticated request) and a
longer-lived **refresh token** (used to obtain a new access token
without logging in again).

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/auth/register` | POST | Create an account, returns tokens |
| `/api/v1/auth/login` | POST | Authenticate, returns tokens (rate-limited: 5/min) |
| `/api/v1/auth/refresh` | POST | Exchange a refresh token for a new token pair |

Example:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"a@paywork.dev","password":"password123","full_name":"Test Client","role":"client"}'
```

To call an authenticated endpoint, pass the returned `access_token`:

```bash
curl http://localhost:8000/api/v1/some-protected-route \
  -H "Authorization: Bearer <access_token>"
```

---

## Git workflow

- `main` holds the current working state of the project.
- Create a feature branch for new, unfinished work:
  ```bash
  git checkout -b feature/<what-youre-building>
  ```
- Merge back into `main` once your feature is tested locally and
  working.

## Team

Built by **Team Sapphire Hawks**.

## Status

🚧 Under active development. Currently implemented: project scaffold,
database layer, Alembic migrations, and JWT authentication (accounts
domain). Contracts, escrow, disputes, payments, and payouts are in
progress.