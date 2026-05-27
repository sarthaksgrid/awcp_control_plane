# 02 - Stale-Context Detection

This document details the second DS-3 step in the Agent Workforce Control Plane (AWCP) lifecycle: **DS-3 (Week 2)**. This task builds on Week 1 cryptographic context hashing by adding **Stale-Context Detection**: comparing an agent's working memory against verified Evidence Ledger facts so outdated or hallucinated state can trigger degradation.

## 1. Objective: Detect Outdated Working Memory

In Week 1, DS-3 created the context hash: a stable SHA-256 fingerprint of the context an agent was using.

In Week 2, the problem becomes more dynamic. A hash mismatch can tell us the context changed, but it does not explain whether the agent is making a bad decision because its working memory is stale. For example, an agent might still believe a customer is refund-eligible even though the Evidence Ledger contains a later verified state change saying the customer is no longer eligible.

The goal of **DS-3 Week 2** is to compare the agent's current working memory against chronological ledger facts and return a structured stale-context signal.

### What does Stale-Context Detection do?

1. Compute the current context hash.
2. Read verified evidence entries in chronological order.
3. Compare current hash against the latest ledger context hash.
4. Extract state facts from the current context's working memory.
5. Extract latest verified state facts from ledger entries and folded artifacts.
6. Return a `StaleContextReport` with reasons and concrete conflicts.
7. Feed that report into the degradation trigger evaluator.

## 2. Why This Matters

Without stale-context detection, an agent can continue making decisions based on facts that were true earlier but are false now.

This is dangerous because many governance failures are not caused by bad intent. They are caused by outdated memory:

- A policy changed after the agent started.
- Another agent already completed or rolled back a task.
- A tool call changed customer or billing state.
- A handoff carried old assumptions into a remediation branch.

Stale-context detection gives the control plane a precise safety signal: "the agent's remembered state conflicts with verified ledger state."

### Technical Targets

- **Input:** Current context or Governing Slice plus Evidence Ledger entries.
- **Output:** `StaleContextReport` with `is_stale`, hashes, latest entry metadata, reasons, and conflicts.
- **Conflict Precision:** Include key, working-memory value, ledger value, ledger entry ID, and timestamp.
- **Ledger Discipline:** Ignore failed/denied evidence outcomes when computing verified state.
- **Degradation Integration:** Feed stale-context status into `TriggerEvaluator` as a first-class signal.

---

## 3. Jargon Explained

| Term | Definition in AWCP |
|:---|:---|
| **Stale Context** | A condition where an agent's current context or memory no longer matches verified workflow state. |
| **Working Memory** | The agent's current remembered facts, usually found in context metadata, recent history, or state fields. |
| **Verified Ledger State** | The latest accepted state facts recorded in non-failed Evidence Ledger entries. |
| **Context Hash Mismatch** | The current context hash differs from the latest ledger checkpoint hash. |
| **State Conflict** | A specific field where working memory and ledger state disagree, such as `customer.refund_eligible`. |
| **StaleContextReport** | Structured result that turns stale-context analysis into a degradation-ready signal. |
| **TriggerEvaluator** | Degradation evaluator that consumes stale context along with failure budget, policy, latency, and disagreement signals. |

---

## 4. Implementation Details

The DS-3 Week 2 logic is primarily implemented in:

- `src/orchestration/context_graph/context_hashing.py`
- `src/governance/degradation/trigger_evaluator.py`
- `tests/governance/test_degradation.py`
- `tests/orchestration/test_context_graph.py`

### The Detection Flow

1. **Evaluate Current Context:** `StaleContextDetector.evaluate(current_context, evidence_entries)` starts by hashing the current context.
2. **Select Verified Evidence:** Failed, denied, blocked, rejected, or error outcomes are excluded from the verified timeline.
3. **Sort Chronologically:** Evidence entries are sorted by timestamp and entry ID so latest state wins deterministically.
4. **Check Hash Freshness:** If the latest ledger context hash differs from the current hash, the report includes `context_hash_mismatch`.
5. **Extract Ledger Facts:** The detector reads state facts from ledger fields such as `state_changes`, `changed_variables`, `verified_state`, `facts`, and folded artifact changes.
6. **Extract Working Memory:** The detector reads memory facts from fields such as `working_memory`, `current_memory`, `remembered_state`, `facts`, and `state`.
7. **Find Conflicts:** Matching keys are compared after normalization. Differences become `StaleContextConflict` entries.
8. **Return Signal:** The report can be converted into a compact dictionary through `StaleContextReport.as_signal()`.
9. **Trigger Degradation:** `TriggerEvaluator.evaluate(current_context=..., evidence_entries=...)` embeds the stale report and forces at least `DegradationLevel.TIGHTEN` when stale context is present.

