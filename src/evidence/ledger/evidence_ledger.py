"""
AWCP — Replayable Evidence Ledger
====================================
Immutable, append-only store of all control-plane events.

Week 2 DS-2 focus:
  - Parse large JSON artifacts from tool calls
  - Extract only state-changing variables
  - Fold the compact mutation summary into the evidence ledger

Provides:
  - write_entry()             — append a general evidence entry
  - fold_tool_artifact()      — parse/fold a tool payload into evidence
  - get_entries()             — query entries by workflow/branch
  - get_replay_trace()        — retrieve full replay chain
  - get_rollback_point()      — find nearest safe rollback
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from src.orchestration.context_graph.context_hashing import (
    canonicalize_snapshot,
    compute_context_hash,
)


class EvidenceLedgerError(RuntimeError):
    """Base error raised by the evidence ledger."""


class ArtifactPayloadError(EvidenceLedgerError, ValueError):
    """Raised when a tool artifact payload cannot be parsed."""


class StateChangeOperation(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    UPSERTED = "upserted"
    ADDED = "added"
    REMOVED = "removed"
    PATCHED = "patched"
    MUTATED = "mutated"


@dataclass(frozen=True)
class StateChange:
    """Compact representation of one state-changing variable."""

    path: str
    operation: StateChangeOperation
    before: Any = None
    after: Any = None
    system: str | None = None
    resource_id: str | None = None
    field: str | None = None
    source: str = "tool_payload"
    value_hash: str = ""

    def __post_init__(self) -> None:
        if not self.value_hash:
            object.__setattr__(
                self,
                "value_hash",
                compute_context_hash(
                    {
                        "after": self.after,
                        "before": self.before,
                        "field": self.field,
                        "operation": self.operation.value,
                        "path": self.path,
                        "resource_id": self.resource_id,
                        "system": self.system,
                    }
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "operation": self.operation.value,
            "before": self.before,
            "after": self.after,
            "system": self.system,
            "resource_id": self.resource_id,
            "field": self.field,
            "source": self.source,
            "value_hash": self.value_hash,
        }


@dataclass(frozen=True)
class ArtifactFold:
    """Folded, replayable summary of a potentially huge tool artifact."""

    artifact_id: str
    workflow_id: str
    branch_id: str
    actor_id: str
    tool_name: str
    payload_hash: str
    state_change_hash: str
    changes: list[StateChange]
    payload_size_bytes: int
    omitted_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    folded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def change_count(self) -> int:
        return len(self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "tool_name": self.tool_name,
            "payload_hash": self.payload_hash,
            "state_change_hash": self.state_change_hash,
            "payload_size_bytes": self.payload_size_bytes,
            "change_count": self.change_count,
            "changes": [change.to_dict() for change in self.changes],
            "omitted_paths": self.omitted_paths,
            "metadata": self.metadata,
            "folded_at": self.folded_at.isoformat(),
        }


@dataclass(frozen=True)
class LedgerEntry:
    """One immutable evidence ledger row."""

    entry_id: str
    workflow_id: str
    branch_id: str
    actor_id: str
    action: str
    context_hash: str
    outcome: str
    policy_result: str | None = None
    approval_token: str | None = None
    degradation_state: dict[str, Any] | None = None
    replay_trace_ref: str | None = None
    rollback_pointer: str | None = None
    artifact_fold: ArtifactFold | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "context_hash": self.context_hash,
            "outcome": self.outcome,
            "policy_result": self.policy_result,
            "approval_token": self.approval_token,
            "degradation_state": self.degradation_state,
            "replay_trace_ref": self.replay_trace_ref,
            "rollback_pointer": self.rollback_pointer,
            "artifact_fold": self.artifact_fold.to_dict() if self.artifact_fold else None,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class EvidenceLedger:
    """Append-only in-memory ledger with Week 2 artifact folding support."""

    def __init__(
        self,
        *,
        max_changes_per_artifact: int = 250,
        max_value_chars: int = 1_000,
    ) -> None:
        self.max_changes_per_artifact = max_changes_per_artifact
        self.max_value_chars = max_value_chars
        self._entries: list[LedgerEntry] = []

    def write_entry(
        self,
        *,
        workflow_id: str,
        branch_id: str,
        actor_id: str,
        action: str,
        context_hash: str,
        outcome: str,
        policy_result: str | None = None,
        approval_token: str | None = None,
        degradation_state: Mapping[str, Any] | None = None,
        replay_trace_ref: str | None = None,
        rollback_pointer: str | None = None,
        artifact_fold: ArtifactFold | None = None,
        metadata: Mapping[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> LedgerEntry:
        """Append a new immutable evidence entry."""

        payload = {
            "action": action,
            "actor_id": actor_id,
            "artifact_id": artifact_fold.artifact_id if artifact_fold else None,
            "branch_id": branch_id,
            "context_hash": context_hash,
            "entry_index": len(self._entries) + 1,
            "outcome": outcome,
            "workflow_id": workflow_id,
        }
        entry = LedgerEntry(
            entry_id=entry_id or f"evidence-{compute_context_hash(payload)[:16]}",
            workflow_id=workflow_id,
            branch_id=branch_id,
            actor_id=actor_id,
            action=action,
            context_hash=context_hash,
            outcome=outcome,
            policy_result=policy_result,
            approval_token=approval_token,
            degradation_state=dict(degradation_state) if degradation_state else None,
            replay_trace_ref=replay_trace_ref,
            rollback_pointer=rollback_pointer,
            artifact_fold=artifact_fold,
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        return entry

    def fold_tool_artifact(
        self,
        *,
        workflow_id: str,
        branch_id: str,
        actor_id: str,
        tool_name: str,
        payload: Any,
        context_hash: str,
        policy_result: str | None = None,
        approval_token: str | None = None,
        rollback_pointer: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerEntry:
        """Parse a tool-call artifact, extract mutations, and write ledger evidence."""

        parsed_payload = parse_artifact_payload(payload)
        payload_hash = compute_context_hash(parsed_payload)
        payload_size_bytes = len(canonicalize_snapshot(parsed_payload).encode("utf-8"))
        extracted = extract_state_changes(
            parsed_payload,
            max_changes=self.max_changes_per_artifact,
            max_value_chars=self.max_value_chars,
        )
        changes = extracted["changes"]
        state_change_hash = compute_context_hash([change.to_dict() for change in changes])
        artifact_id = "artifact-" + compute_context_hash(
            {
                "actor_id": actor_id,
                "branch_id": branch_id,
                "payload_hash": payload_hash,
                "state_change_hash": state_change_hash,
                "tool_name": tool_name,
                "workflow_id": workflow_id,
            }
        )[:16]

        artifact_fold = ArtifactFold(
            artifact_id=artifact_id,
            workflow_id=workflow_id,
            branch_id=branch_id,
            actor_id=actor_id,
            tool_name=tool_name,
            payload_hash=payload_hash,
            state_change_hash=state_change_hash,
            changes=changes,
            payload_size_bytes=payload_size_bytes,
            omitted_paths=extracted["omitted_paths"],
            metadata={
                "folding_strategy": "state_change_extraction",
                "source_payload_type": type(payload).__name__,
                **dict(metadata or {}),
            },
        )
        return self.write_entry(
            workflow_id=workflow_id,
            branch_id=branch_id,
            actor_id=actor_id,
            action=f"tool_artifact_fold:{tool_name}",
            context_hash=context_hash,
            outcome="state_changes_extracted"
            if artifact_fold.change_count
            else "no_state_changes_detected",
            policy_result=policy_result,
            approval_token=approval_token,
            rollback_pointer=rollback_pointer,
            artifact_fold=artifact_fold,
            metadata={
                "tool_name": tool_name,
                "change_count": artifact_fold.change_count,
                "payload_hash": payload_hash,
            },
        )

    def get_entries(
        self,
        *,
        workflow_id: str | None = None,
        branch_id: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
    ) -> list[LedgerEntry]:
        """Query append-only ledger entries by common replay dimensions."""

        entries = self._entries
        if workflow_id is not None:
            entries = [entry for entry in entries if entry.workflow_id == workflow_id]
        if branch_id is not None:
            entries = [entry for entry in entries if entry.branch_id == branch_id]
        if actor_id is not None:
            entries = [entry for entry in entries if entry.actor_id == actor_id]
        if action is not None:
            entries = [entry for entry in entries if entry.action == action]
        return list(entries)

    def get_replay_trace(
        self,
        workflow_id: str,
        branch_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return ledger entries as replay-ready dictionaries."""

        return [
            entry.to_dict()
            for entry in self.get_entries(workflow_id=workflow_id, branch_id=branch_id)
        ]

    def get_rollback_point(
        self,
        workflow_id: str,
        branch_id: str | None = None,
    ) -> str | None:
        """Find the latest rollback pointer in the current branch history."""

        for entry in reversed(self.get_entries(workflow_id=workflow_id, branch_id=branch_id)):
            if entry.rollback_pointer:
                return entry.rollback_pointer
        return None


