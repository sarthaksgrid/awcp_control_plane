# Agent Workforce Control Plane (AWCP)

> **Reference Documents:**
> - [`Agent-Workforce-Control-Plane-Magazine.html`](Agent-Workforce-Control-Plane-Magazine.html) — Technical architecture magazine (§01–§09): operating model, scenarios, data flow, context engineering, user flow, sequence diagrams, UI screens, components, tech stack.
> - [`capstone_roadmap.pdf`](capstone_roadmap.pdf) — 45-day implementation blueprint with weekly task breakdowns per domain.

> [!NOTE]
> **Concept architecture.** This is a concept design, not a production claim. Metrics are illustrative unless tagged "Observed in pilot." UI screens are examples until a workflow reaches approval criteria.
> *(Ref: HTML → Validation Status / Evidence Boundary)*

---

## Evidence Boundary

The control plane **sits above existing runtimes — it does not replace the underlying execution stack.** All governance decisions are scoped to the boundaries below.

| Boundary | Definition |
|:---|:---|
| **Write-capable** | Tool and API calls that create, mutate, deploy, approve, message, or otherwise change system state. |
| **Human approval required** | New write scopes, cross-system writes, rollback/restore decisions, policy exceptions, elevated autonomy. |
| **Conservative mode** | Read-only analysis, increased trace sampling, low-risk routing, recommendation-only continuations, evidence packets. |
| **Evidence** | Workflow identity, actor, policy result, approval token, tool call, context snapshot hash, degradation state, replay trace, rollback pointer. |
| **Stack discipline** | **Core:** identity, policy, expiring approval tokens, durable orchestration, evidence ledger, observability hooks. **Optional:** context graph, local LM summaries. **Replaceable:** model provider, runtime, ticketing system, feature-flag provider. |

> *Ref: `Agent-Workforce-Control-Plane-Magazine.html` → Credibility Discipline / Evidence Boundary*

---

## Operating Model (6 Steps)

> *Ref: `Agent-Workforce-Control-Plane-Magazine.html` §01 — Operating Model*

1. **Register Agents & Attach Control Hooks** — owner, runtime, declared write scopes, feature flags, telemetry, policy callbacks. Under-instrumented agents stay visible but cannot execute governed writes.
2. **Orchestrate Existing Workflows** — Ingest active workflows, normalize state, preserve ownership and checkpoints. The control plane wraps runtimes; it does not replace them.
3. **Gate Write Actions** — Evaluate every state-changing tool call against policy. High-risk actions pause until a narrow, expiring approval token is issued.
4. **Degrade Autonomy Gracefully** — On failure signals: increase trace sampling → tighten retry/concurrency limits → shift to safer profiles → recommendation-only → hard stop. Each workflow can override thresholds.
5. **Replay & Recover** — Replayable ledger with step history, context hashes, degradation state, and safe resume points. Failed branches recover without restarting the full workflow.
6. **Generate Instrumentation Patches** — For agents missing hooks, generate a Codex/Claude-assisted patch or PR for telemetry, feature flags, and policy callbacks before they can leave quarantine.

**90-day proof:** Connect one existing workflow, route state-changing actions through expiring approval tokens, keep the service running through progressive autonomy reduction, and replay every failure from the evidence ledger.

---

## Repository Structure

```
Capstone/Main/
├── requirements.txt                        # Python dependencies
├── .env.example                            # Environment variable template
│
├── src/
│   ├── api.py                              # FastAPI entry point
│   ├── routes.py                           # REST API routes
│   ├── common/                             # Shared config, models, exceptions, logging, DB
│   ├── ingestion/                          # Runtime adapters, event bus, intake proxy
│   ├── governance/                         # Agent registry, OPA policy, approval gate, degradation
│   ├── orchestration/                      # Temporal workflows, context graph, handoff
│   ├── execution/                          # CodeAct sandbox, LLM gateway, tool executors, safer profiles
│   ├── evidence/                           # Evidence ledger, replay engine, OTel telemetry
│   └── ui/                                 # Streamlit operator dashboard
│
├── config/
│   ├── policies/                           # OPA Rego policy files
│   └── feature_flags/                      # OpenFeature / Flipt flag defaults
│
├── deploy/
│   ├── docker/                             # Dockerfile + docker-compose
│   └── k8s/                                # Kubernetes CRDs
│
└── tests/                                  # Mirrors src/ structure
```

