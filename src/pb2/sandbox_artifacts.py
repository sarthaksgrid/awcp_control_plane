"""Sandbox artifact folding for PB-2 trace capture."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def fold_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    """Compress sandbox output into the fields the Evidence Ledger needs.

    Future DS artifact-folding logic can replace this function. For now it
    keeps state-changing fields, output sizes, and a cryptographic digest.
    """

    serialized = json.dumps(raw, sort_keys=True, default=str)
    state_changes = {
        key: value
        for key, value in raw.items()
        if any(marker in key.lower() for marker in ("id", "status", "amount", "diff", "write", "updated"))
    }

    return {
        "artifact_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "original_size_bytes": len(serialized.encode("utf-8")),
        "state_changes": state_changes,
        "preview": serialized[:500],
    }
