import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listRuns, getRunPrompts, type RunSummary, type RunPrompts } from "../api/client";

const STAGE_ORDER = [
  "concept", "outline", "script", "prose",
  "illustrator", "letterer", "video_editor", "publisher",
];

export function PipelineViewPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runData, setRunData] = useState<RunPrompts | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);

  useEffect(() => {
    listRuns().then((r) => setRuns(r.runs)).catch(console.error);
  }, []);

  useEffect(() => {
    if (runId) {
      getRunPrompts(runId).then((d) => {
        setRunData(d);
        const first = STAGE_ORDER.find((s) => s in d.stages);
        if (first) setSelectedStage(first);
      }).catch(console.error);
    }
  }, [runId]);

  if (!runId) {
    return (
      <div>
        <h1>Pipeline Runs</h1>
        {runs.length === 0 ? (
          <div className="empty">No pipeline runs yet.</div>
        ) : (
          runs.map((r) => (
            <div key={r.run_id} className="card" onClick={() => navigate(`/pipeline/${r.run_id}`)}>
              <div className="flex justify-between items-center">
                <span className="card-title mono">{r.run_id}</span>
                <span className={`chip ${r.status}`}>{r.status}</span>
              </div>
              <div className="card-meta mt-sm">
                {r.stages.join(" → ")}
              </div>
            </div>
          ))
        )}
      </div>
    );
  }

  if (!runData) return <div className="empty">Loading…</div>;

  const stages = STAGE_ORDER.filter((s) => s in runData.stages);
  const stageData = selectedStage ? runData.stages[selectedStage] : null;

  const totalCost = Object.values(runData.stages).reduce((sum, s) => sum + s.total_cost, 0);
  const totalTokens = Object.values(runData.stages).reduce(
    (sum, s) => sum + s.total_input_tokens + s.total_output_tokens, 0
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-md">
        <h1 className="mono" style={{ marginBottom: 0 }}>{runData.run_id}</h1>
        <button className="btn" onClick={() => navigate("/pipeline")}>← Runs</button>
      </div>

      {/* Summary */}
      <div className="summary-bar mb-md">
        <span className="chip cost">${totalCost.toFixed(4)} total</span>
        <span className="chip tokens">{totalTokens.toLocaleString()} tokens</span>
        <span className="chip">{Object.keys(runData.stages).length} stages</span>
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
            </button>
          );
        })}
      </div>

      {stageData && (
        <div>
          <div className="flex gap-sm mb-md items-center">
            <span className="chip cost">${stageData.total_cost.toFixed(4)}</span>
            <span className="chip tokens">
              {(stageData.total_input_tokens + stageData.total_output_tokens).toLocaleString()} tokens
            </span>
            <span className="chip">{stageData.entries.length} exchanges</span>
          </div>

          {stageData.entries.map((entry, i) => (
            <div key={i} className="prompt-entry">
              <div className="prompt-entry-header">
                <strong>{entry.step}</strong>
                <span className="dim" style={{ marginLeft: "0.5rem", fontSize: "0.75rem" }}>
                  iteration {entry.iteration}
                </span>
                <div className="flex gap-xs items-center" style={{ marginLeft: "auto" }}>
                  <span className="chip model">{entry.model_interface}</span>
                  {entry.cost != null && <span className="chip cost">${entry.cost.toFixed(4)}</span>}
                  {entry.usage && (
                    <span className="chip tokens">
                      {entry.usage.input_tokens}+{entry.usage.output_tokens}
                    </span>
                  )}
                </div>
              </div>
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
