import { useEffect, useState } from "react";
import {
  listTemplates,
  getTemplate,
  saveTemplate,
  previewTemplate,
  type TemplateMeta,
  type TemplateDetail,
  type TemplatePreview,
} from "../api/client";

export function TemplateEditorPage() {
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [source, setSource] = useState("");
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [previewCtx, setPreviewCtx] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTemplates().then((r) => setTemplates(r.templates)).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selected) return;
    getTemplate(selected).then((d) => {
      setDetail(d);
      setSource(d.source);
      setDirty(false);
      setPreview(null);
      setError(null);
      const ctx: Record<string, string> = {};
      for (const v of d.variables) ctx[v] = "";
      setPreviewCtx(ctx);
    });
  }, [selected]);

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await saveTemplate(selected, source);
      setDirty(false);
    } catch (e: unknown) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    if (!selected) return;
    setError(null);
    try {
      setPreview(await previewTemplate(selected, previewCtx));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // Group by directory
  const groups: Record<string, TemplateMeta[]> = {};
  for (const t of templates) {
    const dir = t.name.split("/")[0];
    (groups[dir] ??= []).push(t);
  }

  return (
    <div className="split">
      {/* Sidebar */}
      <div className="sidebar">
        {Object.entries(groups).map(([dir, items]) => (
          <div key={dir} className="sidebar-group">
            <div className="sidebar-group-label">{dir}</div>
            {items.map((t) => (
              <div
                key={t.name}
                className={`sidebar-item ${selected === t.name ? "active" : ""}`}
                onClick={() => setSelected(t.name)}
                title={t.description}
              >
                {t.name.split("/").slice(1).join("/")}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Editor */}
      <div className="content">
        {!selected ? (
          <div className="empty">Select a template to edit</div>
        ) : (
          <>
            <div className="editor-header">
              <h1>{selected}</h1>
              <div className="flex gap-sm">
                <button className="btn" onClick={handlePreview}>
                  Preview
                </button>
                <button
                  className={`btn ${dirty ? "btn-primary" : ""}`}
                  onClick={handleSave}
                  disabled={saving || !dirty}
                >
                  {saving ? "Saving…" : dirty ? "Save" : "Saved"}
                </button>
              </div>
            </div>

            {/* Variable inputs */}
            {detail && detail.variables.length > 0 && (
              <div className="mb-md">
                <div className="sidebar-group-label" style={{ paddingLeft: 0, marginBottom: "0.5rem" }}>
                  Preview variables
                </div>
                <div className="var-grid">
                  {detail.variables.map((v) => (
                    <div key={v}>
                      <div className="var-input-label">{v}</div>
                      <input
                        className="var-input"
                        placeholder={`{{ ${v} }}`}
                        value={previewCtx[v] ?? ""}
                        onChange={(e) =>
                          setPreviewCtx((p) => ({ ...p, [v]: e.target.value }))
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <textarea
              className="template-editor"
              value={source}
              spellCheck={false}
              onChange={(e) => {
                setSource(e.target.value);
                setDirty(true);
              }}
            />

            {error && (
              <div style={{ color: "var(--error)", fontSize: "0.8rem", marginTop: "0.5rem" }}>
                {error}
              </div>
            )}

            {preview && (
              <div className="preview-panel mt-md">
                <div className="preview-panel-header">Rendered Preview</div>

                {preview.base_instruction && (
                  <>
                    <div className="prompt-section-label">Base Instruction</div>
                    <div className="code-block" style={{ borderRadius: 0, border: "none", borderBottom: "1px solid var(--border-soft)" }}>
                      {preview.base_instruction}
                    </div>
                  </>
                )}

                {Object.entries(preview.sections).map(([name, content]) => (
                  <div key={name}>
                    <div className="prompt-section-label">Section: {name}</div>
                    <div className="code-block" style={{ borderRadius: 0, border: "none", borderBottom: "1px solid var(--border-soft)" }}>
                      {content}
                    </div>
                  </div>
                ))}

                {preview.critical_requirements.length > 0 && (
                  <>
                    <div className="prompt-section-label">
                      Critical Requirements ({preview.critical_requirements.length})
                    </div>
                    <div className="code-block" style={{ borderRadius: 0, border: "none", borderBottom: "1px solid var(--border-soft)" }}>
                      {preview.critical_requirements.map((r, i) => `${i + 1}. ${r}`).join("\n\n")}
                    </div>
                  </>
                )}

                {preview.requirements.length > 0 && (
                  <>
                    <div className="prompt-section-label">
                      Requirements ({preview.requirements.length})
                    </div>
                    <div className="code-block" style={{ borderRadius: 0, border: "none" }}>
                      {preview.requirements.map((r, i) => `${i + 1}. ${r}`).join("\n\n")}
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
