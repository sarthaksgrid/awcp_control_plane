"""
AWCP — Context Hashing & Staleness Detection
===============================================
Generates and compares content-addressable hashes of
context snapshots to detect stale state.

Used by the Context Graph Manager and the Degradation
Engine to trigger autonomy reduction when context
diverges from the last checkpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


HASH_ALGORITHM = "sha256"


class FreshnessState(str, Enum):
    """Result of comparing a stored context snapshot with current state."""

    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True)
class HashComparison:
    """Structured outcome for context freshness checks."""

    stored_hash: str
    current_hash: str
    state: FreshnessState
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fresh(self) -> bool:
        return self.state is FreshnessState.FRESH

    @property
    def is_stale(self) -> bool:
        return self.state is FreshnessState.STALE

    def to_dict(self) -> dict[str, Any]:
        return {
            "stored_hash": self.stored_hash,
            "current_hash": self.current_hash,
            "state": self.state.value,
            "is_fresh": self.is_fresh,
            "checked_at": self.checked_at.isoformat(),
            "details": self.details,
        }


def canonicalize_snapshot(snapshot: Any) -> str:
    """Serialize a snapshot into stable JSON before hashing."""

    return json.dumps(
        _make_json_safe(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_context_hash(snapshot: Any) -> str:
    """Return a SHA-256 hash for any JSON-like context snapshot."""

    payload = canonicalize_snapshot(snapshot).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compare_context_hashes(
    stored_hash: str,
    current_hash: str,
    *,
    details: dict[str, Any] | None = None,
) -> HashComparison:
    """Compare two context hashes and return a typed freshness result."""

    state = FreshnessState.FRESH if stored_hash == current_hash else FreshnessState.STALE
    return HashComparison(
        stored_hash=stored_hash,
        current_hash=current_hash,
        state=state,
        details=details or {},
    )


def hash_node_payload(
    *,
    node_type: str,
    content: Any,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | set[str] | tuple[str, ...] | None = None,
    source: str | None = None,
    actor: str | None = None,
) -> str:
    """Hash the immutable payload fields of a context graph node."""

    return compute_context_hash(
        {
            "actor": actor,
            "content": content,
            "metadata": metadata or {},
            "node_type": node_type,
            "source": source,
            "tags": sorted(tags or []),
        }
    )


def _make_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _make_json_safe(value.to_dict())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _make_json_safe(vars(value))
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_make_json_safe(item) for item in value)
    return value
