from __future__ import annotations

import asyncio
import json
import logging
from io import StringIO
from typing import Any

import pytest

from src.common.logging import (
    ApprovalDecision,
    DegradationLevel,
    GovernanceEventType,
    JSONLogFormatter,
    LoggingContext,
    PolicyViolationSeverity,
    ReplayState,
    SandboxExecutionState,
    bind_context,
    clear_context,
    configure_logging,
    copy_current_context,
    extract_trace_context,
    get_logger,
    get_logging_context,
    log_approval_gate,
    log_degradation_event,
    log_governance_event,
    log_policy_violation,
    log_replay_event,
    log_sandbox_event,
    measure_latency,
    run_with_context,
    serialize_exception,
    trace_operation,
)


def _json_logger(name: str = "awcp.test") -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        JSONLogFormatter(service="awcp-test", environment="test", version="1.2.3"),
    )
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger, stream


def _records(stream: StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


@pytest.fixture(autouse=True)
def _clear_logging_context() -> None:
    clear_context()
    yield
    clear_context()


def test_json_formatter_emits_stable_schema_with_context() -> None:
    logger, stream = _json_logger()
    bind_context(
        request_id="req-1",
        workflow_id="wf-1",
        execution_id="exec-1",
        correlation_id="corr-1",
        tenant_id="tenant-1",
        replay_id="replay-1",
    )

    logger.info(
        "policy evaluated",
        extra={
            "event_type": "policy.evaluated",
            "policy_id": "policy-1",
            "agent_id": "agent-1",
            "metadata": {"decision": "allow"},
        },
    )

    record = _records(stream)[0]
    assert list(record) == [
        "timestamp",
        "level",
        "logger",
        "message",
        "service",
        "environment",
        "version",
        "request_id",
        "workflow_id",
        "execution_id",
        "correlation_id",
        "tenant_id",
        "replay_id",
        "trace_id",
        "span_id",
        "event_type",
        "policy_id",
        "agent_id",
        "exception",
        "stacktrace",
        "metadata",
    ]
    assert record["service"] == "awcp-test"
    assert record["environment"] == "test"
    assert record["version"] == "1.2.3"
    assert record["request_id"] == "req-1"
    assert record["workflow_id"] == "wf-1"
    assert record["execution_id"] == "exec-1"
    assert record["correlation_id"] == "corr-1"
    assert record["tenant_id"] == "tenant-1"
    assert record["replay_id"] == "replay-1"
    assert record["event_type"] == "policy.evaluated"
    assert record["policy_id"] == "policy-1"
    assert record["agent_id"] == "agent-1"
    assert record["metadata"] == {"decision": "allow"}


def test_logging_context_bind_clear_and_snapshot() -> None:
    context = bind_context(request_id="req-2", tenant_id="tenant-2")

    assert context == LoggingContext.from_current_context()
    assert get_logging_context().to_dict()["request_id"] == "req-2"

    snapshot = LoggingContext(request_id="req-3", tenant_id="tenant-3")
    snapshot.bind()
    assert get_logging_context().request_id == "req-3"

    clear_context()
    assert get_logging_context() == LoggingContext()


@pytest.mark.asyncio
async def test_concurrent_async_context_isolation() -> None:
    async def worker(request_id: str) -> tuple[str | None, str | None]:
        bind_context(request_id=request_id, tenant_id=f"tenant-{request_id}")
        await asyncio.sleep(0)
        context = get_logging_context()
        return context.request_id, context.tenant_id

    results = await asyncio.gather(worker("a"), worker("b"), worker("c"))

    assert set(results) == {("a", "tenant-a"), ("b", "tenant-b"), ("c", "tenant-c")}
    assert get_logging_context() == LoggingContext()


def test_copy_and_run_with_context_for_sync_handoff() -> None:
    bind_context(request_id="parent", tenant_id="tenant-parent")
    copied = copy_current_context()
    bind_context(request_id="changed", tenant_id="tenant-changed")

    def read_context() -> tuple[str | None, str | None]:
        context = get_logging_context()
        return context.request_id, context.tenant_id

    assert run_with_context(copied, read_context) == ("parent", "tenant-parent")
    assert run_with_context(
        LoggingContext(request_id="snapshot", tenant_id="tenant-snapshot"),
        read_context,
    ) == ("snapshot", "tenant-snapshot")
    assert get_logging_context().request_id == "changed"


@pytest.mark.asyncio
async def test_run_with_context_preserves_async_snapshot() -> None:
    async def read_context() -> tuple[str | None, str | None]:
        await asyncio.sleep(0)
        context = get_logging_context()
        return context.request_id, context.tenant_id

    bind_context(request_id="outer", tenant_id="tenant-outer")
    result = await run_with_context(
        LoggingContext(request_id="async", tenant_id="tenant-async"),
        read_context,
    )

    assert result == ("async", "tenant-async")
    assert get_logging_context().request_id == "outer"


def test_governance_event_serialization_preserves_replay_metadata() -> None:
    logger, stream = _json_logger()
    bind_context(
        request_id="req-gov",
        workflow_id="wf-gov",
        execution_id="exec-gov",
        correlation_id="corr-gov",
        tenant_id="tenant-gov",
        replay_id="replay-gov",
    )

    log_governance_event(
        event_type=GovernanceEventType.GOVERNANCE,
        message="governance checkpoint",
        logger=logger,
        policy_id="policy-gov",
        agent_id="agent-gov",
        metadata={"evidence_id": "ev-1"},
    )

    record = _records(stream)[0]
    payload = record["metadata"]["governance"]
    assert record["event_type"] == "governance.event"
    assert record["policy_id"] == "policy-gov"
    assert record["agent_id"] == "agent-gov"
    assert payload["tenant_id"] == "tenant-gov"
    assert payload["workflow_id"] == "wf-gov"
    assert payload["execution_id"] == "exec-gov"
    assert payload["replay_id"] == "replay-gov"
    assert payload["details"] == {"evidence_id": "ev-1"}


def test_specific_governance_helpers_emit_expected_payloads() -> None:
    logger, stream = _json_logger()
    bind_context(tenant_id="tenant-helpers", workflow_id="wf-helpers")

    log_policy_violation(
        policy_id="policy-deny",
        message="policy denied action",
        severity=PolicyViolationSeverity.CRITICAL,
        agent_id="agent-1",
        action="tool.execute",
        resource="prod-db",
        reason="unsafe access",
        logger=logger,
    )
    log_degradation_event(
        level=DegradationLevel.SEVERE,
        message="degraded to limited mode",
        cause="error budget exhausted",
        logger=logger,
    )
    log_approval_gate(
        decision=ApprovalDecision.ESCALATED,
        message="approval required",
        approval_id="approval-1",
        logger=logger,
    )
    log_replay_event(
        state=ReplayState.DIVERGED,
        message="replay diverged",
        divergence_hash="hash-1",
        logger=logger,
    )
    log_sandbox_event(
        state=SandboxExecutionState.FAILED,
        message="sandbox failed",
        sandbox_id="sandbox-1",
        exit_code=137,
        logger=logger,
    )

    records = _records(stream)
    event_types = [record["event_type"] for record in records]
    assert event_types == [
        "governance.policy_violation",
        "governance.degradation",
        "governance.approval_gate",
        "governance.replay",
        "governance.sandbox",
    ]
    assert records[0]["metadata"]["governance"]["details"]["severity"] == "critical"
    assert records[1]["metadata"]["governance"]["details"]["degradation_level"] == "severe"
    assert records[2]["metadata"]["governance"]["details"]["decision"] == "escalated"
    assert records[3]["metadata"]["governance"]["escalation_required"] is True
    assert records[4]["metadata"]["governance"]["details"]["sandbox_state"] == "failed"


def test_serialize_exception_preserves_chains_and_classification() -> None:
    try:
        try:
            raise ValueError("bad policy input")
        except ValueError as exc:
            raise RuntimeError("policy evaluation failed") from exc
    except RuntimeError as exc:
        payload = serialize_exception(exc)

    assert payload["type"] == "RuntimeError"
    assert payload["category"] == "policy"
    assert payload["message"] == "policy evaluation failed"
    assert payload["cause"]["type"] == "ValueError"
    assert "RuntimeError" in payload["stacktrace"]


def test_json_formatter_serializes_exception_payload() -> None:
    logger, stream = _json_logger()

    try:
        raise RuntimeError("sandbox failed")
    except RuntimeError:
        logger.exception("sandbox exception")

    record = _records(stream)[0]
    assert record["exception"]["type"] == "RuntimeError"
    assert record["exception"]["category"] == "sandbox"
    assert "RuntimeError" in record["stacktrace"]


def test_extract_trace_context_gracefully_degrades() -> None:
    trace_context = extract_trace_context()

    assert set(trace_context) == {"trace_id", "span_id"}
    assert trace_context["trace_id"] is None or isinstance(trace_context["trace_id"], str)
    assert trace_context["span_id"] is None or isinstance(trace_context["span_id"], str)


@pytest.mark.asyncio
async def test_trace_operation_logs_async_failures() -> None:
    logger, stream = _json_logger()
    bind_context(request_id="trace-req", replay_id="trace-replay")

    @trace_operation("agent.step", logger=logger, metadata={"agent_id": "agent-trace"})
    async def failing_operation() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError):
        await failing_operation()

    record = _records(stream)[0]
    assert record["event_type"] == "telemetry.operation_failure"
    assert record["request_id"] == "trace-req"
    assert record["replay_id"] == "trace-replay"
    assert record["metadata"]["operation"] == "agent.step"
    assert record["exception"]["type"] == "RuntimeError"


