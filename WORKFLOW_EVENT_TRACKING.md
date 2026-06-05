# Temporal Workflow Event Tracking - Implementation Guide

## Overview

This document explains how the Temporal workflow processes and records agent execution events and tool calls. The implementation ensures that the Temporal UI shows a clean, grouped view of activities rather than scattered individual events.

## Problem Statement

**Before:** The workflow created separate activities for every single event (started, succeeded, failed), resulting in:
- Agent run with web search → 5+ activities in Temporal UI
- Confusing timeline with fragmented information
- Hard to understand what actually happened

**After:** The workflow groups events intelligently, resulting in:
- Agent run with web search → 2 activities (1 agent_run + 1 web_search)
- Clean, consolidated view
- Each activity contains complete information (input + output + status)

## Architecture

### Expected FastAPI Response Structure

```json
{
  "execution_events": [
    {
      "event_type": "agent",
      "agent_name": "ollama-search",
      "status": "started",
      "input": { "input": "..." }
    },
    {
      "event_type": "agent",
      "agent_name": "ollama-search",
      "status": "succeeded"
    }
  ],
  "tool_calls": [
    {
      "event_type": "tool_call",
      "tool_name": "web_search",
      "status": "started",
      "input": { "query": "..." }
    },
    {
      "event_type": "tool_call",
      "tool_name": "web_search",
      "status": "succeeded",
      "output": { "type": "str", "preview": "..." }
    }
  ]
}
```

### Workflow Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Execute Agent Activity (call_ollama_run_web, etc.) │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Returns full FastAPI response
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Record ONE "agent_run" Activity                     │
│ - Contains full agent response                              │
│ - Input, output, status_code, endpoint                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Extract body.tool_calls
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Group Tool Call Events                              │
│ - Parse tool_calls array from response                      │
│ - Group by tool_name                                         │
│ - Merge started + succeeded/failed into single dict          │
│ - Handle multiple calls to same tool (web_search_1, etc.)   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ For each grouped tool
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Record ONE "tool_call" Activity per Tool            │
│ - tool_name, input, status, output/error                    │
│ - Only final status (not intermediate "started")            │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. New Activities (activities.py)

#### `record_agent_run`
Records the complete agent execution as a single activity.

**Input:** Full FastAPI response dict
**Output:** Consolidated agent run info
```python
{
    "activity_type": "agent_run",
    "agent_name": "ollama-search",
    "input": {"input": "..."},
    "output": {"answer": "...", "tool_calls": [...]},
    "status_code": 200,
    "endpoint": "https://..."
}
```

#### `record_tool_call`
Records a single tool invocation (merged started + final status).

**Input:** Grouped tool call dict
**Output:** Tool call summary
```python
{
    "activity_type": "tool_call",
    "tool_name": "web_search",
    "input": {"query": "..."},
    "status": "succeeded",
    "output": {"type": "str", "preview": "..."}
}
```

### 2. Workflow Logic (workflows.py)

#### `ExecutionEventMixin._group_tool_calls()`
Groups tool call events by tool_name and merges started/succeeded/failed events.

**Logic:**
1. Iterate through tool_calls array
2. Track call count per tool_name (for multiple invocations)
3. When status="started": Create new entry with unique_key
4. When status="succeeded/failed": Merge into existing entry
5. Return list of complete tool call dicts

**Handles Multiple Calls:**
```python
# First web_search call
unique_key = "web_search"

# Second web_search call  
unique_key = "web_search_2"

# Third web_search call
unique_key = "web_search_3"
```

#### `ExecutionEventMixin._execute_with_event_tracking()`
Main workflow orchestration.

**Process:**
1. Execute agent activity (returns full FastAPI response)
2. Call `record_agent_run(result)` → Creates 1 activity
3. Extract `body.tool_calls` from response
4. Group tool calls using `_group_tool_calls()`
5. For each grouped tool, call `record_tool_call()` → Creates 1 activity per tool

## Temporal UI Display

### Example: Agent Run WITHOUT Tool Calls

**Activities shown:**
```
1. agent_run
   Input: {"input": "What is 2+2?"}
   Output: {"answer": "4", "tool_calls": []}
   Status: ✓ Completed
```

### Example: Agent Run WITH Tool Calls

**Activities shown:**
```
1. agent_run
   Input: {"input": "What's the weather?"}
   Output: {"answer": "...", "tool_calls": [...]}
   Status: ✓ Completed

2. web_search
   Input: {"query": "current weather"}
   Output: {"type": "str", "preview": "..."}
   Status: ✓ Completed
```

### Example: Agent Run with MULTIPLE Tool Calls

**Activities shown:**
```
1. agent_run
   Status: ✓ Completed

2. web_search
   Input: {"query": "Python tutorials"}
   Status: ✓ Completed

3. web_search_2
   Input: {"query": "advanced Python"}
   Status: ✓ Completed

4. code_executor
   Input: {"code": "print('hello')"}
   Status: ✓ Completed
```

## Key Benefits

1. **Clean UI**: Each logical operation = 1 activity (not 3+)
2. **Complete Context**: Each activity shows full lifecycle (input → output)
3. **Easy Debugging**: Quickly see what tools were used and their results
4. **Accurate Counting**: Tool invocation count matches actual usage
5. **Scalable**: Works for 0, 1, or N tool calls per agent run

## Testing Checklist

- [ ] Agent run without tools → 1 activity (agent_run only)
- [ ] Agent run with 1 tool → 2 activities (agent_run + tool)
- [ ] Agent run with same tool twice → 3 activities (agent_run + tool_1 + tool_2)
- [ ] Agent run with 2 different tools → 3 activities (agent_run + tool_a + tool_b)
- [ ] Failed tool call shows error in activity output
- [ ] Activity names are descriptive (web_search, not tool_call_123)

## Migration Notes

### What Changed
- Removed: `record_execution_event` (old activity that created 1 activity per event)
- Added: `record_agent_run` (1 activity for full agent result)
- Added: `record_tool_call` (1 activity per tool invocation)
- Removed: Signal-based event handling (`execution_event` signal)
- Removed: Tool buffering logic
- Simplified: No more async signal waiting or event flushing

### Backward Compatibility
⚠️ **Breaking Change**: Old workflows using `record_execution_event` will fail.

**Mitigation:**
1. Complete all in-flight workflows before deploying
2. Or keep `record_execution_event` as deprecated stub
3. Update worker to register new activities

### Deployment Steps
1. Deploy new activities to worker
2. Wait for old workflows to complete
3. Deploy new workflow code
4. Restart worker
5. Test with new agent run

## Troubleshooting

### Issue: No tool activities appear
**Cause:** FastAPI response missing `tool_calls` field or wrong structure
**Fix:** Verify response includes `body.tool_calls = [...]`

### Issue: Tool activities have no output
**Cause:** Only "started" event present, missing "succeeded/failed"
**Fix:** Ensure FastAPI emits both started AND final status events

### Issue: Multiple activities for same tool call
**Cause:** Tool call counters not incrementing correctly
**Fix:** Check that "started" event comes before "succeeded/failed"

### Issue: Activities show "started" as final status
**Cause:** Succeeded/failed event not merging correctly
**Fix:** Verify event structure matches expected format (event_type, tool_name, status)

## Future Enhancements

1. **Nested Tool Calls**: Support tools calling other tools
2. **Parallel Tools**: Handle concurrent tool invocations
3. **Tool Metrics**: Add duration, retry count, cost tracking
4. **Rich Output**: Store full tool results (not just preview)
5. **Event Filtering**: Configurable activity creation rules