---

## Technology Stack & Accelerators

> [!TIP]
> Use the following OSS accelerators to speed up implementation as recommended in §08 and §09 of the Magazine.

| Layer | Recommended Technology | OSS Accelerator | §08 Component |
|:---|:---|:---|:---|
| **Ingestion** | Runtime Adapters + Local LMs | **agent-session-bridge** | Workflow Intake Proxy |
| **Orchestration** | Temporal | **Pentatonic SDK** | Workflow Engine |
| **Context** | Context Graphs + Letta | **Multica** | Context Graph Manager |
| **Governance** | Temporal + OPA | **Pentatonic SDK** | Approval Gate Controller |
| **Governance** | Custom + K8s CRDs | **graph-of-skills** | Agent Registry & Control Hooks |
| **Governance** | OPA + Flags + Local LMs | **Pentatonic SDK** | Degradation Policy Engine |
| **Orchestration** | Custom + Temporal | **agent-session-bridge** | Handoff Coordinator |
| **Execution** | Anthropic / OpenAI | **OpenClaw** | LLM Gateway |
| **Execution** | CodeAct + Modal | **Codex CLI / Claude Code CLI** | CodeAct Sandbox |
| **Platform** | OTel + Object Store | **Pentatonic SDK** | Replayable Evidence Ledger |

---

## Domain 1 — Data Science (Team Size: 3)

**Objective:** Build the Context Intelligence, Safety Mathematics, and Recovery Reasoning.

> *Ref: `capstone_roadmap.pdf` pages 1–6 · `Agent-Workforce-Control-Plane-Magazine.html` §04 Context Engineering, §08 Components*

### Week 1: Context Assembly & Graph Prototyping

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **Workflow State Assembly Logic** — Build the Governing Slice (target: 4K–16K tokens): minimum metadata, owner identity, feature flags, declared write scopes. | `src/orchestration/context_graph/context_manager.py` · `src/common/models.py` |
| DS-2 | **Context Graph Manager Prototyping** — Model memory as a DAG using **Context Graphs + Letta** (long-term recall) and **Multica** (multi-agent comms). Build relevance scoring and token budget management. | `src/orchestration/context_graph/context_manager.py` |
| DS-3 | **Cryptographic Context Hashing** — SHA-256 snapshot of agent state at each step. Tamper-proof, verifiable record. Feeds stale-context detection. | `src/orchestration/context_graph/context_hashing.py` |

### Week 2: Recursive Compression & Trace Summarization

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **RLM Integration** — Configure LLM Gateway for Context Folding. Recursively compress 100-page traces → 10 pages → 1 page. | `src/evidence/replay/rlm_summarizer.py` · `src/execution/llm_gateway/gateway.py` |
| DS-2 | **Artifact Ledger Folding** — Parse massive JSON payloads from tool calls, extract state-changing variables, write to Evidence Ledger. | `src/evidence/ledger/evidence_ledger.py` |
| DS-3 | **Stale-Context Detection** — Compare agent's working memory against the Evidence Ledger to flag outdated/hallucinated state. | `src/orchestration/context_graph/context_hashing.py` · `src/governance/degradation/trigger_evaluator.py` |

