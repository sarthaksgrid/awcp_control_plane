# 02 - Artifact Ledger Folding

This document details the second DS-2 step in the Agent Workforce Control Plane (AWCP) lifecycle: **DS-2 (Week 2)**. This task builds on Week 1 context graph work by adding **Artifact Ledger Folding**: parsing large tool-call payloads, extracting only governance-relevant state changes, and writing compact replayable evidence entries.

## 1. Objective: Fold Tool Artifacts Into Evidence

In a governed workflow, agents call tools that can return very large JSON payloads. A billing update might return hundreds of read-only records, API metadata, nested before/after objects, patch operations, and audit details. Storing the whole payload as the main replay surface creates noise and makes recovery harder.

The goal of **DS-2 Week 2** is to keep the evidence ledger replayable without stuffing raw tool output into every decision.

### What does Artifact Ledger Folding do?

Artifact Ledger Folding takes a tool-call payload and extracts the state-changing facts:

1. Parse the payload, whether it arrives as a Python mapping/list or JSON string.
2. Detect state changes in common shapes such as `before`/`after`, `old`/`new`, `updated`, `deleted`, and JSON Patch operations.
3. Compact large values so evidence stays small and operator-readable.
4. Compute hashes for the original payload and extracted state-change summary.
5. Write a ledger entry with context hash, policy result, rollback pointer, and folded artifact metadata.

The result is an evidence entry that says, "this tool call changed these fields," without forcing replay and recovery logic to inspect the entire raw payload.

## 2. Why This Matters

Without artifact folding, the evidence ledger has two bad options:

1. **Store huge payloads directly.** Replay becomes noisy and expensive because every recovery step must parse large JSON blobs.
2. **Store only a generic success/failure message.** Replay loses the exact state-changing variables needed to know what happened.

Folding gives the middle path: the ledger keeps a compact, hashed summary of mutations while preserving enough metadata to audit, replay, and roll back safely.

### Technical Targets

- **Input:** Tool-call outputs, JSON strings, nested dictionaries, lists, before/after blocks, and JSON Patch payloads.
- **Output:** `LedgerEntry` records containing an `ArtifactFold` summary.
- **State Change Coverage:** Created, updated, and deleted values.
- **Integrity:** Payload hash and state-change hash are deterministic SHA-256 values.
- **Replay Metadata:** Workflow ID, branch ID, actor, action, context hash, policy result, rollback pointer, and optional degradation state.

---

## 3. Jargon Explained

| Term | Definition in AWCP |
|:---|:---|
| **Evidence Ledger** | Append-only workflow record used for replay, audit, recovery, and operator review. |
| **Artifact** | A tool-call output or sandbox result that may contain read-only data, state changes, errors, or patches. |
| **Artifact Fold** | Compact summary of an artifact containing payload hash, extracted changes, omitted paths, size, and metadata. |
| **State Change** | A created, updated, or deleted value caused by a tool call. |
| **Payload Hash** | SHA-256 hash of the normalized original payload. Used to prove the folded summary came from a specific artifact. |
| **State Change Hash** | SHA-256 hash of the extracted changes. Used to verify replay summaries and stale-context comparisons. |
| **Rollback Pointer** | A checkpoint or resume pointer that tells recovery where to return if the action must be undone. |
| **Replay Trace** | A sequence of ledger entries rendered as dictionaries for recovery and operator inspection. |

---

## 4. Implementation Details

The DS-2 Week 2 logic is primarily implemented in:

- `src/evidence/ledger/evidence_ledger.py`
- `tests/evidence/test_evidence_ledger.py`

### The Folding Flow

1. **Receive Payload:** `EvidenceLedger.fold_tool_artifact()` receives workflow metadata, the tool name, payload, context hash, and optional policy/rollback data.
2. **Parse Payload:** `parse_artifact_payload()` accepts JSON strings or ordinary Python data structures.
3. **Hash Payload:** `compute_context_hash()` produces a deterministic hash of the parsed payload.
4. **Extract Changes:** `extract_state_changes()` walks the payload recursively and recognizes common mutation shapes.
5. **Compact Values:** Large values are shortened with stable hashes so evidence remains readable.
6. **Build ArtifactFold:** The ledger records change list, omitted paths, payload size, payload hash, and state-change hash.
7. **Write LedgerEntry:** The folded artifact is written through `EvidenceLedger.write_entry()` with replay metadata.

### Supported Change Shapes

