# PayWork — Development Log

Team Sapphire Hawks. This log tracks what was built, what broke, and how
it got fixed, in the order it happened.

---

## Day 1 — Project setup

**Built:**
- Initial FastAPI + SQLModel + PostgreSQL + Redis + Firestore scaffold, based on the design document
- `requirements.txt` (later replaced with `uv`/`pyproject.toml` — see Day 2)
- `core/config.py` (pydantic-settings), `core/errors.py` (single error response shape), `core/middleware.py` (request-id/logging), `core/rate_limit.py` (slowapi)
- `db/session.py`, `db/base.py` (`IDMixin`, `TimestampMixin`, `UpdatedAtMixin`)
- `docker-compose.yml` + `Dockerfile` for Postgres/Redis/API
- **`accounts` domain**: `User` model, JWT-based auth (`core/security.py` for token encode/decode + bcrypt hashing, `core/dependencies.py` for `get_current_user`/`require_role`), `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`

**Bugs hit and fixed:**
- `email-validator` missing from dependencies — required by `pydantic.EmailStr`, added to requirements
- `slowapi` rate limiter needed a `request: Request` parameter on the decorated endpoint to work correctly

---

## Day 2 — Alembic setup, git repo root fix, switch to `uv`

**Built:**
- Alembic wired up: `alembic/env.py` pulls `DATABASE_URL` from `app.core.config.settings` instead of a hardcoded value, targets `SQLModel.metadata`, imports each domain's models
- Initial `users` table migration
- Switched dependency management from `requirements.txt` to `uv` (`pyproject.toml` + `uv.lock`), updated `Dockerfile` to use `uv sync` instead of `pip install`

**Bugs hit and fixed:**
- `alembic revision --autogenerate` failed with `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver` — the default placeholder `sqlalchemy.url` in `alembic.ini` was never being overridden; fixed by confirming `env.py` actually contained the `settings.DATABASE_URL` override (the first attempt had the folder in the right place but stale, unedited file content)
- `alembic/` and `alembic.ini` were nested inside `app/` instead of the project root — moved both up a level so `env.py`'s `from app.core.config import settings` could resolve correctly
- Generated migrations were missing `import sqlmodel`, needed for `AutoString` columns — fixed the one migration by hand, and patched `alembic/script.py.mako` so every future migration includes the import automatically
- Postgres container failed to start: `Database is uninitialized and superuser password is not specified` — a stale/broken Docker volume from an earlier failed start; fixed with `docker-compose down -v` to force a clean reinitialization
- **Major structural bug**: discovered the git repository root was actually `EscrowProj/app/`, not `EscrowProj/` — meaning `alembic/`, `docker-compose.yaml`, `pyproject.toml`, and `.gitignore` at the true project root were completely untracked by git this whole time. Fixed by moving `.git` itself up to the correct root (`mv app/.git .git`) and re-staging everything. Along the way, caught and stopped a `.env` file from accidentally being committed (would have leaked `JWT_SECRET_KEY`, `WEBHOOK_SECRET`, DB password into git history) and cleaned stray `.pyc`/`__pycache__` files out of staging
- `passlib`'s bcrypt self-test crashed with `ValueError: password cannot be longer than 72 bytes` — a known compatibility break between `passlib==1.7.4` and `bcrypt>=4.1`; fixed by pinning `bcrypt==4.0.1`
- Swagger's "Authorize" button showed OAuth2 password-grant fields (username/password/client_id/client_secret) that didn't match how login actually works — switched `core/dependencies.py` from `OAuth2PasswordBearer` to `HTTPBearer`, so Swagger shows a single paste-your-token field instead
- `uvicorn app.main:app` and `alembic` commands failed with `ModuleNotFoundError: No module named 'app'` on separate occasions — both caused by running the command from inside `app/` instead of the project root

---

## Day 3 — `contracts` domain

