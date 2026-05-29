"""
AWCP — Logging Context Infrastructure
=====================================
Async-safe telemetry context propagation for structured logging.

This module intentionally implements only the foundational context layer.
Future logging components can consume this state to enrich JSON logs,
OpenTelemetry spans, governance events, replay records, and evidence ledger
entries without coupling request handling, workflow execution, or agent code
to a concrete logging backend.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import sys
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import Context, ContextVar, Token, copy_context as _copy_context
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import wraps
from time import perf_counter_ns
from types import TracebackType
from typing import Any, Final, Literal, Mapping, ParamSpec, TypedDict, TypeAlias, TypeVar, cast


ContextValue: TypeAlias = str | None
ContextToken: TypeAlias = Token[ContextValue]
ContextTokenMap: TypeAlias = dict[str, ContextToken]
ExceptionPayload: TypeAlias = dict[str, Any]
LogStream: TypeAlias = Literal["stdout", "stderr"]
MetricHook: TypeAlias = Callable[[str, float, Mapping[str, Any]], None]
P = ParamSpec("P")
R = TypeVar("R")


class StructuredLogRecord(TypedDict):
    """
    Canonical AWCP log envelope.

    TypedDict is used instead of Pydantic because log formatting sits on the
    hot path for high-volume governance telemetry. The schema remains typed for
    static analysis while avoiding runtime validation overhead on every record.
    All top-level keys are emitted for every log line to keep replay, evidence
    ledger ingestion, Loki labels, ELK mappings, and OTel collector pipelines
    schema-stable across services and deployments.
    """

    timestamp: str
    level: str
    logger: str
    message: str
    service: str
    environment: str
    version: str
    request_id: ContextValue
    workflow_id: ContextValue
    execution_id: ContextValue
    correlation_id: ContextValue
    tenant_id: ContextValue
    replay_id: ContextValue
    trace_id: ContextValue
    span_id: ContextValue
    event_type: ContextValue
    policy_id: ContextValue
    agent_id: ContextValue
    exception: ExceptionPayload | None
    stacktrace: str | None
    metadata: dict[str, Any]


class GovernanceEventType(StrEnum):
    """Stable event names for governance and evidence-ledger ingestion."""

    GOVERNANCE = "governance.event"
    POLICY_VIOLATION = "governance.policy_violation"
    DEGRADATION = "governance.degradation"
    APPROVAL_GATE = "governance.approval_gate"
    REPLAY = "governance.replay"
    SANDBOX = "governance.sandbox"
    OPERATION_FAILURE = "telemetry.operation_failure"
    LATENCY = "telemetry.latency"


class ApprovalDecision(StrEnum):
    """Approval gate outcomes retained for audit export."""

    APPROVED = "approved"
    DENIED = "denied"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    PENDING = "pending"


class DegradationLevel(StrEnum):
    """Operational degradation levels used by control-plane safety systems."""

    NONE = "none"
    PARTIAL = "partial"
    LIMITED = "limited"
    SEVERE = "severe"
    QUARANTINED = "quarantined"


class ReplayState(StrEnum):
    """Replay lifecycle states for deterministic diagnostics."""

    STARTED = "started"
    CHECKPOINT_LOADED = "checkpoint_loaded"
    DIVERGED = "diverged"
    COMPLETED = "completed"
    FAILED = "failed"


class SandboxExecutionState(StrEnum):
    """Sandbox execution states emitted by isolated tool/code runtimes."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    QUARANTINED = "quarantined"


