# Event Tracking Architecture Diagram

## High-Level Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                         FastAPI Client                              │
│                    (Local or External Service)                      │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 │ HTTP POST
                                 │ {"input": "What's the weather?"}
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Control Plane FastAPI                            │
│                 /api/v1/runollamaapiweb                             │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 │ Start Workflow
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                      Temporal Server                                │
│                    (localhost:7233)                                 │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 │ Schedule Workflow
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                   OllamaRunWorkflowWeb                              │
│                   (ExecutionEventMixin)                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Step 1: Execute Agent Activity                               │ │
│  │  └─> call_ollama_run_web(request)                           │ │
│  │       └─> HTTP POST to agent service                        │ │
│  │            └─> Returns full response with tool_calls        │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Step 2: Record Agent Run                                     │ │
│  │  └─> record_agent_run(full_response)                        │ │
│  │       └─> ONE activity in Temporal UI                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Step 3: Extract & Group Tool Calls                           │ │
│  │  └─> tool_calls = response.body.tool_calls                  │ │
│  │  └─> grouped = _group_tool_calls(tool_calls)                │ │
│  │       └─> Merge started + succeeded/failed                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Step 4: Record Tool Calls                                    │ │
│  │  └─> For each grouped_tool:                                 │ │
│  │       └─> record_tool_call(grouped_tool)                    │ │
│  │            └─> ONE activity per tool in Temporal UI         │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Workflow Complete
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                        Temporal UI                                  │
│                    (localhost:8080)                                 │
│                                                                     │
│  Activities:                                                        │
│  ├─ agent_run                                                      │
│  │   Input: {"input": "What's the weather?"}                      │
│  │   Output: {"answer": "...", "tool_calls": [...]}              │
│  │                                                                 │
│  └─ web_search                                                     │
│      Input: {"query": "current weather"}                           │
│      Output: {"type": "str", "preview": "..."}                     │
└────────────────────────────────────────────────────────────────────┘
```

## Agent Service Response Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                    Agent Service (FastAPI)                          │
│               e.g., ollama-search service                           │
│                                                                     │
│  Receives: {"input": "What's the weather?"}                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Processing Agent Request                                     │ │
│  │                                                               │ │
│  │  1. Parse input                                              │ │
│  │  2. Determine if tools needed                                │ │
│  │  3. If yes, execute tools:                                   │ │
│  │     ┌─────────────────────────────────────────────────────┐ │ │
│  │     │ Tool Execution: web_search                          │ │ │
│  │     │                                                      │ │ │
│  │     │ Emit: {                                             │ │ │
│  │     │   "event_type": "tool_call",                       │ │ │
│  │     │   "tool_name": "web_search",                       │ │ │
│  │     │   "status": "started",                             │ │ │
│  │     │   "input": {"query": "current weather"}            │ │ │
│  │     │ }                                                   │ │ │
│  │     │                                                      │ │ │
│  │     │ [Execute web search...]                             │ │ │
│  │     │                                                      │ │ │
│  │     │ Emit: {                                             │ │ │
│  │     │   "event_type": "tool_call",                       │ │ │
│  │     │   "tool_name": "web_search",                       │ │ │
│  │     │   "status": "succeeded",                           │ │ │
│  │     │   "output": {                                       │ │ │
│  │     │     "type": "str",                                  │ │ │
│  │     │     "preview": "Sunny, 72°F..."                    │ │ │
│  │     │   }                                                 │ │ │
│  │     │ }                                                   │ │ │
│  │     └─────────────────────────────────────────────────────┘ │ │
│  │                                                               │ │
│  │  4. Generate final answer using tool results                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Returns: {                                                         │
│    "body": {                                                        │
│      "answer": "The weather is sunny and 72°F",                    │
│      "tool_calls": [                                                │
│        {                                                            │
│          "event_type": "tool_call",                                 │
│          "tool_name": "web_search",                                 │
│          "status": "started",                                       │
│          "input": {"query": "current weather"}                      │
│        },                                                           │
│        {                                                            │
│          "event_type": "tool_call",                                 │
│          "tool_name": "web_search",                                 │
│          "status": "succeeded",                                     │
│          "output": {"type": "str", "preview": "Sunny, 72°F..."}   │
│        }                                                            │
│      ],                                                             │
│      "search_used": true                                            │
│    }                                                                │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘
```

## Tool Grouping Logic

