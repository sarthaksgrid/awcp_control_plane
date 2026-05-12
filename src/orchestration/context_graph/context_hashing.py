"""
AWCP — Context Hashing & Staleness Detection
===============================================
Generates and compares content-addressable hashes of
context snapshots to detect stale state.

Used by the Context Graph Manager and the Degradation
Engine to trigger autonomy reduction when context
diverges from the last checkpoint.
"""

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping


class ContextHasher:
    """
    DS-3: Cryptographic Context Hashing
    Generates a stable, deterministic SHA-256 hash from a GoverningSlice.
    """

    HASH_ALGORITHM = "sha256"
    EXCLUDED_FIELDS = frozenset({"token_count"})

    @classmethod
    def canonicalize(cls, slice_obj: Any) -> Dict[str, Any]:
        """
        Convert a GoverningSlice-like object into canonical, hashable data.
        Excluded fields (e.g. token_count) are stripped because they are
        transient values that change after pruning.
        """
        return cls._normalize(cls._to_mapping(slice_obj))

    @classmethod
    def canonical_json(cls, slice_obj: Any) -> str:
        """
        Return stable JSON used as the direct input to the hash function.
        Keys are sorted and separators minimized for determinism.
        """
        return json.dumps(
            cls.canonicalize(slice_obj),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def generate_hash(cls, slice_obj: Any) -> str:
        """
        Takes a GoverningSlice object and returns its SHA-256 context hash.
        This hash is stored in the Evidence Ledger as a tamper-proof fingerprint.
        """
        context_str = cls.canonical_json(slice_obj)
        return hashlib.sha256(context_str.encode("utf-8")).hexdigest()

    @staticmethod
    def compare_hashes(current_hash: str, stored_hash: str) -> bool:
        """
        Return True when the current and stored context hashes match.
        """
        return current_hash == stored_hash

    @classmethod
    def is_stale(cls, slice_obj: Any, stored_hash: str) -> bool:
        """
        Return True when the current context no longer matches stored_hash.
        This is the primary staleness signal fed to the Degradation Engine.
        """
        return cls.generate_hash(slice_obj) != stored_hash

    @staticmethod
    def _to_mapping(slice_obj: Any) -> Mapping[str, Any]:
        if hasattr(slice_obj, "model_dump"):
            try:
                return slice_obj.model_dump(mode="json")
            except TypeError:
                return slice_obj.model_dump()

        if isinstance(slice_obj, Mapping):
            return slice_obj

        raise TypeError("ContextHasher expects a GoverningSlice, Pydantic model, or mapping")

    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return cls._normalize(cls._to_mapping(value))

        if isinstance(value, Mapping):
            return {
                str(key): cls._normalize(child)
                for key, child in value.items()
                if key not in cls.EXCLUDED_FIELDS
            }

        if isinstance(value, (list, tuple)):
            return [cls._normalize(item) for item in value]

        if isinstance(value, str):
            return " ".join(value.split())

        if isinstance(value, (datetime, date, time)):
            return value.isoformat()

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, Decimal):
            return str(value)

        return value
