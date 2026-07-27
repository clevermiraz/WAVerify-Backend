import argparse
import sys
from datetime import UTC, datetime

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.services.billing import BillingService


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new admin user.")
    parser.add_argument("email", help="The admin's email address")
    parser.add_argument("password", help="The admin's password")

    args = parser.parse_args()
    email = args.email.strip().lower()

    configure_logging()

    with SessionLocal() as session:
        users = UserRepository(session)

        if users.get_by_email(email) is not None:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        admin = users.create(
            email=email,
            hashed_password=hash_password(args.password),
            full_name="Administrator",
            role=UserRole.ADMIN,
            is_email_verified=True,
            email_verified_at=datetime.now(UTC),
        )
        BillingService(session).create_default_wallet(admin.id)
        session.commit()

        print(f"Success! Admin user created for {email}")


if __name__ == "__main__":
    main()