| Payload Shape | Example | Result |
|:---|:---|:---|
| `before` / `after` | `{"before": {"status": "paid"}, "after": {"status": "refunded"}}` | One `updated` change per changed field. |
| `old` / `new` | `{"field": "note", "old": "pending", "new": "approved"}` | One `updated` change. |
| `updated` list | `{"updated": [{"field": "note", "old": "...", "new": "..."}]}` | One or more `updated` changes. |
| `deleted` list | `{"deleted": [{"resource_id": "flag", "value": true}]}` | One or more `deleted` changes. |
| JSON Patch | `{"op": "replace", "path": "/invoice/status", "value": "refunded"}` | `updated`, `created`, or `deleted` based on `op`. |
| Read-only payload | `{"records": [...]}` | A no-op evidence entry with zero state changes. |

### Key Classes and Functions

| Code Object | Purpose |
|:---|:---|
| `EvidenceLedger` | In-memory append-only ledger used by tests and prototype flows. |
| `EvidenceLedger.write_entry()` | Writes a general immutable ledger row. |
| `EvidenceLedger.fold_tool_artifact()` | Main DS-2 Week 2 entry point for artifact folding. |
| `LedgerEntry` | One immutable evidence row with context hash, policy result, replay trace ref, rollback pointer, and optional artifact fold. |
| `ArtifactFold` | Folded artifact summary attached to a ledger entry. |
| `StateChange` | One extracted mutation with path, operation, before/after values, system, resource, and value hash. |
| `StateChangeOperation` | Enum for `created`, `updated`, and `deleted`. |
| `parse_artifact_payload()` | Converts JSON strings or Python payloads into parsed structures. |
| `extract_state_changes()` | Extracts state-changing variables from nested payloads. |

---

## 5. DS-2 Independence Boundary

DS-2 Week 2 should prove artifact folding without requiring production storage, orchestration, UI, or live tool execution.

### DS-2 Owns

- The artifact folding path in `EvidenceLedger.fold_tool_artifact()`.
- State-change extraction from large JSON payloads.
- Payload and state-change hashing.
- Replay-ready ledger entries for folded artifacts.
- Tests proving large payload, JSON Patch, read-only, and invalid JSON behavior.

### DS-2 Should Not Block On

- Durable object store persistence. The HTML describes replayable evidence storage at the architecture level, but DS-2 Week 2 only needs the ledger folding behavior.
- UI replay screens.
- Backend workflow orchestration.
- Real sandbox/tool execution. The payload parser can be tested with synthetic tool outputs.
- DS-1 RLM summaries, except through ordinary ledger entries when available.
- DS-3 stale-context detection, except by exposing folded changes in a shape DS-3 can read later.

### Integration Points

- **DS-1 Week 2:** RLM summaries can be written as ledger entries using `summarize_trace_to_ledger()`.
- **DS-3 Week 2:** Stale-context detection can read state changes from ledger entries and artifact folds.
- **Replay Engine:** Later replay synthesis can use `get_replay_trace()` to show folded artifacts to an operator.
- **Workflow Engine:** Workflow activities can call `fold_tool_artifact()` after write-capable tool calls.

---

## 6. Prerequisite Files & Current Repo Status

| File | Needed For | Required Now? | Current Status | Notes |
|:---|:---|:---|:---|:---|
| `src/evidence/ledger/evidence_ledger.py` | Main DS-2 Week 2 implementation. | Yes | Implemented | Contains `EvidenceLedger`, `LedgerEntry`, `ArtifactFold`, `StateChange`, parsing, folding, and replay helpers. |
| `src/orchestration/context_graph/context_hashing.py` | Deterministic hashing for payloads and state-change summaries. | Yes | Implemented | Provides `compute_context_hash()` and `canonicalize_snapshot()`. DS-2 depends on it for integrity hashes. |
| `src/common/models.py` | Shared governance models for context hashes and evidence-like schemas. | Optional | Implemented | Not required by `fold_tool_artifact()`, but used by adjacent DS tests and context flows. |
| `src/evidence/replay/rlm_summarizer.py` | RLM summaries that can be written into ledger evidence. | Optional | Implemented | Provides `summarize_trace_to_ledger()` for the HTML-backed RLM-to-ledger integration. |
| `src/evidence/replay/replay_engine.py` | Future consumer of replayable ledger entries. | No | Placeholder | Contains only module-level responsibility documentation today. Week 4/replay ownership can build on `get_replay_trace()`. |
| `src/execution/codeact_sandbox/sandbox_runner.py` | Future source of sandbox artifacts. | No | Present | Integration point for tool/sandbox outputs. DS-2 tests use synthetic payloads instead. |
| `tests/evidence/test_evidence_ledger.py` | DS-2 Week 2 regression tests. | Yes | Implemented | Covers large payloads, JSON Patch payloads, no-op read-only payloads, and invalid JSON rejection. |
| `tests/evidence/test_rlm_ledger_integration.py` | Cross-check for RLM summary evidence writes. | Optional | Implemented | Confirms summaries can enter the ledger with context hash, degradation state, replay ref, and rollback pointer. |
| `scratch_tests/test_week2_ds_integration.py` | Manual visible DS Week 2 smoke test. | Optional | Present but ignored by Git | Useful for local manual validation; not part of committed test suite unless force-added. |

