"""Local append-only Evidence Ledger implementation for PB-2 demos."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from src.pb2.schemas import EvidenceEntry


PB2_DATA_DIR = Path(os.getenv("AWCP_PB2_DATA_DIR", "data/pb2"))


class EvidenceStore:
    """Thread-safe local evidence store.

    DevOps will later provide durable object storage or SQL persistence. This
    class is the temporary boundary PB-2 uses to keep workflow evidence visible
    to the UI, FastAPI, and Temporal worker processes.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or PB2_DATA_DIR / "evidence.jsonl"
        self._lock = Lock()

    def append(self, entry: EvidenceEntry) -> EvidenceEntry:
        """Append one immutable evidence entry."""

        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as file:
                file.write(entry.model_dump_json())
                file.write("\n")
        return entry

    def list(self, workflow_id: str | None = None) -> list[EvidenceEntry]:
        """Return all evidence, optionally filtered by workflow."""

        with self._lock:
            if not self._path.exists():
                return []
            lines = self._path.read_text(encoding="utf-8").splitlines()

        entries: list[EvidenceEntry] = []
        for line in lines:
            if not line.strip():
                continue
            entries.append(EvidenceEntry.model_validate_json(line))

        if workflow_id:
            entries = [entry for entry in entries if entry.workflow_id == workflow_id]

        return sorted(entries, key=lambda entry: entry.created_at, reverse=True)

    def clear(self) -> None:
        """Clear local demo evidence.

        This is only for development resets. Production evidence will be
        immutable once DevOps provides the real ledger boundary.
        """

        with self._lock:
            if self._path.exists():
                self._path.unlink()
