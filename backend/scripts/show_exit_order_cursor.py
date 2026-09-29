from sqlalchemy import select

from app.db import SessionLocal
from app.models import IntegrationCursor


def main():
    with SessionLocal() as db:
        cursor = db.scalar(select(IntegrationCursor).where(IntegrationCursor.source == "EXIT_ORDERS"))
        print({
            "source": "EXIT_ORDERS",
            "cursor": cursor.cursor_value if cursor else None,
            "last_success_at": cursor.last_success_at.isoformat() if cursor and cursor.last_success_at else None,
            "last_error": cursor.last_error if cursor else None,
            "status": "ready_for_mapping",
        })


if __name__ == "__main__":
    main()