### Week 3: Failure Budgeting & Autonomy Thresholds

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **Failure Budget Modeling** — Dynamic threshold formulas evaluating 5 signal types: failure budgets, stale context, policy violations, disagreement, and latency. Central defaults with workflow-specific override ladders. | `src/governance/degradation/trigger_evaluator.py` · `config/policies/failure_budget.rego` |
| DS-2 | **Progressive Autonomy Reduction Ladder** — State transition matrix: Full → Conservative → Recommendation-Only → Hard Stop. | `src/governance/degradation/degradation_engine.py` · `src/execution/safer_profiles/profile_manager.py` |
| DS-3 | **Trace Sampling Multipliers** — Logic to spike trace capture from 10% → 100% on failure signal. | `src/evidence/telemetry/otel_setup.py` · `src/evidence/telemetry/metrics.py` |

### Week 4: Recovery & Replay Intelligence

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **Replay Synthesis Logic** — Prompts/pipelines that read the Evidence Ledger to produce human-readable Replay Summaries (what failed, next safe action). | `src/evidence/replay/replay_engine.py` |
| DS-2 | **Safe Resume Checkpointing** — Scan Context Graph for the last verified Safe Resume Point before the error. | `src/evidence/replay/replay_engine.py` · `src/orchestration/context_graph/context_manager.py` |
| DS-3 | **Cross-Agent Context Transfer** — Ensure the Handoff Coordinator transfers the exact Governing Slice to the remediation agent without context loss. | `src/orchestration/handoff/handoff_coordinator.py` |

### Week 5: Automated Instrumentation & Code Reasoning

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **Codex/Claude Patch Generation** — Read under-instrumented agent code and generate PRs that inject missing observability hooks. | `src/execution/codeact_sandbox/patch_generator.py` |
| DS-2 | **Quarantine Exit Validation** — LLM-as-Judge framework to verify generated patches cover all write-capable functions. | `src/governance/registry/control_hooks.py` · `config/policies/quarantine.rego` |
| DS-3 | **Risk-Tier Classification** — Score every tool call into LOW / MEDIUM / HIGH / CRITICAL tiers. | `src/execution/tool_executors/risk_classifier.py` |

### Week 6: Provider Routing & Safer Profiles

| Engineer | Task | Repo Files |
|:---|:---|:---|
| DS-1 | **Dynamic Model Routing** — Use **OpenClaw** to route simple tasks to cheaper models; pin critical failures to Claude. | `src/execution/llm_gateway/gateway.py` · `src/execution/llm_gateway/providers.py` |
| DS-2 | **Safer Profile Overrides** — Integrate DS models with **OpenFeature/Flipt** to auto-toggle safer profiles on failure. | `src/execution/safer_profiles/profile_manager.py` |
| DS-3 | **90-Day Proof Milestone Evaluation** — Simulate massive cross-system write failure; prove end-to-end degradation. | `tests/governance/test_degradation.py` |

---

## Domain 2 — Python Backend & Orchestration (Team Size: 2)

**Objective:** Build the Durable Orchestration, Security Sandboxing, and Governance Integration.

> *Ref: `capstone_roadmap.pdf` pages 4–6 · `Agent-Workforce-Control-Plane-Magazine.html` §01 Operating Model, §03 Data Flow, §06 Sequence Diagram*

### Week 1: Orchestration Foundations & The Intake Proxy

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **Workflow Intake Proxy** — Build **agent-session-bridge** adapters that normalize runtime-specific signals (REST/gRPC/WebSocket) into a canonical Identity. Also handle Control Signals (alerts, flags, policy events) and Policy Schedules (quarantine checks, expiry scans). | `src/ingestion/intake_proxy.py` · `src/ingestion/adapters/rest_adapter.py` · `src/ingestion/signals/signal_router.py` |
| PB-2 | **Temporal Cluster Initialization** — Configure workflows using **Pentatonic SDK** for durable state and auto-saved history. | `src/orchestration/workflow_engine/worker.py` · `src/orchestration/workflow_engine/workflows.py` |
| Both | **Event Ingestion Pipeline** — Connect to Kafka/NATS/SQS. Implement Load Shaping to smooth agent activity spikes. | `src/ingestion/events/event_consumer.py` · `src/ingestion/events/event_publisher.py` |