def test_trace_operation_preserves_sync_return_value() -> None:
    logger, stream = _json_logger()

    @trace_operation("sync.step", logger=logger)
    def operation() -> str:
        return "ok"

    assert operation() == "ok"
    assert _records(stream) == []


@pytest.mark.asyncio
async def test_measure_latency_logs_and_invokes_metric_hook() -> None:
    logger, stream = _json_logger()
    metrics: list[tuple[str, float, dict[str, Any]]] = []

    def metric_hook(name: str, duration_ms: float, metadata: dict[str, Any]) -> None:
        metrics.append((name, duration_ms, metadata))

    @measure_latency(
        "queue.execute",
        logger=logger,
        metric_hook=metric_hook,
        metadata={"queue": "critical"},
    )
    async def operation() -> str:
        await asyncio.sleep(0)
        return "done"

    assert await operation() == "done"
    record = _records(stream)[0]
    assert record["event_type"] == "telemetry.latency"
    assert record["metadata"]["latency"]["operation"] == "queue.execute"
    assert record["metadata"]["latency"]["success"] is True
    assert record["metadata"]["latency"]["duration_ms"] >= 0
    assert metrics[0][0] == "queue.execute"
    assert metrics[0][1] >= 0
    assert metrics[0][2]["queue"] == "critical"


def test_measure_latency_logs_failures() -> None:
    logger, stream = _json_logger()

    @measure_latency("sync.failure", logger=logger)
    def operation() -> None:
        raise RuntimeError("failed")

    with pytest.raises(RuntimeError):
        operation()

    record = _records(stream)[0]
    assert record["event_type"] == "telemetry.latency"
    assert record["level"] == "ERROR"
    assert record["metadata"]["latency"]["success"] is False


def test_configure_logging_and_get_logger_emit_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(
        log_level="INFO",
        json_logs=True,
        stream="stdout",
        service="awcp-config-test",
        environment="unit",
        version="test",
        force=True,
    )
    logger = get_logger("awcp.config.test")
    logger.info("configured logger")

    output = capsys.readouterr().out.strip()
    record = json.loads(output)
    assert record["service"] == "awcp-config-test"
    assert record["environment"] == "unit"
    assert record["version"] == "test"
    assert record["logger"] == "awcp.config.test"
    assert record["message"] == "configured logger"


def test_configure_logging_avoids_duplicate_awcp_handlers() -> None:
    configure_logging(force=True)
    configure_logging()

    awcp_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_awcp_handler", False)
    ]
    assert len(awcp_handlers) == 1
