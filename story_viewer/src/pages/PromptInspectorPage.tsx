import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  listRuns,
  getRunPrompts,
  type RunSummary,
  type RunPrompts,
  type PromptEntry,
} from "../api/client";

const STAGE_ORDER = [
  "concept", "outline", "script", "prose",
  "illustrator", "letterer", "video_editor", "publisher",
];

export function PromptInspectorPage() {
  const { runId, stage: stageParam } = useParams();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runData, setRunData] = useState<RunPrompts | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(stageParam ?? null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    listRuns().then((r) => setRuns(r.runs)).catch(console.error);
  }, []);

  useEffect(() => {
    if (runId) {
      getRunPrompts(runId).then((d) => {
        setRunData(d);
        if (!selectedStage) {
          const first = STAGE_ORDER.find((s) => s in d.stages);
          if (first) setSelectedStage(first);
        }
      });
    }
  }, [runId]);

  const toggleExpand = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  if (!runId) {
    return (
      <div>
        <h1>Prompt Inspector</h1>
        {runs.length === 0 ? (
          <div className="empty">No runs with prompt logs yet.</div>
        ) : (
          runs.map((r) => (
            <div key={r.run_id} className="card" onClick={() => navigate(`/inspector/${r.run_id}`)}>
              <div className="flex justify-between items-center">
                <span className="card-title mono">{r.run_id}</span>
                <span className={`chip ${r.status}`}>{r.status}</span>
              </div>
              <div className="card-meta mt-sm">{r.stages.join(" → ")}</div>
            </div>
          ))
        )}
      </div>
    );
  }

  if (!runData) return <div className="empty">Loading…</div>;

  const stages = STAGE_ORDER.filter((s) => s in runData.stages);
  const stageData = selectedStage ? runData.stages[selectedStage] : null;

  // Group by step for iteration diffs
  const byStep: Record<string, PromptEntry[]> = {};
  if (stageData) {
    for (const e of stageData.entries) {
      (byStep[e.step] ??= []).push(e);
    }
  }

  const totalCost = Object.values(runData.stages).reduce((s, d) => s + d.total_cost, 0);
  const totalTokens = Object.values(runData.stages).reduce(
    (s, d) => s + d.total_input_tokens + d.total_output_tokens, 0
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-md">
        <h1 className="mono" style={{ marginBottom: 0 }}>{runData.run_id}</h1>
        <button className="btn" onClick={() => navigate("/inspector")}>← Runs</button>
      </div>

      {/* Cross-stage cost summary */}
      <div className="summary-bar mb-md">
        <span className="chip cost">${totalCost.toFixed(4)} total</span>
        <span className="chip tokens">{totalTokens.toLocaleString()} tokens</span>
        {stages.map((stage) => {
          const d = runData.stages[stage];
          return (
            <span key={stage} className="chip">
              {stage} ${d.total_cost.toFixed(3)}
            </span>
          );
        })}
      </div>

      <div className="stage-timeline">
        {stages.map((stage) => {
          const d = runData.stages[stage];
          return (
            <button
              key={stage}
              className={`stage-chip ${d.status} ${selectedStage === stage ? "active" : ""}`}
              onClick={() => setSelectedStage(stage)}
            >
              {stage}
              <span style={{ opacity: 0.6, marginLeft: "0.375rem", fontSize: "0.65rem" }}>
                {d.entries.length}
              </span>
            </button>
          );
        })}
      </div>

      {stageData &&
        Object.entries(byStep).map(([step, entries]) => (
          <div key={step} style={{ marginBottom: "1.5rem" }}>
            <div className="flex items-center gap-sm mb-sm">
              <h2 style={{ margin: 0 }}>{step}</h2>
              {entries.length > 1 && (
                <span className="chip">{entries.length} iterations</span>
              )}
            </div>

            {entries.map((entry, i) => {
              const globalIdx = stageData.entries.indexOf(entry);
              const isOpen = expanded.has(globalIdx);
              return (
                <div key={i} className="prompt-entry">
                  <div
                    className="prompt-entry-header"
                    onClick={() => toggleExpand(globalIdx)}
                  >
                    <strong>iter {entry.iteration}</strong>
                    <span className="dim mono" style={{ marginLeft: "0.5rem", fontSize: "0.7rem" }}>
                      {entry.template_name || "inline"}
                    </span>
                    <div className="flex gap-xs items-center" style={{ marginLeft: "auto" }}>
                      <span className="chip model">{entry.model_interface}</span>
                      {entry.cost != null && <span className="chip cost">${entry.cost.toFixed(4)}</span>}
                      {entry.usage && (
                        <span className="chip tokens">
                          {entry.usage.input_tokens}↑ {entry.usage.output_tokens}↓
                        </span>
                      )}
                      <span className="muted" style={{ fontSize: "0.8rem", marginLeft: "0.25rem" }}>
                        {isOpen ? "▾" : "▸"}
                      </span>
                    </div>
                  </div>

                  {isOpen && (
                    <>
                      <div className="prompt-section-label">System</div>
                      <div className="code-block" style={{ borderRadius: 0, border: "none", borderBottom: "1px solid var(--border-soft)" }}>
                        {entry.system_prompt || "(none)"}
                      </div>
                      <div className="prompt-section-label">User</div>
                      <div className="code-block" style={{ borderRadius: 0, border: "none", borderBottom: "1px solid var(--border-soft)" }}>
                        {entry.user_prompt || "(none)"}
                      </div>
                      <div className="prompt-section-label">Response</div>
                      <div className="code-block" style={{ borderRadius: 0, border: "none" }}>
                        {entry.response_text}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
    </div>
  );
}
