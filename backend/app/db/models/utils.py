"""Shared helpers for database models."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)
