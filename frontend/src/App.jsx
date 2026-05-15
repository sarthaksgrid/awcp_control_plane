import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

function StatusBadge({ value }) {
  const tone = value?.includes("approval") || value === "escalate" ? "warn" : value === "deny" ? "danger" : "ok";
  return <span className={`badge badge-${tone}`}>{value}</span>;
}

function Kpi({ label, value }) {
  return (
    <section className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

export default function App() {
  const [data, setData] = useState({ kpis: {}, workflows: [], approvals: [], evidence: [] });
  const [selectedWorkflow, setSelectedWorkflow] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const dashboard = await api("/api/pb2/dashboard");
    setData(dashboard);
    if (!selectedWorkflow && dashboard.workflows.length > 0) {
      setSelectedWorkflow(dashboard.workflows[0].workflow_id);
    }
  }

  async function runAction(action) {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
    const timer = setInterval(() => load().catch(() => {}), 5000);
    return () => clearInterval(timer);
  }, []);

  const selectedEvidence = useMemo(
    () => data.evidence.filter((entry) => !selectedWorkflow || entry.workflow_id === selectedWorkflow),
    [data.evidence, selectedWorkflow]
  );

  const activeWorkflow = data.workflows.find((workflow) => workflow.workflow_id === selectedWorkflow);
  const pendingApprovals = data.approvals.filter((approval) => approval.status === "pending");
  const approvalHistory = data.approvals.filter((approval) => approval.status !== "pending");
  const canFoldSandbox = activeWorkflow?.status === "approved_ready_for_sandbox" || activeWorkflow?.status === "sandbox_complete";

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">PB-2 Python Full Stack Backend</p>
          <h1>AWCP Control Surface</h1>
        </div>
        <div className="actions">
          <button
            disabled={busy}
            onClick={() => runAction(() => api("/api/pb2/workflows/temporal/start", { method: "POST", body: "{}" }))}
          >
            Start Temporal Flow
          </button>
          <button
            disabled={busy}
            onClick={() => runAction(() => api("/api/pb2/workflows/simulate", { method: "POST", body: "{}" }))}
          >
            Simulate Risky Flow
          </button>
          <button
            disabled={busy || !canFoldSandbox}
            onClick={() =>
              runAction(() =>
                api("/api/pb2/sandbox/run", {
                  method: "POST",
                  body: JSON.stringify({ workflow_id: activeWorkflow.workflow_id, branch_id: activeWorkflow.branch_id }),
                })
              )
            }
          >
            Fold Sandbox Evidence
          </button>
          <button
            className="ghost"
            disabled={busy}
            onClick={() => runAction(() => api("/api/pb2/reset", { method: "POST", body: "{}" }))}
          >
            Reset Demo
          </button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="kpiGrid">
        <Kpi label="Active workflows" value={data.kpis.active_workflows || 0} />
        <Kpi label="Pending tokens" value={data.kpis.pending_approvals || 0} />
        <Kpi label="Evidence entries" value={data.kpis.evidence_entries || 0} />
        <Kpi label="Degraded flows" value={data.kpis.degraded_workflows || 0} />
      </section>

      <section className="layout">
        <div className="panel">
          <div className="panelHead">
            <h2>Workflow Queue</h2>
            <span>{data.workflows.length} governed</span>
          </div>
          <div className="table">
            {data.workflows.map((workflow) => (
              <button
                className={`row ${selectedWorkflow === workflow.workflow_id ? "rowActive" : ""}`}
                key={workflow.workflow_id}
                onClick={() => setSelectedWorkflow(workflow.workflow_id)}
              >
                <span>
                  <strong>{workflow.workflow_id}</strong>
                  <small>{workflow.agent_id} · {workflow.owner}</small>
                </span>
                <StatusBadge value={workflow.status} />
                <span className="mono">{workflow.risk_tier}</span>
              </button>
            ))}
            {data.workflows.length === 0 && <p className="empty">Run a simulation to create the first workflow.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panelHead">
            <h2>Approval Queue</h2>
            <span>{pendingApprovals.length} pending</span>
          </div>
          <div className="approvalList">
            {pendingApprovals.map((approval) => (
              <article className="approval" key={approval.id}>
                <div>
                  <strong>{approval.action_class}</strong>
                  <p>{approval.reason}</p>
                  <small className="mono">{approval.rollback_pointer}</small>
                </div>
                <StatusBadge value={approval.status} />
                <div className="inlineActions">
                  <button
                    disabled={busy || approval.status !== "pending"}
                    onClick={() =>
                      runAction(() =>
                        api(`/api/pb2/approvals/${approval.id}/approve`, {
                          method: "POST",
                          body: JSON.stringify({ operator: "operator.demo" }),
                        })
                      )
                    }
                  >
                    Approve
                  </button>
                  <button
                    className="ghost"
                    disabled={busy || approval.status !== "pending"}
                    onClick={() =>
                      runAction(() =>
                        api(`/api/pb2/approvals/${approval.id}/deny`, {
                          method: "POST",
                          body: JSON.stringify({ operator: "operator.demo" }),
                        })
                      )
                    }
                  >
                    Deny
                  </button>
                </div>
              </article>
            ))}
            {pendingApprovals.length === 0 && (
              <p className="empty">No action is waiting right now. Start a Temporal flow to create a pending token.</p>
            )}
            {approvalHistory.length > 0 && (
              <div className="history">
                <span>History</span>
                {approvalHistory.map((approval) => (
                  <article className="approval approvalHistory" key={approval.id}>
                    <div>
                      <strong>{approval.action_class}</strong>
                      <p>{approval.reason}</p>
                      <small className="mono">{approval.rollback_pointer}</small>
                    </div>
                    <StatusBadge value={approval.status} />
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="workbench">
        <div className="panel">
          <div className="panelHead">
            <h2>Recovery Workbench</h2>
            <span>{activeWorkflow?.autonomy_mode || "idle"}</span>
          </div>
          {activeWorkflow ? (
            <div className="detailGrid">
              <div>
                <label>Context hash</label>
                <code>{activeWorkflow.context_hash}</code>
              </div>
              <div>
                <label>Policy decision</label>
                <StatusBadge value={activeWorkflow.policy_decision} />
              </div>
              <div className="wide">
                <label>Latest summary</label>
                <p>{activeWorkflow.latest_summary}</p>
              </div>
            </div>
          ) : (
            <p className="empty">Select a workflow to inspect replay state.</p>
          )}
        </div>

        <div className="panel evidencePanel">
          <div className="panelHead">
            <h2>Evidence Ledger</h2>
            <span>{selectedEvidence.length} visible</span>
          </div>
          <div className="timeline">
            {selectedEvidence.map((entry) => (
              <article className="event" key={entry.id}>
                <div className="dot" />
                <div>
                  <strong>{entry.action}</strong>
                  <p>{entry.actor} · {entry.policy_result} · {entry.degradation_state}</p>
                  <pre>{JSON.stringify(entry.replay_trace, null, 2)}</pre>
                </div>
              </article>
            ))}
            {selectedEvidence.length === 0 && <p className="empty">Evidence appears here after simulation.</p>}
          </div>
        </div>
      </section>
    </main>
  );
}