def parse_artifact_payload(payload: Any) -> Any:
    """Accept dict/list JSON payloads or serialized JSON strings/bytes."""

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ArtifactPayloadError("tool artifact payload must be valid JSON") from exc
    if isinstance(payload, (dict, list)):
        return payload
    return _model_to_dict(payload)


def extract_state_changes(
    payload: Any,
    *,
    max_changes: int = 250,
    max_value_chars: int = 1_000,
) -> dict[str, Any]:
    """Extract compact state-changing variables from a large artifact payload."""

    changes: list[StateChange] = []
    omitted_paths: list[str] = []
    _walk_payload(
        payload,
        path="$",
        context={},
        changes=changes,
        omitted_paths=omitted_paths,
        max_changes=max_changes,
        max_value_chars=max_value_chars,
    )
    return {"changes": changes, "omitted_paths": omitted_paths}


BEFORE_AFTER_PAIRS = (
    ("before", "after"),
    ("old", "new"),
    ("previous", "current"),
    ("previous_value", "current_value"),
)
OPERATION_KEYS = {
    "created": StateChangeOperation.CREATED,
    "created_records": StateChangeOperation.CREATED,
    "inserted": StateChangeOperation.CREATED,
    "added": StateChangeOperation.ADDED,
    "updated": StateChangeOperation.UPDATED,
    "updated_records": StateChangeOperation.UPDATED,
    "modified": StateChangeOperation.UPDATED,
    "patched": StateChangeOperation.PATCHED,
    "upserted": StateChangeOperation.UPSERTED,
    "deleted": StateChangeOperation.DELETED,
    "deleted_records": StateChangeOperation.DELETED,
    "removed": StateChangeOperation.REMOVED,
    "state_changes": StateChangeOperation.MUTATED,
    "mutations": StateChangeOperation.MUTATED,
    "writes": StateChangeOperation.MUTATED,
}
CONTEXT_KEYS = (
    "system",
    "service",
    "resource",
    "resource_id",
    "record_id",
    "entity_id",
    "id",
    "invoice_id",
    "customer_id",
    "case_id",
    "field",
    "name",
)