**Built:**
- `Contract` and `Milestone` models (`ContractStatus`, `MilestoneStatus` enums), with `amount_minor` stored as an integer in the smallest currency unit (never a float, to avoid rounding errors on money)
- `POST /contracts` (client), `GET /contracts/{id}` (party or arbiter), `POST /milestones/{id}/submit` (assigned freelancer), `POST /milestones/{id}/approve` (contract's client)
- Authorization logic kept in `services.py`, never in the router
- Contract auto-completes once every milestone reaches `approved`

**Bugs/design fixes:**
- Added a `description` field to `Milestone` (originally only had `title`) so each milestone can spell out what "done" means, not just a short label — caught before the first migration was generated, so no schema-altering follow-up migration was needed

---

## Day 4 — `escrow` domain (the ledger)

**Built, based on the team's models diagram:**
- `LedgerEntry` — append-only, per-contract, triple-account (`client` / `escrow` / `freelancer`), signed `Decimal` amount. A balance is always `SUM(amount)`, never a stored mutable counter
- `IdempotencyKey` — keyed by the client's own `Idempotency-Key` header value, storing the full response so a retried request replays instead of double-processing
- `POST /contracts/{id}/fund` (client, requires `Idempotency-Key` header) — locks the contract row (`SELECT ... FOR UPDATE`), sums milestone amounts, writes a balanced client/escrow entry pair
- `GET /contracts/{id}/statement` (party or arbiter) — returns all account balances + full entry history
- Wired `contracts.approve_milestone()` to actually call `escrow.release_milestone()` in the same DB transaction — milestone approval and the ledger release now succeed or fail together, replacing an earlier `TODO` placeholder

**Bugs hit and fixed:**
- After a `docker-compose down -v` to fix an unrelated Postgres issue, the DB's `alembic_version` tracking was wiped, causing `Target database is not up to date` on the next `alembic revision --autogenerate` — fixed by running `alembic upgrade head` first to re-apply the pending `users` migration before generating the new one
- First-generated `contracts`/`milestones` migration was missing the newly-added `description` columns entirely — traced to a stale/leftover local file; fixed by clearing `__pycache__`, deleting the bad migration, and regenerating

---

## Day 5 — `payouts` domain — built by Chidinma

**Built (teammate):**
- `Payout` model — `freelancer_id`, `milestone_id` (unique — one payout per milestone), `amount_minor`, `status` (`pending`/`sent`)
- `POST /payouts` (freelancer) — validates the milestone is `approved`, checks available balance against the ledger before allowing the request
- `POST /payouts/{id}/mark-sent` (finance) — row-locks the payout, moves status to `sent`
- Added a fourth ledger account, `payout`, to `LedgerAccount` — extending the escrow design so a completed payout is its own balanced ledger entry (`freelancer: -amount`, `payout: +amount`), consistent with how funding and milestone release already worked, rather than payouts being tracked outside the ledger

**Bugs hit and fixed:**
- Migration for the `payouts` table existed locally but had never been applied — `POST /payouts` failed with `relation "payouts" does not exist`; fixed with `alembic upgrade head`
- `escrow.services.record_payout()` (added to support the payout ledger entries) had two typos that would have crashed on first use: `utilis.get_balance(...)` (undefined name, should be `utils`) and `LedgerEntry(..., ammount=amount)` (misspelled field name — `LedgerEntry` requires `amount`) — both fixed
- `StatementOut` schema had `freelancer_balance: Decimal` listed twice (the second silently overwrote the first at class definition — not a crash, but dead/confusing duplication) — cleaned up to one field each for `client_balance`, `escrow_balance`, `freelancer_balance`, `payout_balance`

**End-to-end verification:** funded a contract, approved one milestone, requested and marked a payout sent, then confirmed via `GET /statement` that all four account balances summed to exactly zero across the whole contract — confirming the ledger stayed internally consistent through a full funding → release → payout cycle.

---

## Day 6 (today) — `payments` domain, Paystack integration

**Built:**
- Researched and confirmed the `paystackease` SDK's actual API (`TransactionClientAPI.initialize()`/`.verify_transaction()`, HMAC-SHA512 webhook signing using the Paystack **secret key** directly — not a separate webhook secret, unlike Stripe)
- **Restructured how funding works**: `POST /contracts/{id}/fund` no longer writes ledger entries directly — it now calls Paystack's Transactions API and returns a `checkout_url`. The actual ledger movement only happens once `POST /webhooks/payment` confirms the payment really succeeded
- New `payments` domain: `PaymentTransaction` (maps our `reference` → `contract_id`, so the webhook never has to trust the request body alone for which contract a payment belongs to), `ProcessedEvent` (dedupes retried webhook deliveries, with its own `processed_at` timestamp)
- `escrow.fund_contract()` renamed/refactored to `escrow.confirm_funding()` — now purely the ledger-writing logic, called only by the payment webhook handler
- `platform/payments/paystack_client.py` — one shared Paystack client instance
- Manual HMAC-SHA512 webhook signature verification (`hmac.compare_digest` against the raw request body, verified before any JSON parsing)

**Open items flagged, not yet resolved:**
- Exact PaystackEase method name for transaction verification (`.verify_transaction()` vs `.verify()`) needs confirming against the actually-installed package version before this is fully trusted
- Local webhook testing needs `ngrok` (or similar) since Paystack can't reach `localhost` directly — not yet set up
- `payouts.mark_payout_sent` still writes ledger entries directly rather than calling Paystack's Transfers API for a real bank payout — flagged as the next piece of Paystack work, not yet built

---

## Still not started
- **`disputes`** domain — dispute threads (Firestore-backed), arbiter resolution, SSE activity stream
- **`payouts`** → real Paystack Transfers integration (currently ledger-only, no actual money leaves the system)
- **`platform/cache`, `platform/events`, `platform/tasks`** — shared Redis client, event broadcaster for SSE, background/scheduled jobs — not yet built, planned to be built alongside the domains that need them (disputes, mainly)