```
┌────────────────────────────────────────────────────────────────────┐
│            _group_tool_calls(tool_calls) Method                     │
│                                                                     │
│  Input: tool_calls = [                                              │
│    {"event_type": "tool_call", "tool_name": "web_search",          │
│     "status": "started", "input": {"query": "Python"}},            │
│    {"event_type": "tool_call", "tool_name": "web_search",          │
│     "status": "succeeded", "output": {...}},                        │
│    {"event_type": "tool_call", "tool_name": "web_search",          │
│     "status": "started", "input": {"query": "JavaScript"}},        │
│    {"event_type": "tool_call", "tool_name": "web_search",          │
│     "status": "succeeded", "output": {...}}                         │
│  ]                                                                  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Processing Loop                                              │ │
│  │                                                               │ │
│  │ For each event in tool_calls:                                │ │
│  │                                                               │ │
│  │   IF status == "started":                                    │ │
│  │     ┌─────────────────────────────────────────────────────┐ │ │
│  │     │ 1. Increment call counter for this tool_name       │ │ │
│  │     │    web_search counter: 0 → 1                       │ │ │
│  │     │                                                      │ │ │
│  │     │ 2. Generate unique key                              │ │ │
│  │     │    IF counter == 1: key = "web_search"             │ │ │
│  │     │    ELSE: key = "web_search_2"                      │ │ │
│  │     │                                                      │ │ │
│  │     │ 3. Create new entry in grouped_tools dict          │ │ │
│  │     │    grouped_tools["web_search"] = {                 │ │ │
│  │     │      "tool_name": "web_search",                    │ │ │
│  │     │      "unique_key": "web_search",                   │ │ │
│  │     │      "input": {"query": "Python"},                 │ │ │
│  │     │      "status": "started"                           │ │ │
│  │     │    }                                                │ │ │
│  │     └─────────────────────────────────────────────────────┘ │ │
│  │                                                               │ │
│  │   ELSE IF status == "succeeded" or "failed":                 │ │
│  │     ┌─────────────────────────────────────────────────────┐ │ │
│  │     │ 1. Find corresponding started event                 │ │ │
│  │     │    current counter = 1                              │ │ │
│  │     │    key = "web_search"                               │ │ │
│  │     │                                                      │ │ │
│  │     │ 2. Merge final status into existing entry          │ │ │
│  │     │    grouped_tools["web_search"]["status"] =         │ │ │
│  │     │      "succeeded"                                    │ │ │
│  │     │    grouped_tools["web_search"]["output"] =         │ │ │
│  │     │      {...}                                          │ │ │
│  │     └─────────────────────────────────────────────────────┘ │ │
│  │                                                               │ │
│  │ [Process continues for second web_search call...]            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Output: [                                                          │
│    {                                                                │
│      "tool_name": "web_search",                                     │
│      "unique_key": "web_search",                                    │
│      "input": {"query": "Python"},                                  │
│      "status": "succeeded",                                         │
│      "output": {...}                                                │
│    },                                                               │
│    {                                                                │
│      "tool_name": "web_search",                                     │
│      "unique_key": "web_search_2",                                  │
│      "input": {"query": "JavaScript"},                              │
│      "status": "succeeded",                                         │
│      "output": {...}                                                │
│    }                                                                │
│  ]                                                                  │
│                                                                     │
│  Result: 2 separate activities in Temporal UI:                     │
│    - "web_search"                                                   │
│    - "web_search_2"                                                 │
└────────────────────────────────────────────────────────────────────┘
```

