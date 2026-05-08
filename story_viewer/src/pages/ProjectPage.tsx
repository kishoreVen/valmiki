import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  createTemplate,
  createCharacter,
  deleteCharacter,
  updateWorld,
  addStoryRun,
  type Project,
  type CharacterTemplate,
  type World,
  type WorldRule,
} from "../lib/character-store";
import "../character.css";

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);

  // World editing
  const [worldDesc, setWorldDesc] = useState("");
  const [ruleInput, setRuleInput] = useState("");
  const [isCompacting, setIsCompacting] = useState<"characters" | "stories" | null>(null);

  // Character / template modal
  const [showCharModal, setShowCharModal] = useState(false);
  const [pickedTemplate, setPickedTemplate] = useState<CharacterTemplate | null>(null);
  const [newTemplateMode, setNewTemplateMode] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState("");

  // Generate Story modal
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [genTheme, setGenTheme] = useState("");
  const [selectedCharIds, setSelectedCharIds] = useState<string[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    const p = getProject(projectId!);
    if (!p) {
      navigate("/characters");
      return;
    }
    setProject(p);
    setWorldDesc(p.world.description);
  }, [projectId]);

  if (!project) return null;

  const hasTemplates = project.templates.length > 0;
  const templateById = Object.fromEntries(project.templates.map((t) => [t.id, t]));

  // ── World actions ─────────────────────────────────────────────────────────

  function saveWorldDesc() {
    if (!project) return;
    const updated: World = { ...project.world, description: worldDesc };
    updateWorld(project.id, updated);
    setProject(getProject(project.id)!);
  }

  function handleAddRule() {
    if (!ruleInput.trim() || !project) return;
    const rule: WorldRule = {
      id: crypto.randomUUID(),
      text: ruleInput.trim(),
      source: "user",
      createdAt: new Date().toISOString(),
    };
    const updated: World = { ...project.world, rules: [...project.world.rules, rule] };
    updateWorld(project.id, updated);
    setProject(getProject(project.id)!);
    setRuleInput("");
  }

  function handleDeleteRule(ruleId: string) {
    if (!project) return;
    const updated: World = { ...project.world, rules: project.world.rules.filter((r) => r.id !== ruleId) };
    updateWorld(project.id, updated);
    setProject(getProject(project.id)!);
  }

  async function handleCompactCharacters() {
    if (isCompacting || !project || project.characters.length === 0) return;
    setIsCompacting("characters");
    try {
      const characters = project.characters.map((c) => {
        const tmpl = project.templates.find((t) => t.id === c.templateId);
        if (!tmpl) return null;
        const named: Record<string, unknown> = {};
        for (const field of tmpl.fields) {
          if (c.values[field.id] !== undefined) named[field.name] = c.values[field.id];
        }
        return named;
      }).filter(Boolean);

      const res = await fetch("/api/projects/compact/characters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          world_description: project.world.description,
          world_rules: project.world.rules.map((r) => r.text),
          characters,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { description, rules: ruleTexts } = await res.json();

      const now = new Date().toISOString();
      const userRules = project.world.rules.filter((r) => r.source === "user");
      const storyRules = project.world.rules.filter((r) => r.source === "story_compaction");
      const newCharRules: WorldRule[] = (ruleTexts as string[]).map((text) => ({
        id: crypto.randomUUID(),
        text,
        source: "character_compaction" as const,
        createdAt: now,
      }));

      const updatedWorld: World = {
        ...project.world,
        description,
        rules: [...userRules, ...newCharRules, ...storyRules],
        lastCharacterCompactionAt: now,
      };
      updateWorld(project.id, updatedWorld);
      const fresh = getProject(project.id)!;
      setProject(fresh);
      setWorldDesc(description);
    } catch (e) {
      console.error("Character compaction failed:", e);
    } finally {
      setIsCompacting(null);
    }
  }

  async function handleCompactStories() {
    if (isCompacting || !project || project.world.storyRuns.length === 0) return;
    setIsCompacting("stories");
    try {
      const res = await fetch("/api/projects/compact/stories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          world_description: project.world.description,
          world_rules: project.world.rules.map((r) => r.text),
          stories: project.world.storyRuns,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { description, rules: ruleTexts } = await res.json();

      const now = new Date().toISOString();
      const userRules = project.world.rules.filter((r) => r.source === "user");
      const charRules = project.world.rules.filter((r) => r.source === "character_compaction");
      const newStoryRules: WorldRule[] = (ruleTexts as string[]).map((text) => ({
        id: crypto.randomUUID(),
        text,
        source: "story_compaction" as const,
        createdAt: now,
      }));

      const updatedWorld: World = {
        ...project.world,
        description,
        rules: [...userRules, ...charRules, ...newStoryRules],
        lastStoryCompactionAt: now,
      };
      updateWorld(project.id, updatedWorld);
      const fresh = getProject(project.id)!;
      setProject(fresh);
      setWorldDesc(description);
    } catch (e) {
      console.error("Story compaction failed:", e);
    } finally {
      setIsCompacting(null);
    }
  }

  // ── Template actions ──────────────────────────────────────────────────────

  function handleCreateTemplate() {
    if (!newTemplateName.trim()) return;
    const t = createTemplate(project!.id, newTemplateName.trim());
    setShowCharModal(false);
    setNewTemplateMode(false);
    setNewTemplateName("");
    navigate(`/characters/${project!.id}/t/${t.id}`);
  }

  // ── Character actions ─────────────────────────────────────────────────────

  function openCharModal() {
    setPickedTemplate(null);
    setNewTemplateMode(false);
    setNewTemplateName("");
    setShowCharModal(true);
  }

  function handleCreateCharacter() {
    if (!pickedTemplate) return;
    const char = createCharacter(project!.id, pickedTemplate.id);
    setShowCharModal(false);
    navigate(`/characters/${project!.id}/t/${pickedTemplate.id}/c/${char.id}`);
  }

  function handleDeleteCharacter(e: React.MouseEvent, charId: string) {
    e.stopPropagation();
    if (!confirm("Delete this character?")) return;
    deleteCharacter(project!.id, charId);
    setProject(getProject(project!.id)!);
  }

  // ── Generate Story ────────────────────────────────────────────────────────

  async function handleGenerate() {
    if (!genTheme.trim() || isGenerating || !project) return;
    setIsGenerating(true);
    try {
      const characters = selectedCharIds.map((charId) => {
        const c = project.characters.find((x) => x.id === charId);
        if (!c) return null;
        const tmpl = project.templates.find((t) => t.id === c.templateId);
        if (!tmpl) return null;
        const named: Record<string, unknown> = { identifier: c.id };
        for (const field of tmpl.fields) {
          if (c.values[field.id] !== undefined) {
            named[field.name.toLowerCase().replace(/\s+/g, "_")] = c.values[field.id];
          }
        }
        return named;
      }).filter(Boolean);

      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          theme: genTheme.trim(),
          characters,
          project_id: project.id,
          world_description: project.world.description,
          world_rules: project.world.rules.map((r) => r.text),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { run_id } = await res.json();

      addStoryRun(project.id, { runId: run_id, theme: genTheme.trim(), createdAt: new Date().toISOString() });
      setProject(getProject(project.id)!);
      setShowGenerateModal(false);
      setGenTheme("");
      setSelectedCharIds([]);
      navigate(`/inspector/${run_id}`);
    } catch (e) {
      console.error("Generate failed:", e);
    } finally {
      setIsGenerating(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="cm-root">
      <div className="cm-inner">
        {/* Header */}
        <div className="cm-page-header">
          <div className="cm-breadcrumb">
            <button className="cm-btn cm-btn-ghost" onClick={() => navigate("/characters")}>
              ← Projects
            </button>
            <span className="cm-breadcrumb-sep">/</span>
            <span className="cm-breadcrumb-current">{project.name}</span>
          </div>
          <div className="cm-header-actions">
            <button className="cm-btn cm-btn-primary" onClick={openCharModal}>
              + New Character
            </button>
          </div>
        </div>

        {/* ── World section ── */}
        <div className="cm-section">
          <div className="cm-section-header">
            <span className="cm-section-label">World</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="cm-btn"
                style={{ height: 28, fontSize: 12, padding: "0 10px" }}
                onClick={handleCompactCharacters}
                disabled={isCompacting !== null || project.characters.length === 0}
                title={project.characters.length === 0 ? "Add characters first" : "Update world from character data"}
              >
                {isCompacting === "characters" ? "Updating…" : "Update from Characters"}
              </button>
              <button
                className="cm-btn"
                style={{ height: 28, fontSize: 12, padding: "0 10px" }}
                onClick={handleCompactStories}
                disabled={isCompacting !== null || project.world.storyRuns.length === 0}
                title={project.world.storyRuns.length === 0 ? "Generate a story first" : "Update world from story data"}
              >
                {isCompacting === "stories" ? "Updating…" : "Update from Stories"}
              </button>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 6 }}>Description</div>
            <textarea
              className="cm-input"
              style={{ width: "100%", minHeight: 90, resize: "vertical" }}
              placeholder="Describe this world — its tone, setting, history, rules of nature…"
              value={worldDesc}
              onChange={(e) => setWorldDesc(e.target.value)}
              onBlur={saveWorldDesc}
            />
          </div>

          <div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 8 }}>Canon Rules</div>
            {project.world.rules.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                {project.world.rules.map((rule) => (
                  <div
                    key={rule.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "4px 10px",
                      borderRadius: 20,
                      background: rule.source === "user" ? "var(--surface-2)" : "var(--hi-bg)",
                      border: `1px solid ${rule.source === "user" ? "var(--border-mid)" : "var(--hi)"}`,
                      fontSize: 12,
                      color: "var(--text)",
                    }}
                  >
                    <span>{rule.text}</span>
                    <button
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", fontSize: 16, lineHeight: 1, padding: 0, marginLeft: 2 }}
                      onClick={() => handleDeleteRule(rule.id)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="cm-input"
                style={{ flex: 1 }}
                placeholder="Add a canon rule…"
                value={ruleInput}
                onChange={(e) => setRuleInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddRule()}
              />
              <button
                className="cm-btn"
                style={{ padding: "0 14px", whiteSpace: "nowrap" }}
                onClick={handleAddRule}
                disabled={!ruleInput.trim()}
              >
                + Add
              </button>
            </div>
          </div>
        </div>

        {/* ── Characters section ── */}
        <div className="cm-section">
          <div className="cm-section-header">
            <span className="cm-section-label">Characters ({project.characters.length})</span>
          </div>

          {project.characters.length === 0 ? (
            <div className="cm-empty">
              <div className="cm-empty-icon">✦</div>
              <p className="cm-empty-title">No characters yet</p>
              <p className="cm-empty-desc">Create your first character — or define a template for your cast.</p>
              <button className="cm-btn cm-btn-primary" onClick={openCharModal}>
                + New Character
              </button>
            </div>
          ) : (
              <div className="cm-roster-grid">
                {project.characters.map((c) => {
                  const tmpl = templateById[c.templateId];
                  const nameField = tmpl?.fields.find(
                    (f) => f.name.toLowerCase() === "name" || f.name.toLowerCase() === "character name"
                  );
                  const portraitField = tmpl?.fields.find((f) => f.kind === "image");
                  const charName = nameField ? ((c.values[nameField.id] as string) || "Unnamed") : "Character";
                  const portraitUrl = portraitField ? (c.values[portraitField.id] as string) || null : null;

                  return (
                    <div
                      key={c.id}
                      className="cm-roster-card"
                      onClick={() => navigate(`/characters/${project.id}/t/${c.templateId}/c/${c.id}`)}
                    >
                      <div className="cm-roster-portrait">
                        {portraitUrl ? (
                          <img src={portraitUrl} alt={charName} />
                        ) : (
                          <div className="cm-roster-portrait-placeholder">{charName[0]?.toUpperCase() ?? "?"}</div>
                        )}
                      </div>
                      <div className="cm-roster-name">{charName}</div>
                      {tmpl && project.templates.length > 1 && (
                        <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 3 }}>{tmpl.name}</div>
                      )}
                      <button
                        className="cm-btn cm-btn-danger-ghost cm-roster-delete"
                        onClick={(e) => handleDeleteCharacter(e, c.id)}
                      >
                        Delete
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
        </div>

        {/* ── Stories section ── */}
        <div className="cm-section">
          <div className="cm-section-header">
            <span className="cm-section-label">Stories ({project.world.storyRuns.length})</span>
            {hasTemplates && project.characters.length > 0 && (
              <button
                className="cm-btn cm-btn-primary"
                style={{ height: 30, fontSize: 12, padding: "0 12px" }}
                onClick={() => setShowGenerateModal(true)}
              >
                Generate Story
              </button>
            )}
          </div>

          {project.world.storyRuns.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-3)", padding: "4px 0 8px" }}>
              No stories yet.{hasTemplates && project.characters.length > 0 ? " Generate one above." : " Create characters first."}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {project.world.storyRuns.map((run) => (
                <div
                  key={run.runId}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    borderRadius: "var(--r-sm)",
                    background: "var(--surface-2)",
                    border: "1px solid var(--border-mid)",
                    cursor: "pointer",
                    transition: "border-color 0.12s",
                  }}
                  onClick={() => navigate(`/inspector/${run.runId}`)}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{run.theme}</div>
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
                      {new Date(run.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                    </div>
                  </div>
                  <span style={{ fontSize: 12, color: "var(--text-3)" }}>View →</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── New Character / Template modal ── */}
      {showCharModal && (
        <div className="cm-modal-overlay" onClick={() => { setShowCharModal(false); setNewTemplateMode(false); setNewTemplateName(""); }}>
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="cm-modal-title">New Character</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
              {project.templates.map((t) => (
                <div
                  key={t.id}
                  onClick={() => setPickedTemplate(t)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "12px 14px",
                    borderRadius: "var(--r-sm)",
                    border: `1px solid ${pickedTemplate?.id === t.id ? "var(--hi)" : "var(--border-mid)"}`,
                    background: pickedTemplate?.id === t.id ? "var(--hi-bg)" : "var(--surface-2)",
                    cursor: "pointer",
                    transition: "border-color 0.12s, background 0.12s",
                  }}
                >
                  <div style={{ width: 32, height: 32, borderRadius: "var(--r-xs)", background: "var(--hi-bg)", color: "var(--hi)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 14, flexShrink: 0 }}>
                    {t.name[0]?.toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{t.name}</div>
                    <div style={{ fontSize: 12, color: "var(--text-2)" }}>{t.fields.length} field{t.fields.length !== 1 ? "s" : ""}</div>
                  </div>
                </div>
              ))}
              {newTemplateMode ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    className="cm-input"
                    style={{ flex: 1 }}
                    placeholder="e.g. Hero, NPC, Villain…"
                    value={newTemplateName}
                    onChange={(e) => setNewTemplateName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreateTemplate()}
                    autoFocus
                  />
                  <button className="cm-btn cm-btn-primary" onClick={handleCreateTemplate} disabled={!newTemplateName.trim()}>
                    Create →
                  </button>
                  <button className="cm-btn" onClick={() => { setNewTemplateMode(false); setNewTemplateName(""); }}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  className="cm-btn"
                  style={{ alignSelf: "flex-start", fontSize: 12 }}
                  onClick={() => setNewTemplateMode(true)}
                >
                  + New Template
                </button>
              )}
            </div>
            <div className="cm-modal-actions">
              <button className="cm-btn" onClick={() => { setShowCharModal(false); setNewTemplateMode(false); setNewTemplateName(""); }}>Cancel</button>
              <button className="cm-btn cm-btn-primary" onClick={handleCreateCharacter} disabled={!pickedTemplate}>
                Create Character →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Generate Story modal ── */}
      {showGenerateModal && (
        <div
          className="cm-modal-overlay"
          onClick={() => { setShowGenerateModal(false); setGenTheme(""); setSelectedCharIds([]); }}
        >
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="cm-modal-title">Generate Story</h2>

            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 6 }}>Theme</div>
              <input
                className="cm-input"
                style={{ width: "100%" }}
                placeholder="e.g. overcoming fear of the dark"
                value={genTheme}
                onChange={(e) => setGenTheme(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !isGenerating && genTheme.trim() && handleGenerate()}
                autoFocus
              />
            </div>

            {project.characters.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 6 }}>
                  Characters{" "}
                  <span style={{ color: "var(--text-4, var(--text-3))" }}>(select up to 2)</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {project.characters.map((c) => {
                    const tmpl = templateById[c.templateId];
                    const nameField = tmpl?.fields.find((f) => f.name.toLowerCase().includes("name"));
                    const charName = nameField ? ((c.values[nameField.id] as string) || "Unnamed") : "Character";
                    const checked = selectedCharIds.includes(c.id);
                    const maxReached = selectedCharIds.length >= 2 && !checked;
                    return (
                      <label
                        key={c.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          padding: "8px 12px",
                          borderRadius: "var(--r-xs)",
                          background: checked ? "var(--hi-bg)" : "var(--surface-2)",
                          border: `1px solid ${checked ? "var(--hi)" : "var(--border-mid)"}`,
                          cursor: maxReached ? "not-allowed" : "pointer",
                          opacity: maxReached ? 0.5 : 1,
                          transition: "border-color 0.12s, background 0.12s",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={maxReached}
                          onChange={() => {
                            setSelectedCharIds((prev) =>
                              prev.includes(c.id) ? prev.filter((id) => id !== c.id) : [...prev, c.id]
                            );
                          }}
                          style={{ accentColor: "var(--hi)" }}
                        />
                        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{charName}</span>
                        {tmpl && project.templates.length > 1 && (
                          <span style={{ fontSize: 11, color: "var(--text-3)" }}>{tmpl.name}</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="cm-modal-actions">
              <button
                className="cm-btn"
                onClick={() => { setShowGenerateModal(false); setGenTheme(""); setSelectedCharIds([]); }}
              >
                Cancel
              </button>
              <button
                className="cm-btn cm-btn-primary"
                onClick={handleGenerate}
                disabled={!genTheme.trim() || isGenerating}
              >
                {isGenerating ? "Queuing…" : "Generate →"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