class PolicyViolationSeverity(StrEnum):
    """Policy violation severities for compliance and retention controls."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationTrigger(StrEnum):
    """Escalation trigger categories for approval and incident workflows."""

    POLICY_DENIAL = "policy_denial"
    RISK_THRESHOLD = "risk_threshold"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    DEGRADATION_THRESHOLD = "degradation_threshold"
    REPLAY_DIVERGENCE = "replay_divergence"
    SANDBOX_VIOLATION = "sandbox_violation"


class GovernanceEventPayload(TypedDict, total=False):
    """Evidence-ledger-friendly metadata payload shared by governance events."""

    event_type: str
    event_version: str
    policy_id: str
    agent_id: str
    tenant_id: str
    workflow_id: str
    execution_id: str
    replay_id: str
    correlation_id: str
    request_id: str
    escalation_trigger: str
    escalation_required: bool
    reason: str
    details: dict[str, Any]


class LatencyPayload(TypedDict, total=False):
    """Structured latency payload for logs and optional metric hooks."""

    operation: str
    duration_ms: float
    queue_duration_ms: float
    execution_duration_ms: float
    success: bool


class _Unset:
    """Sentinel used to distinguish omitted fields from explicit clears."""


_UNSET: Final = _Unset()


# ContextVars provide task-local isolation for asyncio workloads. This keeps
# concurrent FastAPI requests, Temporal activities, and background tasks from
# leaking telemetry metadata into each other while still allowing child tasks to
# inherit the active context at creation time.
_request_id_var: ContextVar[ContextValue] = ContextVar("awcp_request_id", default=None)
_workflow_id_var: ContextVar[ContextValue] = ContextVar("awcp_workflow_id", default=None)
_execution_id_var: ContextVar[ContextValue] = ContextVar("awcp_execution_id", default=None)
_correlation_id_var: ContextVar[ContextValue] = ContextVar(
    "awcp_correlation_id",
    default=None,
)
_tenant_id_var: ContextVar[ContextValue] = ContextVar("awcp_tenant_id", default=None)
_replay_id_var: ContextVar[ContextValue] = ContextVar("awcp_replay_id", default=None)
_trace_id_var: ContextVar[ContextValue] = ContextVar("awcp_trace_id", default=None)
_span_id_var: ContextVar[ContextValue] = ContextVar("awcp_span_id", default=None)

_CONTEXT_VARS: Final[Mapping[str, ContextVar[ContextValue]]] = {
    "request_id": _request_id_var,
    "workflow_id": _workflow_id_var,
    "execution_id": _execution_id_var,
    "correlation_id": _correlation_id_var,
    "tenant_id": _tenant_id_var,
    "replay_id": _replay_id_var,
    "trace_id": _trace_id_var,
    "span_id": _span_id_var,
}

_DEFAULT_SERVICE_NAME: Final = "awcp"
_DEFAULT_ENVIRONMENT: Final = "development"
_DEFAULT_VERSION: Final = "unknown"
_MAX_EXCEPTION_CHAIN_DEPTH: Final = 8
_MAX_STACKTRACE_CHARS: Final = 32_000
_GOVERNANCE_EVENT_VERSION: Final = "1.0"
_LOG_RECORD_RESERVED_ATTRIBUTES: Final = frozenset(
    logging.makeLogRecord({}).__dict__.keys()
    | {
        "args",
        "asctime",
        "exc_info",
        "exc_text",
        "message",
        "metadata",
        "stack_info",
    },
)
_AWCP_ENVELOPE_KEYS: Final = frozenset(StructuredLogRecord.__annotations__)


@dataclass(frozen=True, slots=True)
class LoggingContext:
    """
    Immutable snapshot of AWCP telemetry metadata.

    The context is deliberately string-only and side-effect free so replayed
    workflows can reconstruct log metadata deterministically from persisted
    identifiers. Optional values allow infrastructure layers to bind only the
    identifiers available at a given boundary, such as HTTP ingress, Temporal
    workflow execution, or an OpenTelemetry span bridge.
    """

    request_id: ContextValue = None
    workflow_id: ContextValue = None
    execution_id: ContextValue = None
    correlation_id: ContextValue = None
    tenant_id: ContextValue = None
    replay_id: ContextValue = None
    trace_id: ContextValue = None
    span_id: ContextValue = None

    def to_dict(self) -> dict[str, ContextValue]:
        """
        Return a stable dictionary representation of the current metadata.

        Keys are always present, even when values are unavailable. Keeping the
        schema stable makes downstream JSON formatters, evidence ledger writers,
        and replay tooling deterministic and easy to validate.
        """

        return {
            "request_id": self.request_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "replay_id": self.replay_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }

    @classmethod
    def from_current_context(cls) -> "LoggingContext":
        """
        Capture the active task-local logging context as an immutable snapshot.

        Snapshotting avoids accidental mutation during async handoffs and gives
        future logging formatters a consistent view of metadata for one record.
        """

        return cls(
            request_id=_request_id_var.get(),
            workflow_id=_workflow_id_var.get(),
            execution_id=_execution_id_var.get(),
            correlation_id=_correlation_id_var.get(),
            tenant_id=_tenant_id_var.get(),
            replay_id=_replay_id_var.get(),
            trace_id=_trace_id_var.get(),
            span_id=_span_id_var.get(),
        )

    def bind(self) -> ContextTokenMap:
        """
        Bind this snapshot into the active async context.

        The returned tokens can be used by middleware or workflow boundaries to
        reset the context to its previous state. Step 1 exposes the token map
        for isolation-aware callers while `clear_context()` remains available
        for deterministic hard resets at trusted ingress or replay boundaries.
        """

        return _bind_values(self.to_dict())

    @staticmethod
    def clear() -> ContextTokenMap:
        """
        Clear all AWCP logging metadata from the active async context.

        Clearing every known key prevents tenant, trace, or replay metadata from
        bleeding across pooled workers, reused tasks, or test execution.
        """

        return _bind_values({key: None for key in _CONTEXT_VARS})


def bind_context(
    *,
    request_id: str | None | _Unset = _UNSET,
    workflow_id: str | None | _Unset = _UNSET,
    execution_id: str | None | _Unset = _UNSET,
    correlation_id: str | None | _Unset = _UNSET,
    tenant_id: str | None | _Unset = _UNSET,
    replay_id: str | None | _Unset = _UNSET,
    trace_id: str | None | _Unset = _UNSET,
    span_id: str | None | _Unset = _UNSET,
) -> LoggingContext:
    """
    Bind supplied metadata fields into the current async logging context.

    Omitted fields preserve their current values, while fields explicitly set
    to `None` are cleared. This is important for middleware layering: ingress
    can establish request and tenant metadata, workflow code can add replay
    identifiers later, and OTel integration can attach trace/span identifiers
    without erasing unrelated governance context.
    """

    updates = {
        "request_id": request_id,
        "workflow_id": workflow_id,
        "execution_id": execution_id,
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "replay_id": replay_id,
        "trace_id": trace_id,
        "span_id": span_id,
    }

    values: dict[str, ContextValue] = {}
    for key, value in updates.items():
        if isinstance(value, _Unset):
            continue
        values[key] = cast(ContextValue, value)

    _bind_values(values)
    return LoggingContext.from_current_context()


def clear_context() -> LoggingContext:
    """
    Clear all logging metadata and return the resulting empty context snapshot.

    Use this at trusted execution boundaries such as request ingress, worker
    startup hooks, and replay setup before binding fresh metadata.
    """

    LoggingContext.clear()
    return LoggingContext.from_current_context()


def get_logging_context() -> LoggingContext:
    """
    Return the active AWCP logging context for the current async execution flow.

    The returned object is immutable, making it safe to pass into formatters,
    governance event builders, evidence ledger payloads, and future telemetry
    adapters without risking mutation by downstream code.
    """

    return LoggingContext.from_current_context()


def _bind_values(values: Mapping[str, ContextValue]) -> ContextTokenMap:
    """
    Apply raw context values and return reset tokens for isolation-aware callers.

    This private helper centralizes ContextVar writes so all public binding paths
    have identical async propagation behavior.
    """

    tokens: ContextTokenMap = {}
    for key, value in values.items():
        context_var = _CONTEXT_VARS[key]
        tokens[key] = context_var.set(value)
    return tokens


def serialize_exception(exc: BaseException) -> ExceptionPayload:
    """
    Serialize an exception into deterministic, replay-safe metadata.

    Chained exceptions are preserved so governance violations, policy evaluator
    failures, and degradation causes keep their causal history without requiring
    downstream systems to parse human-readable stack traces.
    """

    try:
        return _serialize_exception(exc, depth=0)
    except Exception as serializer_error:  # pragma: no cover - defensive guardrail.
        return {
            "type": serializer_error.__class__.__name__,
            "module": serializer_error.__class__.__module__,
            "message": "failed to serialize exception",
            "stacktrace": None,
            "cause": None,
            "context": None,
            "notes": [],
        }


def extract_trace_context() -> dict[str, ContextValue]:
    """
    Extract the active OpenTelemetry trace/span identifiers when available.

    OpenTelemetry remains optional at this layer so local development, replay
    workers, and constrained bootstrap paths do not fail because tracing is not
    installed. When OTel is present, IDs are formatted as canonical lowercase
    hexadecimal strings compatible with W3C trace context and collector ingest.
    """

    try:
        from opentelemetry import trace
    except Exception:
        return {"trace_id": None, "span_id": None}

    try:
        span = trace.get_current_span()
        span_context = span.get_span_context()
    except Exception:
        return {"trace_id": None, "span_id": None}

    if not getattr(span_context, "is_valid", False):
        return {"trace_id": None, "span_id": None}

    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }


class JSONLogFormatter(logging.Formatter):
    """
    Format Python LogRecord instances as schema-stable AWCP JSON envelopes.

    The formatter keeps top-level fields stable and pushes arbitrary data into
    `metadata`. That protects ingestion mappings in ELK/Loki-style systems while
    still allowing governance payloads to carry nested evidence details.
    """

    def __init__(
        self,
        *,
        service: str = _DEFAULT_SERVICE_NAME,
        environment: str = _DEFAULT_ENVIRONMENT,
        version: str = _DEFAULT_VERSION,
    ) -> None:
        super().__init__()
        self.service = service
        self.environment = environment
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        """
        Return a valid JSON string for a log record.

        The method avoids deep copies and sanitizes only values that enter the
        envelope, reducing formatter overhead for high-volume telemetry streams.
        """

        context = get_logging_context()
        otel_context = extract_trace_context()
        exception_payload, stacktrace = self._format_exception(record)

        trace_id = context.trace_id or otel_context["trace_id"]
        span_id = context.span_id or otel_context["span_id"]

        envelope: StructuredLogRecord = {
            "timestamp": self._format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
            "environment": self.environment,
            "version": self.version,
            "request_id": context.request_id,
            "workflow_id": context.workflow_id,
            "execution_id": context.execution_id,
            "correlation_id": context.correlation_id,
            "tenant_id": context.tenant_id,
            "replay_id": context.replay_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "event_type": _coerce_optional_string(getattr(record, "event_type", None)),
            "policy_id": _coerce_optional_string(getattr(record, "policy_id", None)),
            "agent_id": _coerce_optional_string(getattr(record, "agent_id", None)),
            "exception": exception_payload,
            "stacktrace": stacktrace,
            "metadata": self._extract_metadata(record),
        }

        return json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )

    @staticmethod
    def _format_timestamp(created: float) -> str:
        """Format a LogRecord timestamp as UTC ISO-8601 with millisecond precision."""

        return (
            datetime.fromtimestamp(created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _format_exception(
        record: logging.LogRecord,
    ) -> tuple[ExceptionPayload | None, str | None]:
        """Serialize exception data attached to a LogRecord, if present."""

        if record.exc_info is None:
            return None, None

        exc_type, exc, exc_traceback = record.exc_info
        if exc is None:
            return None, None

        stacktrace = "".join(
            traceback.format_exception(
                exc_type,
                exc,
                cast(TracebackType | None, exc_traceback),
            ),
        )
        return serialize_exception(exc), _truncate_text(stacktrace)

    @staticmethod
    def _extract_metadata(record: logging.LogRecord) -> dict[str, Any]:
        """
        Collect structured metadata without destabilizing the top-level schema.

        Callers may pass `extra={"metadata": {...}}` for nested governance or
        replay payloads. Other custom LogRecord attributes are retained under
        metadata so downstream pipelines do not need dynamic top-level mappings.
        """

        metadata: dict[str, Any] = {}
        explicit_metadata = getattr(record, "metadata", None)
        if isinstance(explicit_metadata, Mapping):
            metadata.update(
                {
                    str(key): _to_json_compatible(value)
                    for key, value in explicit_metadata.items()
                },
            )
        elif explicit_metadata is not None:
            metadata["metadata"] = _to_json_compatible(explicit_metadata)

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_RESERVED_ATTRIBUTES or key in _AWCP_ENVELOPE_KEYS:
                continue
            metadata[key] = _to_json_compatible(value)

        # Replay identifiers stay top-level, while replay-specific payloads can
        # live here without changing the envelope contract across record types.
        return metadata


def configure_logging(
    *,
    log_level: str | int = "INFO",
    json_logs: bool = True,
    stream: LogStream = "stdout",
    service: str | None = None,
    environment: str | None = None,
    version: str | None = None,
    force: bool = False,
) -> None:
    """
    Configure process-wide AWCP logging for container-native deployments.

    The root logger receives a single AWCP-owned stream handler. Named loggers
    remain hierarchical and propagate to root, which avoids duplicate handlers
    while remaining compatible with Kubernetes stdout/stderr collection,
    sidecars, OpenTelemetry collectors, Loki, and ELK pipelines.
    """

    root_logger = logging.getLogger()
    resolved_level = _resolve_log_level(log_level)
    output_stream = sys.stdout if stream == "stdout" else sys.stderr

    if force:
        root_logger.handlers.clear()
    else:
        root_logger.handlers = [
            handler
            for handler in root_logger.handlers
            if not getattr(handler, "_awcp_handler", False)
        ]

    handler = logging.StreamHandler(output_stream)
    handler.setLevel(resolved_level)
    setattr(handler, "_awcp_handler", True)

    resolved_service = service or _env_or_default(
        "AWCP_SERVICE_NAME",
        _DEFAULT_SERVICE_NAME,
    )
    resolved_environment = environment or _env_or_default(
        "AWCP_ENVIRONMENT",
        _env_or_default("ENVIRONMENT", _DEFAULT_ENVIRONMENT),
    )
    resolved_version = version or _env_or_default("AWCP_VERSION", _DEFAULT_VERSION)

    if json_logs:
        handler.setFormatter(
            JSONLogFormatter(
                service=resolved_service,
                environment=resolved_environment,
                version=resolved_version,
            ),
        )
    else:
        # Human-readable mode is intentionally plain and still context-aware
        # through message/extra formatting by callers; production should prefer
        # JSON for evidence and replay ingestion.
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            ),
        )

    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a hierarchical logger configured for AWCP structured output.

    If logging has not yet been bootstrapped, a conservative default
    configuration is installed so early startup logs are not lost.
    """

    root_logger = logging.getLogger()
    if not any(getattr(handler, "_awcp_handler", False) for handler in root_logger.handlers):
        configure_logging()

    logger = logging.getLogger(name)
    logger.propagate = True
    return logger