### Week 2: Durable Execution & State Machines

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **DAG Modeling & Safe Resume Points** — Model workflows as DAGs. Program Safe Resume Points as Temporal checkpoints. | `src/orchestration/workflow_engine/workflows.py` · `src/orchestration/workflow_engine/activities.py` |
| PB-2 | **Saga Semantics & Compensating Transactions** — Automated rollback scripts for multi-step cross-system writes. | `src/orchestration/workflow_engine/workflows.py` |
| Both | **Idempotency Key Management** — Middleware attaching unique keys to every tool call to prevent duplicate execution. | `src/common/models.py` (ToolCallRequest) · `src/execution/tool_executors/tool_executor.py` |

### Week 3: Sandboxed Execution & CodeAct

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **Modal Ephemeral Sandboxing** — Spin up restricted containers for agent-generated code. Self-destruct after execution. | `src/execution/codeact_sandbox/sandbox_runner.py` |
| PB-2 | **Trace & Artifact Capture** — Intercept sandbox outputs, compress, write to Evidence Ledger. | `src/evidence/ledger/evidence_ledger.py` · `src/evidence/ledger/ledger_models.py` |

### Week 4: Policy Enforcement & Token Gates

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **OPA Integration** — Connect workflow engine to OPA via Approval Gate Controller using **Pentatonic SDK**. | `src/governance/policy/opa_evaluator.py` · `config/policies/*.rego` |
| PB-2 | **Expiring Approval Tokens** — Durable Wait + narrow JWT tokens. Resume workflow only when valid token is presented. | `src/governance/approval/approval_gate.py` · `src/governance/approval/token_manager.py` |

### Week 5: Agent Handoffs & Context Middleware

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **Handoff Coordinator** — Branch isolation and session continuity using **agent-session-bridge** during agent-to-agent handoffs. Prevent context loss, maintain safe resume points. | `src/orchestration/handoff/handoff_coordinator.py` |
| PB-2 | **Agent Registry CRUD API** — Versioned catalog of identity, owner, observability status, write scopes, feature flags, policy callbacks, and quarantine state using **graph-of-skills**. | `src/governance/registry/agent_registry.py` · `src/governance/registry/registry_models.py` · `src/governance/registry/control_hooks.py` |

### Week 6: End-to-End Integration & Load Testing

| Engineer | Task | Repo Files |
|:---|:---|:---|
| PB-1 | **Full API Wire-up** — Connect all routes, replace mocks with live services. Build **Resume/Handoff APIs** (structured JSON, streaming) as output endpoints. | `src/api.py` · `src/routes.py` |
| PB-2 | **Integration Testing** — End-to-end tests for all three scenarios (degradation, approval, quarantine). | `tests/orchestration/test_workflows.py` · `tests/governance/test_approval_gate.py` · `tests/ingestion/test_intake_proxy.py` |

---

## Domain 3 — UI / Frontend (Team Size: 1)

**Objective:** Build the Operator Dashboard, Approval Interfaces, and Live Telemetry Visualization.

