"""
AWCP — Context Hashing & Staleness Detection
===============================================
Generates and compares content-addressable hashes of
context snapshots to detect stale state.

Used by the Context Graph Manager and the Degradation
Engine to trigger autonomy reduction when context
diverges from the last checkpoint.
"""

# DS-3 Cryptographic Context Hashing

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional


class FreshnessState(str, Enum):
    """
    Week 1 DS-3 freshness classification for context hash comparison.
    """

    FRESH = "fresh"
    STALE = "stale"


class ContextHasher:
    """
    DS-3: Cryptographic Context Hashing
    Generates a stable, deterministic SHA-256 hash from a GoverningSlice.
    """

    HASH_ALGORITHM = "sha256"
    EXCLUDED_FIELDS = frozenset({"token_count"})

    @classmethod
    def canonicalize(cls, slice_obj: Any) -> dict[str, Any]:
        """
        Convert a GoverningSlice-like object into canonical, hashable data.
        """
        return cls._normalize(cls._to_mapping(slice_obj))

    @classmethod
    def canonical_json(cls, slice_obj: Any) -> str:
        """
        Return stable JSON used as the direct input to the hash function.
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

        if isinstance(value, (set, frozenset)):
            normalized_items = [cls._normalize(item) for item in value]
            return sorted(normalized_items, key=lambda item: json.dumps(item, sort_keys=True))

        if isinstance(value, str):
            return " ".join(value.split())

        if isinstance(value, (datetime, date, time)):
            return value.isoformat()

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, Decimal):
            return str(value)

        return value


@dataclass(frozen=True)
class HashComparison:
    """
    Structured Week 1 DS-3 hash comparison result.
    """

    stored_hash: str
    current_hash: str
    is_fresh: bool
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> FreshnessState:
        return FreshnessState.FRESH if self.is_fresh else FreshnessState.STALE

    @property
    def is_stale(self) -> bool:
        return not self.is_fresh

    def to_dict(self) -> dict[str, Any]:
        return {
            "stored_hash": self.stored_hash,
            "current_hash": self.current_hash,
            "state": self.state.value,
            "is_fresh": self.is_fresh,
            "is_stale": self.is_stale,
            "details": dict(self.details),
        }


def canonicalize_snapshot(value: Any) -> str:
    """
    Return the canonical JSON snapshot used by Week 1 hashing and DS-2 folding.
    """
    return ContextHasher.canonical_json(value)


def compute_context_hash(value: Any) -> str:
    """
    Compatibility wrapper for the shared DS-3 hashing surface.
    """
    return ContextHasher.generate_hash(value)


def compare_context_hashes(
    stored_hash: str,
    current_hash: str,
    *,
    details: Optional[dict[str, Any]] = None,
) -> HashComparison:
    """
    Compare two context hashes and return a structured result.
    """
    return HashComparison(
        stored_hash=stored_hash,
        current_hash=current_hash,
        is_fresh=ContextHasher.compare_hashes(current_hash, stored_hash),
        details=dict(details or {}),
    )


def hash_node_payload(
    *,
    node_type: str,
    content: Any,
    metadata: Optional[Mapping[str, Any]] = None,
    tags: Optional[Iterable[str]] = None,
    source: Optional[str] = None,
    actor: Optional[str] = None,
) -> str:
    """
    Hash a single context-node payload for the context graph.
    """
    payload = {
        "node_type": node_type,
        "content": content,
        "metadata": dict(metadata or {}),
        "tags": list(tags or []),
        "source": source,
        "actor": actor,
    }
    return compute_context_hash(payload)


# Week 2 DS-3 : Stale Context Detection
@dataclass(frozen=True)
class StaleContextConflict:
    """
    A concrete mismatch between agent working memory and verified ledger state.
    """

    key: str
    working_memory_value: Any
    ledger_value: Any
    ledger_entry_id: Optional[str] = None
    ledger_timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class StaleContextReport:
    """
    Result of comparing current working memory against the evidence ledger.
    """

    is_stale: bool
    current_hash: str
    ledger_hash: Optional[str] = None
    latest_entry_id: Optional[str] = None
    latest_entry_timestamp: Optional[datetime] = None
    reasons: list[str] = field(default_factory=list)
    conflicts: list[StaleContextConflict] = field(default_factory=list)

    def as_signal(self) -> dict[str, Any]:
        """
        Return a compact signal payload for the degradation trigger evaluator.
        """
        return {
            "stale_context": self.is_stale,
            "current_hash": self.current_hash,
            "ledger_hash": self.ledger_hash,
            "latest_entry_id": self.latest_entry_id,
            "latest_entry_timestamp": self.latest_entry_timestamp.isoformat()
            if self.latest_entry_timestamp
            else None,
            "reasons": list(self.reasons),
            "conflicts": [
                {
                    "key": conflict.key,
                    "working_memory_value": conflict.working_memory_value,
                    "ledger_value": conflict.ledger_value,
                    "ledger_entry_id": conflict.ledger_entry_id,
                    "ledger_timestamp": conflict.ledger_timestamp.isoformat()
                    if conflict.ledger_timestamp
                    else None,
                }
                for conflict in self.conflicts
            ],
        }


class StaleContextDetector:
    """
    Week 2 DS-3: compare agent working memory against verified ledger state.

    Detection has two paths:
      1. Hash mismatch against the latest chronological evidence checkpoint.
      2. State-fact conflicts when ledger entries expose changed variables.
    """

    FAILED_OUTCOMES = frozenset({"blocked", "denied", "error", "failed", "rejected"})
    LEDGER_STATE_KEYS = (
        "state_changes",
        "changed_variables",
        "verified_state",
        "facts",
    )
    MEMORY_STATE_KEYS = (
        "working_memory",
        "current_memory",
        "remembered_state",
        "facts",
        "state",
    )

    def __init__(self, hasher: type[ContextHasher] = ContextHasher):
        self.hasher = hasher

    def evaluate(
        self,
        current_context: Any,
        evidence_entries: Optional[Iterable[Any]] = None,
    ) -> StaleContextReport:
        """
        Flag stale context using the current context and chronological ledger.
        """
        current_hash = self.hasher.generate_hash(current_context)
        ledger_entries = self._chronological_entries(
            evidence_entries if evidence_entries is not None else self._active_evidence(current_context)
        )
        latest_entry = ledger_entries[-1] if ledger_entries else None
        latest_hash = self._read_field(latest_entry, "context_hash") if latest_entry else None

        reasons: list[str] = []
        if latest_hash and not self.hasher.compare_hashes(current_hash, latest_hash):
            reasons.append("context_hash_mismatch")

        latest_ledger_state = self._latest_ledger_state(ledger_entries)
        working_memory_state = self._working_memory_state(current_context)
        conflicts = self._find_conflicts(working_memory_state, latest_ledger_state)
        if conflicts:
            reasons.append("working_memory_conflicts_with_ledger")

        return StaleContextReport(
            is_stale=bool(reasons),
            current_hash=current_hash,
            ledger_hash=latest_hash,
            latest_entry_id=self._read_field(latest_entry, "entry_id") if latest_entry else None,
            latest_entry_timestamp=self._read_timestamp(latest_entry) if latest_entry else None,
            reasons=reasons,
            conflicts=conflicts,
        )

    def _active_evidence(self, current_context: Any) -> Iterable[Any]:
        if isinstance(current_context, Mapping):
            return current_context.get("active_evidence", [])
        return getattr(current_context, "active_evidence", [])

    def _chronological_entries(self, evidence_entries: Iterable[Any]) -> list[Any]:
        verified_entries = [
            entry for entry in evidence_entries or [] if self._is_verified_entry(entry)
        ]
        return sorted(
            verified_entries,
            key=lambda entry: (
                self._read_timestamp(entry) or datetime.min,
                self._read_field(entry, "entry_id") or "",
            ),
        )

    def _is_verified_entry(self, entry: Any) -> bool:
        outcome = self._read_field(entry, "outcome")
        if outcome is None:
            return True
        return str(outcome).strip().lower() not in self.FAILED_OUTCOMES

    def _latest_ledger_state(self, ledger_entries: list[Any]) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for entry in ledger_entries:
            state_changes = self._extract_ledger_state_fields(entry)
            timestamp = self._read_timestamp(entry)
            entry_id = self._read_field(entry, "entry_id")
            for key, value in state_changes.items():
                latest[key] = {
                    "value": value,
                    "entry_id": entry_id,
                    "timestamp": timestamp,
                }
        return latest

    def _working_memory_state(self, current_context: Any) -> dict[str, Any]:
        current_data = self.hasher.canonicalize(current_context)
        state: dict[str, Any] = {}
        state.update(self._extract_state_fields(current_data, self.MEMORY_STATE_KEYS))

        metadata = current_data.get("metadata")
        if isinstance(metadata, Mapping):
            state.update(self._extract_state_fields(metadata, self.MEMORY_STATE_KEYS))

        for history_item in current_data.get("recent_history", []):
            if isinstance(history_item, Mapping):
                state.update(self._extract_state_fields(history_item, self.MEMORY_STATE_KEYS))

        return state

    def _find_conflicts(
        self,
        working_memory_state: Mapping[str, Any],
        ledger_state: Mapping[str, Mapping[str, Any]],
    ) -> list[StaleContextConflict]:
        conflicts: list[StaleContextConflict] = []
        for key, working_value in working_memory_state.items():
            ledger_fact = ledger_state.get(key)
            if not ledger_fact:
                continue

            ledger_value = ledger_fact["value"]
            if self.hasher._normalize(working_value) == self.hasher._normalize(ledger_value):
                continue

            conflicts.append(
                StaleContextConflict(
                    key=key,
                    working_memory_value=working_value,
                    ledger_value=ledger_value,
                    ledger_entry_id=ledger_fact.get("entry_id"),
                    ledger_timestamp=ledger_fact.get("timestamp"),
                )
            )
        return conflicts

    def _extract_state_fields(
        self,
        source: Any,
        candidate_keys: Iterable[str],
    ) -> dict[str, Any]:
        if not isinstance(source, Mapping):
            return {}

        extracted: dict[str, Any] = {}
        for key in candidate_keys:
            value = source.get(key)
            if isinstance(value, Mapping):
                extracted.update(self._flatten_state(value))
        return extracted

    def _extract_ledger_state_fields(self, entry: Any) -> dict[str, Any]:
        extracted = self._extract_state_fields(entry, self.LEDGER_STATE_KEYS)
        artifact_fold = self._read_field(entry, "artifact_fold")
        extracted.update(self._extract_artifact_fold_changes(artifact_fold))
        return extracted

    def _extract_artifact_fold_changes(self, artifact_fold: Any) -> dict[str, Any]:
        if artifact_fold is None:
            return {}

        changes = self._read_field(artifact_fold, "changes")
        if not isinstance(changes, list):
            return {}

        extracted: dict[str, Any] = {}
        for change in changes:
            path = self._read_field(change, "path")
            if not path:
                continue

            after_value = self._read_field(change, "after")
            if isinstance(after_value, Mapping):
                extracted.update(self._flatten_state(after_value, str(path)))
            else:
                extracted[str(path)] = after_value
        return extracted

    def _flatten_state(self, value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, Mapping):
                flattened.update(self._flatten_state(child, path))
            else:
                flattened[path] = child
        return flattened

    def _read_field(self, entry: Any, field_name: str) -> Optional[Any]:
        if entry is None:
            return None
        if isinstance(entry, Mapping):
            return entry.get(field_name)
        return getattr(entry, field_name, None)

    def _read_timestamp(self, entry: Any) -> Optional[datetime]:
        timestamp = self._read_field(entry, "timestamp")
        if isinstance(timestamp, datetime):
            return timestamp
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp)
            except ValueError:
                return None
        return None
