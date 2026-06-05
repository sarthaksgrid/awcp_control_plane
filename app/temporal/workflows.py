from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        call_deepseek_run,
        call_ollama_run,
        call_ollama_run_web,
        execute_agent,
        record_tool_call,
        run_image_deepseek_activity,
    )


class ExecutionEventMixin:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def _enrich_request(self, request: dict[str, Any]) -> dict[str, Any]:
        info = workflow.info()
        return {
            **request,
            "workflow_id": info.workflow_id,
            "run_id": info.run_id,
        }

    def _group_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Group tool call events by tool_name.
        Handles both formats:
        1. Full format with event_type, started/succeeded events
        2. Simple format with just tool_name and status
        
        Returns list of tool call dicts, one per tool invocation.
        """
        # Check if this is the simple format (no event_type field)
        if tool_calls and isinstance(tool_calls, list):
            first_event = tool_calls[0] if tool_calls else {}
            if "event_type" not in first_event and "tool_name" in first_event:
                # Simple format - just return as-is
                result = []
                tool_counters: dict[str, int] = {}
                
                for event in tool_calls:
                    tool_name = event.get("tool_name")
                    if not tool_name:
                        continue
                    
                    # Count occurrences for unique naming
                    tool_counters[tool_name] = tool_counters.get(tool_name, 0) + 1
                    count = tool_counters[tool_name]
                    
                    result.append({
                        "tool_name": tool_name,
                        "unique_key": f"{tool_name}_{count}" if count > 1 else tool_name,
                        "status": event.get("status", "unknown"),
                        "input": event.get("input"),
                        "output": event.get("output"),
                        "error": event.get("error"),
                    })
                
                return result
        
        # Full format with event_type - use original grouping logic
        grouped_tools: dict[str, dict[str, Any]] = {}
        tool_call_counters: dict[str, int] = {}
        
        for event in tool_calls:
            if event.get("event_type") != "tool_call":
                continue
            
            tool_name = event.get("tool_name")
            if not tool_name:
                continue
            
            status = event.get("status")
            
            if status == "started":
                tool_call_counters[tool_name] = tool_call_counters.get(tool_name, 0) + 1
                call_index = tool_call_counters[tool_name]
                
                if call_index > 1:
                    unique_key = f"{tool_name}_{call_index}"
                else:
                    unique_key = tool_name
                
                grouped_tools[unique_key] = {
                    "tool_name": tool_name,
                    "unique_key": unique_key,
                    "input": event.get("input"),
                    "status": "started",
                }
            
            elif status in ("succeeded", "failed"):
                if tool_name in tool_call_counters:
                    call_index = tool_call_counters[tool_name]
                    if call_index > 1:
                        unique_key = f"{tool_name}_{call_index}"
                    else:
                        unique_key = tool_name
                    
                    if unique_key in grouped_tools:
                        grouped_tools[unique_key]["status"] = status
                        if status == "succeeded":
                            grouped_tools[unique_key]["output"] = event.get("output")
                        else:
                            grouped_tools[unique_key]["error"] = event.get("error")
        
        return list(grouped_tools.values())

    async def _execute_with_event_tracking(
        self,
        request: dict[str, Any],
        activity_fn: Any,
        *,
        start_to_close_timeout: timedelta,
        retry_policy: RetryPolicy | None = None,
    ) -> dict[str, Any]:
        """
        Execute agent activity (shown as ONE activity in Temporal UI).
        Then record tool calls as separate activities (if any).
        """
        enriched = self._enrich_request(request)
        activity_kwargs: dict[str, Any] = {
            "start_to_close_timeout": start_to_close_timeout,
        }
        if retry_policy is not None:
            activity_kwargs["retry_policy"] = retry_policy

        # Execute the agent activity - this shows as ONE activity in Temporal UI
        result = await workflow.execute_activity(activity_fn, enriched, **activity_kwargs)

        # Extract tool calls - check multiple possible locations
        tool_calls = []
        
        # Check if tool_calls is at root level (from activity)
        if "tool_calls" in result:
            tool_calls = result.get("tool_calls", [])

        # Check if it's in the body
        elif "body" in result:
            body = result.get("body", {})
            if isinstance(body, dict):
                tool_calls = body.get("tool_calls", [])
            
        # Check for tool_events (alternative field name)
        if not tool_calls and "tool_events" in result:
            tool_calls = result.get("tool_events", [])
        
        workflow.logger.info(f"Found {len(tool_calls) if tool_calls else 0} tool call events")
        
        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            grouped_tools = self._group_tool_calls(tool_calls)
            
            workflow.logger.info(f"Grouped into {len(grouped_tools)} tool activities")
            
            # Record ONE activity per tool call
            for tool_data in grouped_tools:
                workflow.logger.info(f"Recording tool activity: {tool_data.get('tool_name')}")
                await workflow.execute_activity(
                    record_tool_call,
                    tool_data,
                    start_to_close_timeout=timedelta(seconds=10),
                )
        
        return result


@workflow.defn
class OllamaRunWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            call_ollama_run,
            request,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class deepSeekRunWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            call_deepseek_run,
            request,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class AgentRunWorkflow(ExecutionEventMixin):
    def __init__(self) -> None:
        super().__init__()

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_with_event_tracking(
            request,
            execute_agent,
            start_to_close_timeout=timedelta(minutes=5),
        )


@workflow.defn
class ImageRunWorkflow:
    @workflow.run
    async def run(self, request: dict) -> dict[str, Any]:
        return await workflow.execute_activity(
            run_image_deepseek_activity,
            request,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class OllamaRunWorkflowWeb(ExecutionEventMixin):
    def __init__(self) -> None:
        super().__init__()

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_with_event_tracking(
            request,
            call_ollama_run_web,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