## Activity Recording Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                     Activity Recording                              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Activity 1: record_agent_run                                 │ │
│  │                                                               │ │
│  │ Input:                                                        │ │
│  │   {                                                           │ │
│  │     "called_url": "https://...",                             │ │
│  │     "status_code": 200,                                      │ │
│  │     "payload": {"input": "..."},                             │ │
│  │     "body": {                                                │ │
│  │       "answer": "...",                                       │ │
│  │       "tool_calls": [...]                                    │ │
│  │     }                                                         │ │
│  │   }                                                           │ │
│  │                                                               │ │
│  │ Logged:                                                       │ │
│  │   AGENT_RUN | status=200 | agent=ollama-search              │ │
│  │                                                               │ │
│  │ Stored in Temporal:                                           │ │
│  │   activity_type: "agent_run"                                 │ │
│  │   agent_name: "ollama-search"                                │ │
│  │   input: {...}                                               │ │
│  │   output: {...}                                              │ │
│  │   status_code: 200                                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Activity 2: record_tool_call (web_search)                    │ │
│  │                                                               │ │
│  │ Input:                                                        │ │
│  │   {                                                           │ │
│  │     "tool_name": "web_search",                               │ │
│  │     "unique_key": "web_search",                              │ │
│  │     "input": {"query": "Python tutorials"},                  │ │
│  │     "status": "succeeded",                                   │ │
│  │     "output": {"type": "str", "preview": "..."}             │ │
│  │   }                                                           │ │
│  │                                                               │ │
│  │ Logged:                                                       │ │
│  │   TOOL_CALL | tool=web_search | status=succeeded            │ │
│  │                                                               │ │
│  │ Stored in Temporal:                                           │ │
│  │   activity_type: "tool_call"                                 │ │
│  │   tool_name: "web_search"                                    │ │
│  │   input: {"query": "..."}                                    │ │
│  │   status: "succeeded"                                        │ │
│  │   output: {...}                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Activity 3: record_tool_call (web_search_2)                  │ │
│  │                                                               │ │
│  │ [Same structure as Activity 2, different input/output]       │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

## Temporal UI Visualization

```
┌────────────────────────────────────────────────────────────────────┐
│ Workflow: ollama-run-abc123                                         │
│ Status: Completed ✓                                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Timeline:                                                           │
│                                                                     │
│ 12:00:00  WorkflowStarted                                          │
│    │                                                                │
│    │                                                                │
│ 12:00:01  ActivityScheduled: agent_run                             │
│    ├──── ActivityStarted: agent_run                                │
│    │     ┌─────────────────────────────────────────────────────┐  │
│    │     │ Input:                                              │  │
│    │     │   endpoint_url: "https://..."                       │  │
│    │     │   payload: {"input": "What's the weather?"}        │  │
│    │     │                                                      │  │
│    │     │ Output:                                             │  │
│    │     │   activity_type: "agent_run"                        │  │
│    │     │   agent_name: "ollama-search"                       │  │
│    │     │   status_code: 200                                  │  │
│    │     └─────────────────────────────────────────────────────┘  │
│    └──── ActivityCompleted: agent_run                              │
│                                                                     │
│ 12:00:05  ActivityScheduled: web_search                            │
│    ├──── ActivityStarted: web_search                               │
│    │     ┌─────────────────────────────────────────────────────┐  │
│    │     │ Input:                                              │  │
│    │     │   tool_name: "web_search"                           │  │
│    │     │   input: {"query": "current weather"}              │  │
│    │     │                                                      │  │
│    │     │ Output:                                             │  │
│    │     │   activity_type: "tool_call"                        │  │
│    │     │   status: "succeeded"                               │  │
│    │     │   output: {"type": "str", "preview": "..."}        │  │
│    │     └─────────────────────────────────────────────────────┘  │
│    └──── ActivityCompleted: web_search                             │
│                                                                     │
│ 12:00:06  WorkflowCompleted                                        │
│                                                                     │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Summary:                                                            │
│   Duration: 6 seconds                                               │
│   Activities: 2                                                     │
│   Status: Completed                                                 │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

## Component Interaction Diagram

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   FastAPI   │      │   Temporal   │      │  Agent Service  │
│  Control    │      │   Workflow   │      │  (with tools)   │
│   Plane     │      │              │      │                 │
└──────┬──────┘      └──────┬───────┘      └────────┬────────┘
       │                    │                       │
       │ Start workflow     │                       │
       ├───────────────────>│                       │
       │                    │                       │
       │                    │ Execute activity      │
       │                    ├──────────────────────>│
       │                    │                       │
       │                    │                       │ Run agent
       │                    │                       │ + tools
       │                    │                       │
       │                    │ Response (tool_calls) │
       │                    │<──────────────────────┤
       │                    │                       │
       │                    │ record_agent_run      │
       │                    ├──────────────────────>│
       │                    │        ACTIVITY 1     │
       │                    │                       │
       │                    │ record_tool_call      │
       │                    ├──────────────────────>│
       │                    │        ACTIVITY 2     │
       │                    │                       │
       │                    │ record_tool_call      │
       │                    ├──────────────────────>│
       │                    │        ACTIVITY 3     │
       │                    │                       │
       │ Workflow result    │                       │
       │<───────────────────┤                       │
       │                    │                       │
       ▼                    ▼                       ▼
```

---

**Diagram Version:** 1.0  
**Last Updated:** 2026-06-03  
**Purpose:** Visual reference for event tracking architecture
