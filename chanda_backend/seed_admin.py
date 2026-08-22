"""
The DB's users table starts empty (data_import.sql only seeds materials +
suppliers, not users -- correctly, since only a human should own the first
admin credential). Run this once after schema.sql is applied:

    python seed_admin.py

It's idempotent: safe to re-run, it skips creation if the admin already exists.
"""
import getpass
import sys
from app.db.session import SessionLocal
from app.core.security import hash_password
from app.models import User


def main():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == "admin").first()
        if existing:
            print(f"An admin user already exists: '{existing.username}'. Nothing to do.")
            return

        print("=== Create the first Admin user for Chanda Enterprises Store System ===")
        username = input("Username [admin]: ").strip() or "admin"
        email = input("Email: ").strip()
        full_name = input("Full name: ").strip()
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")

        if not email:
            print("Email is required."); sys.exit(1)
        if password != confirm:
            print("Passwords do not match."); sys.exit(1)
        if len(password) < 6:
            print("Password must be at least 6 characters."); sys.exit(1)

        user = User(
            username=username, email=email, full_name=full_name or username,
            password_hash=hash_password(password), role="admin", department="Management",
        )
        db.add(user)
        db.commit()
        print(f"Admin user '{username}' created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