def log_governance_event(
    *,
    event_type: GovernanceEventType | str,
    message: str,
    logger: logging.Logger | str | None = None,
    level: str | int = logging.INFO,
    policy_id: str | None = None,
    agent_id: str | None = None,
    escalation_trigger: EscalationTrigger | str | None = None,
    escalation_required: bool = False,
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """
    Emit a canonical governance event.

    Governance metadata is nested under `metadata.governance` so evidence
    streams and audit exports receive a deterministic payload without creating
    dynamic top-level fields in log aggregation systems.
    """

    context = get_logging_context()
    payload = _build_governance_payload(
        event_type=event_type,
        policy_id=policy_id,
        agent_id=agent_id,
        escalation_trigger=escalation_trigger,
        escalation_required=escalation_required,
        reason=reason,
        details=metadata,
        context=context,
    )
    _enrich_active_span(
        {
            "awcp.event_type": str(event_type),
            "awcp.policy_id": policy_id,
            "awcp.agent_id": agent_id,
            "awcp.tenant_id": context.tenant_id,
            "awcp.workflow_id": context.workflow_id,
            "awcp.execution_id": context.execution_id,
            "awcp.replay_id": context.replay_id,
            "awcp.escalation_required": escalation_required,
        },
    )
    _resolve_logger(logger).log(
        _resolve_log_level(level),
        message,
        extra={
            "event_type": str(event_type),
            "policy_id": policy_id,
            "agent_id": agent_id,
            "metadata": {"governance": payload},
        },
    )


def log_policy_violation(
    *,
    policy_id: str,
    message: str,
    severity: PolicyViolationSeverity | str = PolicyViolationSeverity.HIGH,
    agent_id: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    reason: str | None = None,
    escalation_trigger: EscalationTrigger | str = EscalationTrigger.POLICY_DENIAL,
    metadata: Mapping[str, Any] | None = None,
    logger: logging.Logger | str | None = None,
) -> None:
    """Log a policy violation with attribution suitable for compliance review."""

    details = _merge_metadata(
        metadata,
        {
            "severity": str(severity),
            "action": action,
            "resource": resource,
        },
    )
    log_governance_event(
        event_type=GovernanceEventType.POLICY_VIOLATION,
        message=message,
        logger=logger,
        level=logging.WARNING,
        policy_id=policy_id,
        agent_id=agent_id,
        escalation_trigger=escalation_trigger,
        escalation_required=True,
        reason=reason,
        metadata=details,
    )


def log_degradation_event(
    *,
    level: DegradationLevel | str,
    message: str,
    cause: str,
    agent_id: str | None = None,
    policy_id: str | None = None,
    escalation_trigger: EscalationTrigger | str | None = None,
    metadata: Mapping[str, Any] | None = None,
    logger: logging.Logger | str | None = None,
) -> None:
    """Log a degradation state transition for operational replay diagnostics."""

    degradation_level = str(level)
    _enrich_active_span({"awcp.degradation_level": degradation_level})
    log_governance_event(
        event_type=GovernanceEventType.DEGRADATION,
        message=message,
        logger=logger,
        level=logging.WARNING,
        policy_id=policy_id,
        agent_id=agent_id,
        escalation_trigger=escalation_trigger,
        escalation_required=degradation_level
        in {str(DegradationLevel.SEVERE), str(DegradationLevel.QUARANTINED)},
        reason=cause,
        metadata=_merge_metadata(metadata, {"degradation_level": degradation_level}),
    )


def log_approval_gate(
    *,
    decision: ApprovalDecision | str,
    message: str,
    approval_id: str,
    policy_id: str | None = None,
    agent_id: str | None = None,
    approver: str | None = None,
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    logger: logging.Logger | str | None = None,
) -> None:
    """Log approval gate decisions for audit export and retention workflows."""

    decision_value = str(decision)
    log_governance_event(
        event_type=GovernanceEventType.APPROVAL_GATE,
        message=message,
        logger=logger,
        level=logging.INFO if decision_value == str(ApprovalDecision.APPROVED) else logging.WARNING,
        policy_id=policy_id,
        agent_id=agent_id,
        escalation_trigger=(
            EscalationTrigger.HUMAN_APPROVAL_REQUIRED
            if decision_value
            in {str(ApprovalDecision.ESCALATED), str(ApprovalDecision.PENDING)}
            else None
        ),
        escalation_required=decision_value
        in {str(ApprovalDecision.ESCALATED), str(ApprovalDecision.PENDING)},
        reason=reason,
        metadata=_merge_metadata(
            metadata,
            {
                "approval_id": approval_id,
                "decision": decision_value,
                "approver": approver,
            },
        ),
    )


def log_replay_event(
    *,
    state: ReplayState | str,
    message: str,
    checkpoint_id: str | None = None,
    divergence_hash: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    logger: logging.Logger | str | None = None,
) -> None:
    """Log replay lifecycle events while preserving deterministic replay metadata."""

    state_value = str(state)
    log_governance_event(
        event_type=GovernanceEventType.REPLAY,
        message=message,
        logger=logger,
        level=logging.ERROR
        if state_value in {str(ReplayState.DIVERGED), str(ReplayState.FAILED)}
        else logging.INFO,
        escalation_trigger=(
            EscalationTrigger.REPLAY_DIVERGENCE
            if state_value == str(ReplayState.DIVERGED)
            else None
        ),
        escalation_required=state_value == str(ReplayState.DIVERGED),
        reason="replay divergence detected"
        if state_value == str(ReplayState.DIVERGED)
        else None,
        metadata=_merge_metadata(
            metadata,
            {
                "replay_state": state_value,
                "checkpoint_id": checkpoint_id,
                "divergence_hash": divergence_hash,
            },
        ),
    )


def log_sandbox_event(
    *,
    state: SandboxExecutionState | str,
    message: str,
    sandbox_id: str,
    agent_id: str | None = None,
    policy_id: str | None = None,
    exit_code: int | None = None,
    duration_ms: float | None = None,
    metadata: Mapping[str, Any] | None = None,
    logger: logging.Logger | str | None = None,
) -> None:
    """Log sandbox execution state for isolated runtime evidence trails."""

    state_value = str(state)
    failure_state = state_value in {
        str(SandboxExecutionState.FAILED),
        str(SandboxExecutionState.TIMED_OUT),
        str(SandboxExecutionState.QUARANTINED),
    }
    log_governance_event(
        event_type=GovernanceEventType.SANDBOX,
        message=message,
        logger=logger,
        level=logging.ERROR if failure_state else logging.INFO,
        policy_id=policy_id,
        agent_id=agent_id,
        escalation_trigger=EscalationTrigger.SANDBOX_VIOLATION if failure_state else None,
        escalation_required=failure_state,
        reason="sandbox execution did not complete successfully" if failure_state else None,
        metadata=_merge_metadata(
            metadata,
            {
                "sandbox_id": sandbox_id,
                "sandbox_state": state_value,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        ),
    )


def trace_operation(
    operation_name: str | None = None,
    *,
    logger: logging.Logger | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorate sync or async operations with OTel span enrichment and failure logs.

    ContextVar metadata remains untouched, which preserves request, workflow,
    tenant, and replay correlation across Temporal and FastAPI execution paths.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = operation_name or f"{func.__module__}.{func.__qualname__}"

        if _is_async_callable(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                with _start_otel_span(name, metadata):
                    try:
                        result = func(*args, **kwargs)
                        return await cast(Awaitable[Any], result)
                    except Exception as exc:
                        _log_operation_failure(name, exc, logger, metadata)
                        raise

            return cast(Callable[P, R], async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            with _start_otel_span(name, metadata):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    _log_operation_failure(name, exc, logger, metadata)
                    raise

        return cast(Callable[P, R], sync_wrapper)

    return decorator


def measure_latency(
    operation_name: str | None = None,
    *,
    logger: logging.Logger | str | None = None,
    metric_hook: MetricHook | None = None,
    metadata: Mapping[str, Any] | None = None,
    log_success: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Measure sync or async operation latency using a high-precision monotonic clock.

    Optional metric hooks receive milliseconds and sanitized metadata without
    coupling this logging module to a concrete metrics backend.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = operation_name or f"{func.__module__}.{func.__qualname__}"

        if _is_async_callable(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                start_ns = perf_counter_ns()
                try:
                    result = func(*args, **kwargs)
                    value = await cast(Awaitable[Any], result)
                except Exception:
                    _emit_latency(name, start_ns, False, logger, metric_hook, metadata)
                    raise
                _emit_latency(name, start_ns, True, logger, metric_hook, metadata, log_success)
                return value

            return cast(Callable[P, R], async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            start_ns = perf_counter_ns()
            try:
                value = func(*args, **kwargs)
            except Exception:
                _emit_latency(name, start_ns, False, logger, metric_hook, metadata)
                raise
            _emit_latency(name, start_ns, True, logger, metric_hook, metadata, log_success)
            return value

        return cast(Callable[P, R], sync_wrapper)

    return decorator


def copy_current_context() -> Context:
    """
    Copy the current execution context for safe async or executor handoff.

    The returned Context captures AWCP correlation state at a deterministic
    boundary and can be passed to `run_with_context()` for isolated execution.
    """

    return _copy_context()


def run_with_context(
    context: LoggingContext | Context,
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """
    Run a callable with an explicit AWCP logging context.

    `contextvars.Context` is supported for low-level executor handoff, while
    `LoggingContext` provides a stable replay-friendly snapshot API.
    """

    if _is_async_callable(func):
        execution_context = (
            context if isinstance(context, Context) else _context_from_snapshot(context)
        )

        async def _async_runner() -> Any:
            coroutine = cast(
                Coroutine[Any, Any, Any],
                execution_context.run(func, *args, **kwargs),
            )
            task: asyncio.Task[Any] = asyncio.create_task(
                coroutine,
                context=execution_context,
            )
            return await task

        return cast(R, _async_runner())

    if isinstance(context, Context):
        return context.run(func, *args, **kwargs)

    execution_context = _context_from_snapshot(context)
    return execution_context.run(func, *args, **kwargs)


def _context_from_snapshot(context: LoggingContext) -> Context:
    """Create an isolated Context populated from a LoggingContext snapshot."""

    execution_context = _copy_context()
    execution_context.run(context.bind)
    return execution_context


def _build_governance_payload(
    *,
    event_type: GovernanceEventType | str,
    policy_id: str | None,
    agent_id: str | None,
    escalation_trigger: EscalationTrigger | str | None,
    escalation_required: bool,
    reason: str | None,
    details: Mapping[str, Any] | None,
    context: LoggingContext,
) -> GovernanceEventPayload:
    """Build a deterministic governance payload from context and event details."""

    payload: GovernanceEventPayload = {
        "event_type": str(event_type),
        "event_version": _GOVERNANCE_EVENT_VERSION,
        "escalation_required": escalation_required,
    }

    if policy_id is not None:
        payload["policy_id"] = policy_id
    if agent_id is not None:
        payload["agent_id"] = agent_id
    if context.tenant_id is not None:
        payload["tenant_id"] = context.tenant_id
    if context.workflow_id is not None:
        payload["workflow_id"] = context.workflow_id
    if context.execution_id is not None:
        payload["execution_id"] = context.execution_id
    if context.replay_id is not None:
        payload["replay_id"] = context.replay_id
    if context.correlation_id is not None:
        payload["correlation_id"] = context.correlation_id
    if context.request_id is not None:
        payload["request_id"] = context.request_id
    if escalation_trigger is not None:
        payload["escalation_trigger"] = str(escalation_trigger)
    if reason is not None:
        payload["reason"] = reason

    if details:
        payload["details"] = cast(dict[str, Any], _to_json_compatible(details))

    return payload


def _merge_metadata(
    metadata: Mapping[str, Any] | None,
    additions: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge event metadata while dropping absent values for compact payloads."""

    merged: dict[str, Any] = {}
    if metadata:
        merged.update({str(key): value for key, value in metadata.items()})
    for key, value in additions.items():
        if value is not None:
            merged[key] = value
    return merged


def _resolve_logger(logger: logging.Logger | str | None) -> logging.Logger:
    """Resolve optional logger input into a configured hierarchical logger."""

    if isinstance(logger, logging.Logger):
        return logger
    return get_logger(logger or "awcp.governance")


def _is_async_callable(func: Callable[..., Any]) -> bool:
    """Return whether a callable is an async function."""

    return inspect.iscoroutinefunction(func)


@contextmanager
def _start_otel_span(
    operation_name: str,
    metadata: Mapping[str, Any] | None,
) -> Iterator[None]:
    """Start an optional OTel span and attach AWCP correlation attributes."""

    try:
        from opentelemetry import trace
    except Exception:
        with nullcontext():
            yield
        return

    try:
        span_context_manager = trace.get_tracer(__name__).start_as_current_span(
            operation_name,
        )
    except Exception:
        with nullcontext():
            yield
        return

    with span_context_manager:
        _enrich_active_span(
            {
                "awcp.operation": operation_name,
                **_context_span_attributes(get_logging_context()),
                **{
                    f"awcp.metadata.{key}": value
                    for key, value in (metadata or {}).items()
                    if _is_span_attribute_value(value)
                },
            },
        )
        yield


def _enrich_active_span(attributes: Mapping[str, Any]) -> None:
    """Attach sanitized AWCP attributes to the active OTel span when available."""

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not getattr(span.get_span_context(), "is_valid", False):
            return
        for key, value in attributes.items():
            if value is not None and _is_span_attribute_value(value):
                span.set_attribute(key, value)
    except Exception:
        return


def _context_span_attributes(context: LoggingContext) -> dict[str, str]:
    """Convert current logging context to OTel-safe span attributes."""

    return {
        f"awcp.{key}": value
        for key, value in context.to_dict().items()
        if value is not None
    }


def _is_span_attribute_value(value: Any) -> bool:
    """Return whether a value is safe for OpenTelemetry span attributes."""

    return isinstance(value, str | bool | int | float)


def _log_operation_failure(
    operation_name: str,
    exc: BaseException,
    logger: logging.Logger | str | None,
    metadata: Mapping[str, Any] | None,
) -> None:
    """Emit structured failure telemetry for traced operations."""

    _enrich_active_span(
        {
            "awcp.operation": operation_name,
            "awcp.exception_type": exc.__class__.__name__,
            "awcp.exception_category": _classify_exception(exc),
        },
    )
    _resolve_logger(logger or "awcp.telemetry").exception(
        "operation failed",
        extra={
            "event_type": GovernanceEventType.OPERATION_FAILURE,
            "metadata": _merge_metadata(
                metadata,
                {
                    "operation": operation_name,
                    "exception_category": _classify_exception(exc),
                },
            ),
        },
    )


def _emit_latency(
    operation_name: str,
    start_ns: int,
    success: bool,
    logger: logging.Logger | str | None,
    metric_hook: MetricHook | None,
    metadata: Mapping[str, Any] | None,
    log_success: bool = True,
) -> None:
    """Emit latency logs and optional metrics from a monotonic timestamp."""

    duration_ms = (perf_counter_ns() - start_ns) / 1_000_000
    payload: LatencyPayload = {
        "operation": operation_name,
        "duration_ms": round(duration_ms, 6),
        "execution_duration_ms": round(duration_ms, 6),
        "success": success,
    }
    enriched_metadata = _merge_metadata(metadata, cast(Mapping[str, Any], payload))
    _enrich_active_span(
        {
            "awcp.operation": operation_name,
            "awcp.duration_ms": payload["duration_ms"],
            "awcp.success": success,
        },
    )

    if metric_hook is not None:
        metric_hook(operation_name, duration_ms, enriched_metadata)

    if success and not log_success:
        return

    _resolve_logger(logger or "awcp.telemetry").log(
        logging.INFO if success else logging.ERROR,
        "operation latency measured",
        extra={
            "event_type": GovernanceEventType.LATENCY,
            "metadata": {"latency": enriched_metadata},
        },
    )


def _serialize_exception(exc: BaseException, *, depth: int) -> ExceptionPayload:
    """Recursively serialize exception chains with bounded depth."""

    if depth >= _MAX_EXCEPTION_CHAIN_DEPTH:
        return {
            "type": "ExceptionChainTruncated",
            "module": __name__,
            "message": "exception chain exceeded maximum serialization depth",
            "stacktrace": None,
            "cause": None,
            "context": None,
            "notes": [],
        }

    return {
        "type": exc.__class__.__name__,
        "module": exc.__class__.__module__,
        "category": _classify_exception(exc),
        "message": str(exc),
        "stacktrace": _truncate_text(
            "".join(
                traceback.format_exception(
                    exc.__class__,
                    exc,
                    exc.__traceback__,
                ),
            ),
        ),
        "cause": (
            _serialize_exception(exc.__cause__, depth=depth + 1)
            if exc.__cause__ is not None
            else None
        ),
        "context": (
            _serialize_exception(exc.__context__, depth=depth + 1)
            if exc.__context__ is not None and not exc.__suppress_context__
            else None
        ),
        "notes": _to_json_compatible(getattr(exc, "__notes__", [])),
    }


def _classify_exception(exc: BaseException) -> str:
    """
    Classify exceptions by governance relevance without importing domain modules.

    Name-based classification keeps this module independent today while allowing
    future `src.common.exceptions` classes to integrate by convention.
    """

    text = f"{exc.__class__.__name__} {exc}".lower()
    if "policy" in text or "denied" in text:
        return "policy"
    if "approval" in text or "token" in text:
        return "approval"
    if "degradation" in text or "threshold" in text:
        return "degradation"
    if "replay" in text:
        return "replay"
    if "sandbox" in text or "quarantine" in text:
        return "sandbox"
    for chained in (exc.__cause__, exc.__context__):
        if chained is not None:
            chained_category = _classify_exception(chained)
            if chained_category != "application":
                return chained_category
    return "application"


def _truncate_text(value: str) -> str:
    """Apply deterministic stacktrace truncation for bounded log records."""

    if len(value) <= _MAX_STACKTRACE_CHARS:
        return value
    suffix = "\n... truncated by AWCP logging ..."
    return f"{value[: _MAX_STACKTRACE_CHARS - len(suffix)]}{suffix}"


def _to_json_compatible(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> Any:
    """
    Convert arbitrary metadata into JSON-compatible values with recursion guards.

    The conversion is intentionally shallow-bounded so a malformed governance
    payload cannot create recursive serialization traps on the logging hot path.
    """

    if value is None or isinstance(value, str | int | float | bool):
        return value

    if depth >= 12:
        return repr(value)

    if seen is None:
        seen = set()

    value_id = id(value)
    if value_id in seen:
        return "<recursive>"

    if isinstance(value, Mapping):
        seen.add(value_id)
        return {
            str(key): _to_json_compatible(item, depth=depth + 1, seen=seen)
            for key, item in value.items()
        }

    if isinstance(value, tuple | list | set | frozenset):
        seen.add(value_id)
        items = list(value)
        if isinstance(value, set | frozenset):
            items = sorted(items, key=repr)
        return [
            _to_json_compatible(item, depth=depth + 1, seen=seen)
            for item in items
        ]

    return repr(value)


def _json_default(value: Any) -> str:
    """Last-resort JSON encoder fallback for unexpected formatter values."""

    return repr(value)


def _coerce_optional_string(value: Any) -> ContextValue:
    """Normalize optional envelope identifiers to strings or None."""

    if value is None:
        return None
    return str(value)


def _resolve_log_level(log_level: str | int) -> int:
    """Resolve a standard logging level name or integer into its numeric value."""

    if isinstance(log_level, int):
        return log_level

    resolved = logging.getLevelName(log_level.upper())
    if isinstance(resolved, int):
        return resolved

    raise ValueError(f"unknown log level: {log_level}")


def _env_or_default(name: str, default: str) -> str:
    """Return an environment variable value while preserving explicit empty strings."""

    value = os.getenv(name)
    if value is None:
        return default
    return value
