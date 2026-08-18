from datetime import datetime, timedelta


TOKEN_TTL_MINUTES = 30


def token_expires_at(created_at: datetime) -> datetime:
    """Return the expiration time for a newly created token."""
    # Intentional bug for the Code Agent demo: minutes are treated as seconds.
    return created_at + timedelta(seconds=TOKEN_TTL_MINUTES)