### Detection Reasons

| Reason | Meaning |
|:---|:---|
| `context_hash_mismatch` | The current context hash does not match the latest verified ledger hash. |
| `working_memory_conflicts_with_ledger` | At least one remembered state value conflicts with verified ledger state. |

### Key Classes and Functions

| Code Object | Purpose |
|:---|:---|
| `ContextHasher` | Generates deterministic hashes and canonical representations. |
| `StaleContextDetector` | Main DS-3 Week 2 detector. |
| `StaleContextReport` | Structured stale-context result. |
| `StaleContextConflict` | One concrete conflict between working memory and ledger state. |
| `evaluate_stale_context()` | Module-level helper for callers that only need stale-context status. |
| `TriggerEvaluator.evaluate_stale_context()` | Degradation-layer helper that delegates to `StaleContextDetector`. |
| `TriggerEvaluator.evaluate()` | Accepts either normal trigger signals or `current_context` plus `evidence_entries`. |
| `DegradationDecision.stale_context_report` | Carries stale-context evidence alongside the degradation decision. |

---

## 5. DS-3 Independence Boundary

DS-3 Week 2 should be able to run with current context objects and ledger-like evidence entries. It should not require a database, UI, orchestration runtime, or live model provider.

### DS-3 Owns

- `StaleContextDetector`.
- `StaleContextReport` and conflict payloads.
- Hash mismatch detection against ledger checkpoints.
- Working-memory vs ledger-state comparison.
- Degradation evaluator integration for stale context.
- Tests proving stale conflict detection and trigger behavior.

### DS-3 Should Not Block On

- Durable Evidence Ledger storage. DS-3 only needs iterable ledger entries or ledger-like dictionaries/objects.
- UI display of stale-context reports.
- Backend workflow orchestration.
- Real handoff/runtime adapters.
- DS-2's internal payload parser, as long as folded artifact changes are exposed in ledger entries.

### Integration Points

- **DS-2 Week 2:** Folded artifact changes can be read as verified ledger state.
- **DS-1 Week 3:** Failure budget modeling consumes the stale-context signal.
- **DS-2 Week 3:** Degradation engine applies the autonomy reduction recommended by the evaluator.
- **Replay/Recovery:** Stale reports provide concrete conflicts for operator review and next-safe-action reasoning.

---

## 6. Prerequisite Files & Current Repo Status

| File | Needed For | Required Now? | Current Status | Notes |
|:---|:---|:---|:---|:---|
| `src/orchestration/context_graph/context_hashing.py` | Main DS-3 Week 2 implementation. | Yes | Implemented | Contains `ContextHasher`, `StaleContextDetector`, `StaleContextReport`, and conflict extraction. |
| `src/governance/degradation/trigger_evaluator.py` | Degradation trigger integration. | Yes | Implemented | Accepts `current_context` and `evidence_entries`, embeds stale report, and maps stale context to degradation level. |
| `src/evidence/ledger/evidence_ledger.py` | Source of ledger entries and folded artifact changes. | Optional | Implemented | DS-3 can read ledger-like objects/dicts; direct database coupling is not required. |
| `src/common/models.py` | Current context and evidence schemas used by tests. | Optional | Implemented | Provides `GoverningSliceSchema`, `EvidenceEntry`, `WorkflowState`, `AgentIdentity`, and enums. |
| `src/orchestration/context_graph/context_manager.py` | Source of context snapshots and hash freshness checks. | Optional | Implemented | Context graph freshness remains separate from ledger-vs-memory stale detection. |
| `src/governance/degradation/degradation_engine.py` | Consumer of degradation decisions. | Optional | Implemented | Applies autonomy changes after trigger evaluation. Week 2 only requires the trigger signal integration. |
| `tests/orchestration/test_context_graph.py` | Hashing and stale-context detector tests. | Yes | Implemented | Covers context hashing and stale-context detector behavior. |
| `tests/governance/test_degradation.py` | Trigger evaluator stale-context integration tests. | Yes | Implemented | Verifies stale context produces a degradation decision. |
| `scratch_tests/test_week2_ds_integration.py` | Manual visible DS Week 2 smoke test. | Optional | Present but ignored by Git | Exercises DS1, DS2, DS3, and degradation signal flow together. |
| `src/evidence/replay/replay_engine.py` | Future consumer for replay summaries. | No | Placeholder | Not required for DS-3 Week 2 detection. |