def _walk_payload(
    value: Any,
    *,
    path: str,
    context: dict[str, Any],
    changes: list[StateChange],
    omitted_paths: list[str],
    max_changes: int,
    max_value_chars: int,
) -> None:
    if len(changes) >= max_changes:
        _append_omitted(omitted_paths, path)
        return

    if isinstance(value, dict):
        merged_context = _merge_context(context, value)

        if _looks_like_json_patch(value):
            _append_change(
                changes,
                omitted_paths,
                StateChange(
                    path=str(value.get("path", path)),
                    operation=_json_patch_operation(value),
                    before=_compact_value(value.get("from"), max_value_chars),
                    after=_compact_value(value.get("value"), max_value_chars),
                    system=merged_context.get("system"),
                    resource_id=merged_context.get("resource_id"),
                    field=_field_from_path(str(value.get("path", path))),
                    source="json_patch",
                ),
                max_changes,
                path,
            )
            return

        before_after_pair = _find_before_after_pair(value)
        if before_after_pair is not None:
            before_key, after_key = before_after_pair
            _append_diff_changes(
                changes,
                omitted_paths,
                path=path,
                before=value.get(before_key),
                after=value.get(after_key),
                context=merged_context,
                max_changes=max_changes,
                max_value_chars=max_value_chars,
            )

        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in OPERATION_KEYS:
                _append_operation_changes(
                    changes,
                    omitted_paths,
                    operation=OPERATION_KEYS[key],
                    value=item,
                    path=child_path,
                    context=merged_context,
                    max_changes=max_changes,
                    max_value_chars=max_value_chars,
                )
                continue
            if key in {"conversation_history", "logs", "raw_logs", "trace", "read_only_records"}:
                continue
            _walk_payload(
                item,
                path=child_path,
                context=merged_context,
                changes=changes,
                omitted_paths=omitted_paths,
                max_changes=max_changes,
                max_value_chars=max_value_chars,
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            if len(changes) >= max_changes:
                _append_omitted(omitted_paths, f"{path}[{index}:]")
                return
            _walk_payload(
                item,
                path=f"{path}[{index}]",
                context=context,
                changes=changes,
                omitted_paths=omitted_paths,
                max_changes=max_changes,
                max_value_chars=max_value_chars,
            )


def _append_diff_changes(
    changes: list[StateChange],
    omitted_paths: list[str],
    *,
    path: str,
    before: Any,
    after: Any,
    context: dict[str, Any],
    max_changes: int,
    max_value_chars: int,
) -> None:
    for field_path, before_value, after_value, operation in _diff_values(before, after, path):
        output_path = field_path
        if field_path == path and context.get("field"):
            output_path = f"{path}.{context['field']}"
        change = StateChange(
            path=output_path,
            operation=operation,
            before=_compact_value(before_value, max_value_chars),
            after=_compact_value(after_value, max_value_chars),
            system=context.get("system"),
            resource_id=context.get("resource_id"),
            field=context.get("field") or _field_from_path(output_path),
        )
        _append_change(changes, omitted_paths, change, max_changes, output_path)


def _append_operation_changes(
    changes: list[StateChange],
    omitted_paths: list[str],
    *,
    operation: StateChangeOperation,
    value: Any,
    path: str,
    context: dict[str, Any],
    max_changes: int,
    max_value_chars: int,
) -> None:
    values = value if isinstance(value, list) else [value]
    for index, item in enumerate(values):
        item_path = f"{path}[{index}]" if isinstance(value, list) else path
        if isinstance(item, dict) and _find_before_after_pair(item):
            pair = _find_before_after_pair(item)
            if pair:
                _append_diff_changes(
                    changes,
                    omitted_paths,
                    path=item_path,
                    before=item.get(pair[0]),
                    after=item.get(pair[1]),
                    context=_merge_context(context, item),
                    max_changes=max_changes,
                    max_value_chars=max_value_chars,
                )
            continue
        item_context = _merge_context(context, item) if isinstance(item, dict) else context
        before = item if operation in {StateChangeOperation.DELETED, StateChangeOperation.REMOVED} else None
        after = None if operation in {StateChangeOperation.DELETED, StateChangeOperation.REMOVED} else item
        change = StateChange(
            path=item_path,
            operation=operation,
            before=_compact_value(before, max_value_chars),
            after=_compact_value(after, max_value_chars),
            system=item_context.get("system"),
            resource_id=item_context.get("resource_id"),
            field=item_context.get("field") or _field_from_path(item_path),
        )
        _append_change(changes, omitted_paths, change, max_changes, item_path)


def _diff_values(
    before: Any,
    after: Any,
    path: str,
) -> Iterable[tuple[str, Any, Any, StateChangeOperation]]:
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before) | set(after))
        for key in keys:
            child_path = f"{path}.{key}"
            if key not in before:
                yield child_path, None, after[key], StateChangeOperation.CREATED
            elif key not in after:
                yield child_path, before[key], None, StateChangeOperation.DELETED
            elif before[key] != after[key]:
                yield from _diff_values(before[key], after[key], child_path)
        return
    if before != after:
        yield path, before, after, StateChangeOperation.UPDATED


