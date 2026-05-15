"""Idempotency helpers for PB-2 governed tool calls."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class IdempotencyStore:
    """In-memory idempotency cache.

    Replace this with Redis/Postgres when PB-1 and PB-2 wire the shared event
    pipeline. The API shape stays the same: compute key, check key, record key.
    """

    def __init__(self) -> None:
        self._seen: dict[str, Any] = {}

    def key_for(self, workflow_id: str, branch_id: str, action_class: str, payload: dict[str, Any]) -> str:
        """Create a deterministic key so duplicate agent retries collapse."""

        raw = json.dumps(
            {
                "workflow_id": workflow_id,
                "branch_id": branch_id,
                "action_class": action_class,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        """Return a previous result for duplicate tool calls."""

        return self._seen.get(key)

    def record(self, key: str, result: Any) -> None:
        """Store the first completed result for the idempotency key."""

        self._seen[key] = result

    def clear(self) -> None:
        """Clear local demo idempotency cache."""

        self._seen.clear()
