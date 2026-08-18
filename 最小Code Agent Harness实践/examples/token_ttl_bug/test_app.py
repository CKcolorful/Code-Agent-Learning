from datetime import datetime, timedelta, timezone

from app import token_expires_at


def test_token_expires_after_thirty_minutes() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert token_expires_at(created_at) == created_at + timedelta(minutes=30)