> [!IMPORTANT]
> **Design Standards (Sysco Theme):** All UI components must adhere to the editorial system:
> - **Typography:** *Fraunces* (Display), *IBM Plex Sans* (Body), *JetBrains Mono* (Labels).
> - **Color Palette:** *Pepper* (#7A2E1E), *Gold* (#D4A017), *Moss* (#3D4A2E), *Cyan* (#265D6B).
> - **Aesthetics:** Risk-first, card-based layouts with smooth micro-animations.

> *Ref: `capstone_roadmap.pdf` pages 7–9 · `Agent-Workforce-Control-Plane-Magazine.html` §05 User Flow, §07 UI Screens, §08 Components*

### Week 1: Live Control Surface (Risk-First Home)

| Task | Repo Files |
|:---|:---|
| **KPI Grid** — Global Instrumentation Status (%), Degraded workflows, pending tokens, blocked agents, governed actions, median recovery time. | `src/ui/dashboard/home.py` · `src/ui/components/widgets.py` |
| **Workflow Queue Table** — Sortable by failure budgets and policy urgency. Status badges (Degraded, Pending, Quarantined). | `src/ui/dashboard/home.py` |

### Week 2: Replay Workbench & Evidence Explorer

| Task | Repo Files |
|:---|:---|
| **Recovery Workbench** — Degradation ladder accordion, replay evidence code block, context hash display. | `src/ui/dashboard/workflow_detail.py` |
| **Policy Telemetry Carousel** — Rotating cards showing live trace signals, adaptive sampling changes, policy decisions. | `src/ui/components/widgets.py` |

### Week 3: Approval & Quarantine Interfaces

| Task | Repo Files |
|:---|:---|
| **Approval Queue** — Pending approvals sorted by risk/SLA. Show tool plan, context diff, rollback pointer, expiry window. Approve/deny/escalate buttons. | `src/ui/approval_queue/approval_view.py` |
| **Quarantine Exit View** — Onboarding readiness checklist with specific hook checks: (1) OTel span emission for workflow step boundaries, (2) feature-flag callback on autonomy mode transitions, (3) tool checkpoint event before write-capable calls, (4) read-path action logs with request/trace IDs. Patch generation actions, hold/release buttons. | `src/ui/quarantine/quarantine_view.py` |

### Week 4: Tool Gate & Agent Inventory

| Task | Repo Files |
|:---|:---|
| **Tool/Action Gate Table** — State-changing actions awaiting governance. Risk score, decision status, scope, queue. | `src/ui/dashboard/home.py` |
| **Agent Workforce Inventory** — Full catalog with hook status, write scopes, quarantine state, recent activity. | `src/ui/dashboard/agent_inventory.py` |

### Week 5: Notification Channels & Deep Linking

| Task | Repo Files |
|:---|:---|
| **Incident Channel Integration** — Slack/Teams/PagerDuty notifications when workflows degrade or tokens expire. | `src/ingestion/events/event_publisher.py` (UI triggers) |
| **Deep Linking** — Direct links from notifications to specific workflow detail or approval views. | `src/ui/app.py` |

### Week 6: API Wire-up & UX Flow Testing

| Task | Repo Files |
|:---|:---|
| **Replace Mocks with Live Endpoints** — Wire all views to the Python backend's FastAPI. Handle loading states, timeouts. | `src/ui/app.py` · all `src/ui/dashboard/*.py` |
| **End-to-End Operator Flow Test** — Discover degraded workflow → open replay → review context hash → approve token → resume workflow. | `tests/ui/test_dashboard.py` |

---

## Domain 4 — DevOps & Infrastructure (Team Size: 1)

**Objective:** Build the Control Substrate, Evidence Boundary, and Security Sandboxing.

> *Ref: `capstone_roadmap.pdf` pages 10–12 · `Agent-Workforce-Control-Plane-Magazine.html` §08 Components, §09 Tech Stack*

### Week 1: Control Substrate & Evidence Boundary

| Task | Repo Files |
|:---|:---|
| **Temporal Cluster Deployment** — Production-ready Temporal on Kubernetes with PostgreSQL persistence. | `deploy/docker/docker-compose.yaml` · `deploy/k8s/` |
| **Evidence Ledger Storage** — Append-only object store (S3/MinIO) for immutable audit trail. WORM policies. | `src/evidence/ledger/evidence_ledger.py` · `deploy/docker/docker-compose.yaml` |

### Week 2: Security Sandboxing & CodeAct Environment

| Task | Repo Files |
|:---|:---|
| **Modal Integration** — Ephemeral containers for agent code execution. Self-destruct after returning output. | `src/execution/codeact_sandbox/sandbox_runner.py` · `deploy/docker/Dockerfile` |
| **Network Egress & Branch Isolation** — Strict network policies (Calico/Cilium). Contain rogue agents to their sandbox. | `deploy/k8s/` |

### Week 3: Observability & Telemetry Backbone

| Task | Repo Files |
|:---|:---|
| **OTel Collector Deployment** — Fleet of collectors routing metrics to UI dashboard and raw traces to Evidence Ledger. | `src/evidence/telemetry/otel_setup.py` · `deploy/docker/docker-compose.yaml` |
| **Dynamic Trace Sampling** — Spike capture from 10% → 100% on failure budget breach. Wired to DS failure models. | `src/evidence/telemetry/otel_setup.py` · `src/evidence/telemetry/metrics.py` |

### Week 4: Feature Flags & Governance Policies

| Task | Repo Files |
|:---|:---|
| **OpenFeature / Flipt Deployment** — Feature-flag control plane for Safer Profiles and autonomy modes. | `config/feature_flags/defaults.yaml` · `deploy/docker/docker-compose.yaml` |
| **OPA Server Setup** — Ultra-low-latency policy evaluation. Rego rules for write scopes, risk tiers, quarantine. | `config/policies/*.rego` · `deploy/docker/docker-compose.yaml` |

### Week 5: Quarantine & Patch Pipeline

| Task | Repo Files |
|:---|:---|
| **Quarantine Entry Routing** — API Gateway enforcement. Block agents missing OTel hooks or OPA callbacks. | `config/policies/quarantine.rego` · `deploy/k8s/agent_crd.yaml` |
| **CI/CD for Instrumentation Patches** — GitOps pipeline (ArgoCD) to auto-open PRs from Codex-generated patches. | `src/execution/codeact_sandbox/patch_generator.py` (infra integration) |

### Week 6: LLM Gateway Failover & Chaos Engineering

| Task | Repo Files |
|:---|:---|
| **LLM Gateway Provider Pinning** — Force recovery prompts to Claude; configure automatic failovers. | `src/execution/llm_gateway/providers.py` |
| **Chaos Engineering** — Kill Temporal workers, simulate timeouts, trigger failure budgets. Prove the system degrades safely. | `tests/` (all integration tests) |

---

## Cross-Domain Orchestration (Weeks 1–6)

> *Ref: `capstone_roadmap.pdf` pages 13–14 · `Agent-Workforce-Control-Plane-Magazine.html` §02 Scenarios A/B/C*

| Week | Cross-Domain Task | Shared Repo Files |
|:---|:---|:---|
| 1–2 | **Target Workflow Selection** — Agree on single workflow to govern first (e.g., "refund-branch-882"). **Stack Discipline** — Separate Core (identity, policy, ledger) from Replaceable (LLM, flags). **Shared Vocabulary** — Map Governing Slice, Temporal Checkpoint, Replay Summary to exact JSON schemas. | `src/common/models.py` · `src/common/config.py` · `src/common/exceptions.py` |
| 3–4 | **Data→Backend Handoff** — Live event through Temporal → DS scorer → safe/unsafe signal (< 800ms). **Backend→Infra Sandboxing** — LLM-generated script → Modal container → Evidence Ledger fold. **Infra→UI Telemetry** — OTel spans + flag states → dashboard (flag flip = instant UI update). | `src/ingestion/intake_proxy.py` · `src/orchestration/workflow_engine/` · `src/evidence/` · `src/ui/` |
| 5–6 | **Scenario A** (Graceful Degradation): Force 3 write failures → auto-increase trace → safer profile → degraded on dashboard. **Scenario B** (Approval Tokens): Massive DB change → OPA blocks → DS evaluates → operator approves via UI → workflow resumes. **Scenario C** (Quarantine): Rogue agent → DevOps quarantines → Codex patch → operator reviews in UI → agent exits quarantine. | All layers end-to-end |

---

## Quick Start

```bash
cd Capstone/Main
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # fill in values
docker compose -f deploy/docker/docker-compose.yaml up -d
uvicorn src.api:app --reload   # API on :8000
streamlit run src/ui/app.py    # Dashboard on :8501
pytest tests/ -v               # Run tests
```
