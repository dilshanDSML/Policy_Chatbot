import asyncio
import sys
from getpass import getpass

from sqlalchemy import select

from app.api.auth import hash_password
from app.db.models import User
from app.db.session import SessionLocal


async def create_admin(email: str, password: str) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user is not None:
            print("That email already has an account; no new account was created.")
            return False

        admin = User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
        )
        session.add(admin)
        await session.commit()

    print("Admin account created.")
    return True


def main() -> None:
    email = input("Admin email: ").strip().lower()
    if not email or "@" not in email:
        raise SystemExit("Enter a valid email address.")

    password = getpass("Choose an admin password (at least 12 characters): ")
    confirmation = getpass("Enter the password again: ")

    if password != confirmation:
        raise SystemExit("The passwords didn’t match.")
    if len(password) < 12:
        raise SystemExit("Choose a password with at least 12 characters.")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(create_admin(email, password))


if __name__ == "__main__":
    main()