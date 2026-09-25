import logging

from sqlmodel import Session

from app.core.security import hash_password
from app.db.session import engine
from app.src.accounts import utils
from app.src.accounts.models import User, UserRole

logger = logging.getLogger(__name__)


SEED_PASSWORD = "Password123!"

SEED_USERS: list[dict] = [
    {"email": "admin@paywork.dev", "full_name": "Super Admin", "role": UserRole.ADMIN},
    {"email": "client1@paywork.dev", "full_name": "Ada Client", "role": UserRole.CLIENT},
    {"email": "freelancer1@paywork.dev", "full_name": "Femi Freelancer", "role": UserRole.FREELANCER},
    {"email": "arbiter1@paywork.dev", "full_name": "Bola Arbiter", "role": UserRole.ARBITER},
    {"email": "finance1@paywork.dev", "full_name": "Chuka Finance", "role": UserRole.FINANCE},
]


def seed_users(session: Session) -> None:
    for spec in SEED_USERS:
        if utils.get_user_by_email(session, spec["email"]) is not None:
            logger.info("seed: %s already exists, skipping", spec["email"])
            continue

        user = User(
            email=spec["email"],
            password_hash=hash_password(SEED_PASSWORD),
            full_name=spec["full_name"],
            role=spec["role"],
        )
        utils.create_user(session, user)  # commits and refreshes internally
        logger.info("seed: created %s (%s)", spec["email"], spec["role"].value)



def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with Session(engine) as session:
        seed_users(session)


if __name__ == "__main__":
    main()
