"""Create the demo org and its first user (#20).

Run once after `alembic upgrade head`:

    uv run python -m app.auth.seed

Idempotent — re-running leaves an existing org and user alone rather than
resetting a password someone has already changed.
"""

from __future__ import annotations

import argparse
import sys

from app.auth.service import EmailAlreadyRegistered, create_org, create_user
from app.data.synthetic import DEFAULT_ORG_ID
from app.db.session import SessionLocal

DEMO_EMAIL = "demo@lienrho.local"
DEMO_PASSWORD = "lienrho-demo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed an org and its first user.")
    parser.add_argument("--org-id", default=DEFAULT_ORG_ID)
    parser.add_argument("--org-name", default="LIENRHO Demo Supplier")
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        create_org(session, org_id=args.org_id, org_name=args.org_name)
        try:
            user = create_user(
                session,
                org_id=args.org_id,
                email=args.email,
                password=args.password,
                display_name="Demo Owner",
            )
        except EmailAlreadyRegistered:
            session.rollback()
            print(f"{args.email} already exists — leaving it as is.")
            return 0

        session.commit()
        print(f"Created org {args.org_id} and user {user.email}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