def _append_change(
    changes: list[StateChange],
    omitted_paths: list[str],
    change: StateChange,
    max_changes: int,
    path: str,
) -> None:
    if len(changes) >= max_changes:
        _append_omitted(omitted_paths, path)
        return
    changes.append(change)


def _append_omitted(omitted_paths: list[str], path: str) -> None:
    if path not in omitted_paths:
        omitted_paths.append(path)


def _find_before_after_pair(value: Mapping[str, Any]) -> tuple[str, str] | None:
    for before_key, after_key in BEFORE_AFTER_PAIRS:
        if before_key in value and after_key in value:
            return before_key, after_key
    return None


def _looks_like_json_patch(value: Mapping[str, Any]) -> bool:
    return "op" in value and "path" in value and value.get("op") in {
        "add",
        "remove",
        "replace",
        "move",
        "copy",
        "test",
    }


def _json_patch_operation(value: Mapping[str, Any]) -> StateChangeOperation:
    op = value.get("op")
    if op == "add":
        return StateChangeOperation.CREATED
    if op == "remove":
        return StateChangeOperation.DELETED
    if op == "replace":
        return StateChangeOperation.UPDATED
    return StateChangeOperation.PATCHED


def _merge_context(context: dict[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(context)
    for key in CONTEXT_KEYS:
        if key not in value:
            continue
        if key in {"system", "service", "resource"}:
            merged["system"] = value[key]
        elif key == "field":
            merged["field"] = value[key]
        elif key == "name" and "field" not in merged:
            merged["field"] = value[key]
        else:
            merged["resource_id"] = value[key]
    return merged


def _compact_value(value: Any, max_value_chars: int) -> Any:
    if value is None:
        return None
    rendered = canonicalize_snapshot(value)
    if len(rendered) <= max_value_chars:
        return value
    return {
        "truncated": True,
        "hash": compute_context_hash(value),
        "preview": rendered[: max(0, max_value_chars - 3)] + "...",
    }


def _field_from_path(path: str) -> str | None:
    cleaned = path.rstrip("]")
    if "/" in cleaned:
        return cleaned.split("/")[-1] or None
    cleaned = cleaned.split("[")[0]
    if "." in cleaned:
        return cleaned.split(".")[-1] or None
    return cleaned or None


def _model_to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value
