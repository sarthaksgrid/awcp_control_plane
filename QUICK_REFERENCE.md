# Event Tracking Quick Reference

## What Changed?

**TL;DR:** Temporal workflows now group events properly. One agent run with web search = 2 activities (not 5+).

## Visual Comparison

### Before ❌
```
Temporal UI Activities:
├─ record_execution_event: {"event": "agent_started"}
├─ record_execution_event: {"tool": "web_search", "status": "started"}
├─ record_execution_event: {"tool": "web_search", "status": "succeeded"}
└─ record_execution_event: {"event": "agent_completed"}
```
**Problem:** Fragmented, confusing, hard to read

### After ✅
```
Temporal UI Activities:
├─ agent_run: Complete agent execution (input → output)
└─ web_search: Complete tool call (query → result)
```
**Benefit:** Clean, consolidated, easy to understand

## For Developers

### If you maintain the FastAPI agent service:

**Required response structure:**
```python
return {
    "body": {
        "tool_calls": [
            {
                "event_type": "tool_call",
                "tool_name": "web_search",
                "status": "started",
                "input": {"query": "..."}
            },
            {
                "event_type": "tool_call",
                "tool_name": "web_search",
                "status": "succeeded",
                "output": {"type": "str", "preview": "..."}
            }
        ],
        "answer": "...",
        "search_used": true
    }
}
```

**Key points:**
- ✅ Include `body.tool_calls` array (can be empty)
- ✅ Each tool call emits 2 events: started + succeeded/failed
- ✅ Use consistent field names: `event_type`, `tool_name`, `status`

### If you maintain the Temporal workflows:

**What activities exist:**
1. `record_agent_run(full_response)` → One per agent execution
2. `record_tool_call(grouped_tool)` → One per tool invocation

**When activities run:**
```python
# Step 1: Agent executes
result = await execute_activity(execute_agent, ...)

# Step 2: Record agent run
await execute_activity(record_agent_run, result)

# Step 3: Record each tool (if any)
for tool in grouped_tools:
    await execute_activity(record_tool_call, tool)
```

### If you monitor workflows in Temporal UI:

**What you'll see:**

| Scenario | Activities in UI |
|----------|-----------------|
| Agent without tools | 1: `agent_run` |
| Agent with 1 tool | 2: `agent_run`, `web_search` |
| Agent with same tool twice | 3: `agent_run`, `web_search`, `web_search_2` |
| Agent with 2 different tools | 3: `agent_run`, `web_search`, `code_executor` |

**Activity details:**
- Click activity → See Input/Output in JSON
- Input = Tool parameters (query, code, etc.)
- Output = Tool result (preview, data, etc.)
- Status = succeeded/failed

## Common Issues

### ❌ Issue: No tool activities appear
**Cause:** Missing `body.tool_calls` in response
**Fix:** Add `tool_calls: []` to response body

### ❌ Issue: Tool activity has no output
**Cause:** Only "started" event, missing "succeeded"
**Fix:** Emit both events (started → succeeded/failed)

### ❌ Issue: Wrong activity names
**Cause:** Missing `tool_name` field
**Fix:** Include `tool_name` in each event

## Testing Checklist

Run these scenarios after deployment:

```bash
# Test 1: Agent without tools
curl -X POST .../run -d '{"input": "2+2"}'
# Expected: 1 activity (agent_run)

# Test 2: Agent with tools
curl -X POST .../run -d '{"input": "What is the weather?"}'
# Expected: 2 activities (agent_run + web_search)

# Test 3: Multiple tool calls
curl -X POST .../run -d '{"input": "Search Python and JavaScript"}'
# Expected: 3+ activities (agent_run + web_search + web_search_2 + ...)
```

## Code Snippets

### FastAPI: Emit tool events
```python
tool_calls = []

# Tool starts
tool_calls.append({
    "event_type": "tool_call",
    "tool_name": "web_search",
    "status": "started",
    "input": {"query": query}
})

# Tool completes
result = do_search(query)
tool_calls.append({
    "event_type": "tool_call",
    "tool_name": "web_search",
    "status": "succeeded",
    "output": {"type": "str", "preview": result[:100]}
})

return {"body": {"tool_calls": tool_calls, ...}}
```

### Workflow: Add new tool activity
```python
# No changes needed! Tool activities are auto-created
# based on tool_calls array in response
```

### Query: Get tool usage from Temporal
```python
# Get workflow result
result = await workflow_handle.result()

# Extract tool calls
body = result.get("body", {})
tools_used = [
    tc["tool_name"] 
    for tc in body.get("tool_calls", [])
    if tc.get("status") == "succeeded"
]
```

## Deployment

```bash
# 1. Pull latest code
git pull origin main

# 2. Restart Temporal worker
pkill -f "temporal.worker"
python -m app.temporal.worker &

# 3. Verify activities registered
# Check worker logs for: "Registered activities: record_agent_run, record_tool_call, ..."

# 4. Run test workflow
curl -X POST http://localhost:8000/api/v1/runollamaapiweb \
  -H "Content-Type: application/json" \
  -d '{"input": "test query"}'

# 5. Check Temporal UI
open http://localhost:8080
# Navigate to workflow → Activities tab
# Confirm: agent_run activity exists
```

## Support

**See detailed docs:**
- [WORKFLOW_EVENT_TRACKING.md](./WORKFLOW_EVENT_TRACKING.md) - Full implementation guide
- [CHANGES_SUMMARY.md](./CHANGES_SUMMARY.md) - Complete change log

**Common commands:**
```bash
# View worker logs
tail -f worker.log

# List running workflows
curl http://localhost:8000/api/v1/workflow-stats

# Restart worker
pkill -f temporal.worker && python -m app.temporal.worker
```

## FAQ

**Q: Do I need to change my agent code?**
A: Only if it doesn't return `body.tool_calls` in the response.

**Q: Will this break existing workflows?**
A: In-flight workflows may fail. Complete them before deploying.

**Q: How do I add a new tool?**
A: Just emit the events in FastAPI. Workflow auto-creates activities.

**Q: Can I customize activity names?**
A: Yes, modify `_group_tool_calls()` in workflows.py.

**Q: Where is the old `record_execution_event`?**
A: Still exists but unused. Can be removed in future cleanup.

---

Last updated: 2026-06-03