### Status Meaning

- **Implemented:** The file has executable logic and tests currently pass.
- **Placeholder:** The file exists but only describes future responsibility.
- **Optional:** Useful integration point, but not required to prove DS-3 Week 2.
- **Missing:** The file does not currently exist in the repo.

---

## 7. Data Contract

### `StaleContextReport`

| Field | Purpose |
|:---|:---|
| `is_stale` | `True` when any stale-context reason is present. |
| `current_hash` | Hash of the current context under evaluation. |
| `ledger_hash` | Latest verified ledger context hash, if present. |
| `latest_entry_id` | Latest verified evidence entry used by the detector. |
| `latest_entry_timestamp` | Timestamp of that latest verified evidence entry. |
| `reasons` | List of stale reasons such as `context_hash_mismatch`. |
| `conflicts` | List of concrete `StaleContextConflict` objects. |

### `StaleContextConflict`

| Field | Purpose |
|:---|:---|
| `key` | Dot-path of the conflicting fact. |
| `working_memory_value` | Value currently remembered by the agent. |
| `ledger_value` | Latest verified value from the ledger. |
| `ledger_entry_id` | Evidence entry that supplied the ledger value. |
| `ledger_timestamp` | Timestamp of that evidence entry. |

### `DegradationDecision` Additions

| Field or Property | Purpose |
|:---|:---|
| `stale_context_report` | Carries the full DS-3 report with the trigger decision. |
| `evidence["stale_context_report"]` | Compact serialized signal for audit/UI/replay usage. |
| `triggers` | Includes `stale_context` when stale context is breached. |
| `recommended_level` | Forced to at least `TIGHTEN` when stale context is detected. |

---

## 8. Verification & Testing

### Tests That Validate DS-3 Week 2

1. **Memory Conflict Detection**
   - Input: Working memory says `customer.refund_eligible=True`; ledger says latest verified value is `False`.
   - Expected: `is_stale=True`, reason is `working_memory_conflicts_with_ledger`, conflict key is `customer.refund_eligible`.

2. **Chronological Ledger Ordering**
   - Input: Multiple ledger entries for the same fact.
   - Expected: Latest verified entry wins.

3. **Failed Evidence Ignored**
   - Input: Failed or denied ledger entry contains a changed fact.
   - Expected: The failed entry is not treated as verified state.

4. **Hash Mismatch Detection**
   - Input: Latest ledger context hash differs from current context hash.
   - Expected: Report includes `context_hash_mismatch`.

5. **Degradation Integration**
   - Input: `TriggerEvaluator().evaluate(current_context=..., evidence_entries=...)`.
   - Expected: Decision should degrade, triggers include `stale_context`, and recommended level is at least `TIGHTEN`.

6. **Week 2 Integration Smoke Test**
   - Input: DS1 summary, DS2 folded artifact, DS3 stale context conflict.
   - Expected: All Week 2 DS pieces run together.

### Commands

```bash
python -m pytest tests/orchestration/test_context_graph.py
python -m pytest tests/governance/test_degradation.py
python -m pytest scratch_tests/test_week2_ds_integration.py -q -s
```

### Success Signals

- Current context hash is deterministic.
- Stale reports identify exact field conflicts.
- Failed/denied evidence does not overwrite verified state.
- Trigger evaluator exposes stale-context evidence.
- Stale context causes conservative degradation pressure.

---

## 9. Week 2 Completion Criteria

DS-3 Week 2 is complete when:

- `StaleContextDetector.evaluate()` accepts current context plus ledger entries.
- The detector catches both hash mismatches and ledger-vs-memory conflicts.
- Reports include concrete conflict details and ledger provenance.
- Failed or denied evidence is excluded from verified state.
- `TriggerEvaluator` can compute stale context directly from context and evidence entries.
- Stale context appears in `DegradationDecision.triggers`.
- Stale context forces at least a tightening/conservative recommendation.
- Tests pass for context hashing, stale detector behavior, and degradation integration.

---

**Reference:** `Agent-Workforce-Control-Plane-Magazine.html` §04 Context Engineering (pre-conditions, stale-context checks, degradation and replay), §08 Context Graph Manager, §08 Degradation Policy Engine