### Status Meaning

- **Implemented:** The file has executable logic and tests currently pass.
- **Placeholder:** The file exists but does not yet contain the future feature logic.
- **Present:** The file exists, but may be a future integration surface rather than owned by DS-2 Week 2.
- **Missing:** The file does not currently exist in the repo.

---

## 7. Data Contract

### `LedgerEntry`

| Field | Purpose |
|:---|:---|
| `entry_id` | Deterministic evidence ID derived from ledger payload metadata unless explicitly provided. |
| `workflow_id` | Workflow being governed. |
| `branch_id` | Workflow branch where the action occurred. |
| `actor_id` | Agent or control component that produced the evidence. |
| `action` | Ledger action string, such as `tool_artifact_fold:billing.refund`. |
| `context_hash` | Hash of the context snapshot active when the evidence was written. |
| `outcome` | `state_changes_extracted` or `no_state_changes_detected` for folded artifacts. |
| `policy_result` | Optional policy decision related to the tool call. |
| `degradation_state` | Optional autonomy/degradation state at evidence time. |
| `replay_trace_ref` | Optional pointer to trace storage or replay source. |
| `rollback_pointer` | Optional checkpoint for safe recovery. |
| `artifact_fold` | Optional folded artifact details. |
| `metadata` | Additional summary or indexing fields. |

### `ArtifactFold`

| Field | Purpose |
|:---|:---|
| `artifact_id` | Stable folded artifact identifier. |
| `payload_hash` | Hash of the normalized original payload. |
| `state_change_hash` | Hash of the extracted state changes. |
| `changes` | List of `StateChange` objects. |
| `payload_size_bytes` | Size of the canonical payload representation. |
| `omitted_paths` | Paths skipped because extraction reached limits or values were not useful. |
| `metadata` | Folding strategy, source payload type, and caller metadata. |

---

## 8. Verification & Testing

### Tests That Validate DS-2 Week 2

1. **Large Payload Folding**
   - Input: Payload with hundreds of read-only records plus state changes.
   - Expected: Only changed fields are extracted, payload/state hashes are 64-char hashes, rollback pointer is preserved.

2. **JSON Patch Folding**
   - Input: JSON string with `replace`, `add`, and `remove` patch operations.
   - Expected: Operations map to `updated`, `created`, and `deleted`.

3. **Read-Only No-Op**
   - Input: Payload containing only read-only records.
   - Expected: Ledger entry is still written, but `change_count == 0`.

4. **Invalid JSON Rejection**
   - Input: Invalid JSON string.
   - Expected: `ArtifactPayloadError`.

5. **Week 2 Integration Smoke Test**
   - Input: Synthetic DS1 summary, DS2 artifact payload, DS3 stale context ledger facts.
   - Expected: All Week 2 DS pieces work in one run.

### Commands

```bash
python -m pytest tests/evidence/test_evidence_ledger.py
python -m pytest tests/evidence/test_rlm_ledger_integration.py
python -m pytest scratch_tests/test_week2_ds_integration.py -q -s
```

### Success Signals

- State-changing fields are preserved.
- Read-only noise is not treated as mutation evidence.
- Payload and state-change hashes are deterministic.
- Replay trace output includes folded artifact details.
- Rollback pointers and context hashes survive the ledger write.

---

## 9. Week 2 Completion Criteria

DS-2 Week 2 is complete when:

- `EvidenceLedger.fold_tool_artifact()` accepts large nested payloads.
- The system extracts created, updated, and deleted state changes.
- Folded entries preserve context hash, policy result, rollback pointer, and replay metadata.
- No-op read-only payloads still produce replayable evidence entries.
- Invalid payloads fail explicitly.
- Tests pass for large payloads, JSON Patch, no-op payloads, and invalid JSON.
- DS3 can read folded state changes from ledger entries for stale-context detection.

---

**Reference:** `Agent-Workforce-Control-Plane-Magazine.html` §04 Context Engineering (Recovery — Degradation & Replay), §08 Replayable Evidence Ledger
