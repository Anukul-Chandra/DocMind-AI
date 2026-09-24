"""Deterministic extraction of explicitly stated durable user facts."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCandidate:
    key: str
    value: str


class UserMemoryExtractor:
    """Recognize a small allowlist of explicit, durable statements."""

    _NAME_PATTERNS = (
        re.compile(r"^my name is ([A-Za-z][A-Za-z .'-]{0,79})[.!?]?$", re.I),
        re.compile(r"^call me ([A-Za-z][A-Za-z .'-]{0,79})[.!?]?$", re.I),
        re.compile(r"^i am ([A-Za-z][A-Za-z .'-]{0,79})[.!?]?$", re.I),
    )
    _PREFERENCE_PATTERN = re.compile(
        r"^i prefer ([^.!?\n]{1,160})[.!?]?$", re.I
    )
    _FAVORITE_PATTERN = re.compile(
        r"^my favorite ([A-Za-z][A-Za-z -]{0,39}) is ([^.!?\n]{1,120})[.!?]?$",
        re.I,
    )

    def extract(self, message: str) -> MemoryCandidate | None:
        text = " ".join(message.split()).strip()
        if not text:
            return None

        for pattern in self._NAME_PATTERNS:
            match = pattern.match(text)
            if match:
                value = _clean_value(match.group(1))
                if _looks_like_name(value):
                    return MemoryCandidate("name", value)

        match = self._PREFERENCE_PATTERN.match(text)
        if match:
            return MemoryCandidate("preference", _clean_value(match.group(1)))

        match = self._FAVORITE_PATTERN.match(text)
        if match:
            category = re.sub(r"\s+", "_", match.group(1).strip().lower())
            return MemoryCandidate(
                f"favorite_{category}", _clean_value(match.group(2))
            )
        return None


def _clean_value(value: str) -> str:
    return " ".join(value.split()).strip(" .!?\t")


def _looks_like_name(value: str) -> bool:
    words = value.split()
    if not words or len(value) > 80:
        return False
    blocked = {"a", "an", "happy", "fine", "working", "learning", "developer"}
    return all(word.lower() not in blocked for word in words)