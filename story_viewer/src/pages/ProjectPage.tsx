import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  createTemplate,
  deleteTemplate,
  createCharacter,
  deleteCharacter,
  type Project,
  type CharacterTemplate,
} from "../lib/character-store";
import "../character.css";

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);

  // "New Template" modal
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState("");

  // "New Character" modal (template picker)
  const [showCharModal, setShowCharModal] = useState(false);
  const [pickedTemplate, setPickedTemplate] = useState<CharacterTemplate | null>(null);

  useEffect(() => {
    const p = getProject(projectId!);
    if (!p) {
      navigate("/characters");
      return;
    }
    setProject(p);
  }, [projectId]);

  if (!project) return null;

  // ── Template actions ──────────────────────────────────────────────────────

  function handleCreateTemplate() {
    if (!newTemplateName.trim()) return;
    const t = createTemplate(project!.id, newTemplateName.trim());
    setShowTemplateModal(false);
    setNewTemplateName("");
    navigate(`/characters/${project!.id}/t/${t.id}`);
  }

  function handleDeleteTemplate(e: React.MouseEvent, templateId: string) {
    e.stopPropagation();
    const t = project!.templates.find((x) => x.id === templateId);
    const charCount = project!.characters.filter(
      (c) => c.templateId === templateId
    ).length;
    if (
      !confirm(
        `Delete "${t?.name}"? This will also delete ${charCount} character${charCount !== 1 ? "s" : ""}.`
      )
    )
      return;
    deleteTemplate(project!.id, templateId);
    setProject(getProject(project!.id)!);
  }

  // ── Character actions ─────────────────────────────────────────────────────

  function openCharModal() {
    if (project!.templates.length === 1) {
      // Only one template — skip picker
      const char = createCharacter(project!.id, project!.templates[0].id);
      navigate(
        `/characters/${project!.id}/t/${project!.templates[0].id}/c/${char.id}`
      );
    } else {
      setPickedTemplate(null);
      setShowCharModal(true);
    }
  }

  function handleCreateCharacter() {
    if (!pickedTemplate) return;
    const char = createCharacter(project!.id, pickedTemplate.id);
    setShowCharModal(false);
    navigate(
      `/characters/${project!.id}/t/${pickedTemplate.id}/c/${char.id}`
    );
  }

  function handleDeleteCharacter(e: React.MouseEvent, charId: string, templateId: string) {
    e.stopPropagation();
    if (!confirm("Delete this character?")) return;
    deleteCharacter(project!.id, charId);
    setProject(getProject(project!.id)!);
    void templateId; // referenced for navigation but not needed here
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const hasTemplates = project.templates.length > 0;
  const templateById = Object.fromEntries(project.templates.map((t) => [t.id, t]));

  return (
    <div className="cm-root">
      <div className="cm-inner">
        {/* Header */}
        <div className="cm-page-header">
          <div className="cm-breadcrumb">
            <button
              className="cm-btn cm-btn-ghost"
              onClick={() => navigate("/characters")}
            >
              ← Projects
            </button>
            <span className="cm-breadcrumb-sep">/</span>
            <span className="cm-breadcrumb-current">{project.name}</span>
          </div>
          <div className="cm-header-actions">
            {hasTemplates && (
              <button
                className="cm-btn cm-btn-primary"
                onClick={openCharModal}
              >
                + New Character
              </button>
            )}
            <button
              className="cm-btn"
              onClick={() => setShowTemplateModal(true)}
            >
              New Template
            </button>
          </div>
        </div>

        {/* Templates section */}
        <div className="cm-section">
          <div className="cm-section-header">
            <span className="cm-section-label">
              Templates ({project.templates.length})
            </span>
          </div>

          {project.templates.length === 0 ? (
            <div className="cm-empty">
              <div className="cm-empty-icon">⊞</div>
              <p className="cm-empty-title">No templates yet</p>
              <p className="cm-empty-desc">
                A template defines the fields your characters will have — e.g.
                Hero, NPC, Villain.
              </p>
              <button
                className="cm-btn cm-btn-primary"
                onClick={() => setShowTemplateModal(true)}
              >
                Create first template
              </button>
            </div>
          ) : (
            <div className="cm-template-grid">
              {project.templates.map((t, i) => {
                const charCount = project.characters.filter(
                  (c) => c.templateId === t.id
                ).length;
                return (
                  <div
                    key={t.id}
                    className="cm-template-card"
                    style={{ animationDelay: `${i * 30}ms` }}
                    onClick={() =>
                      navigate(`/characters/${project.id}/t/${t.id}`)
                    }
                  >
                    <div className="cm-template-card-icon">
                      {t.name[0]?.toUpperCase()}
                    </div>
                    <div className="cm-template-card-name">{t.name}</div>
                    <div className="cm-template-card-meta">
                      {t.fields.length} field{t.fields.length !== 1 ? "s" : ""}{" "}
                      · {charCount} character{charCount !== 1 ? "s" : ""}
                    </div>
                    <button
                      className="cm-btn cm-btn-danger-ghost cm-project-delete"
                      onClick={(e) => handleDeleteTemplate(e, t.id)}
                    >
                      Delete
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Characters section */}
        {hasTemplates && (
          <div className="cm-section">
            <div className="cm-section-header">
              <span className="cm-section-label">
                Characters ({project.characters.length})
              </span>
            </div>

            {project.characters.length === 0 ? (
              <div className="cm-empty">
                <div className="cm-empty-icon">✦</div>
                <p className="cm-empty-title">No characters yet</p>
                <p className="cm-empty-desc">
                  Create your first character and fill out their details with
                  AI assistance.
                </p>
                <button
                  className="cm-btn cm-btn-primary"
                  onClick={openCharModal}
                >
                  Create first character
                </button>
              </div>
            ) : (
              <div className="cm-roster-grid">
                {project.characters.map((c) => {
                  const tmpl = templateById[c.templateId];
                  const nameField = tmpl?.fields.find(
                    (f) =>
                      f.name.toLowerCase() === "name" ||
                      f.name.toLowerCase() === "character name"
                  );
                  const portraitField = tmpl?.fields.find(
                    (f) => f.kind === "image"
                  );
                  const charName = nameField
                    ? ((c.values[nameField.id] as string) || "Unnamed")
                    : "Character";
                  const portraitUrl = portraitField
                    ? (c.values[portraitField.id] as string) || null
                    : null;

                  return (
                    <div
                      key={c.id}
                      className="cm-roster-card"
                      onClick={() =>
                        navigate(
                          `/characters/${project.id}/t/${c.templateId}/c/${c.id}`
                        )
                      }
                    >
                      <div className="cm-roster-portrait">
                        {portraitUrl ? (
                          <img src={portraitUrl} alt={charName} />
                        ) : (
                          <div className="cm-roster-portrait-placeholder">
                            {charName[0]?.toUpperCase() ?? "?"}
                          </div>
                        )}
                      </div>
                      <div className="cm-roster-name">{charName}</div>
                      {tmpl && project.templates.length > 1 && (
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--text-3)",
                            marginTop: 3,
                          }}
                        >
                          {tmpl.name}
                        </div>
                      )}
                      <button
                        className="cm-btn cm-btn-danger-ghost cm-roster-delete"
                        onClick={(e) =>
                          handleDeleteCharacter(e, c.id, c.templateId)
                        }
                      >
                        Delete
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* New Template modal */}
      {showTemplateModal && (
        <div
          className="cm-modal-overlay"
          onClick={() => {
            setShowTemplateModal(false);
            setNewTemplateName("");
          }}
        >
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="cm-modal-title">New Template</h2>
            <input
              className="cm-input"
              style={{ width: "100%" }}
              placeholder="e.g. Hero, NPC, Villain, Side Character"
              value={newTemplateName}
              onChange={(e) => setNewTemplateName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateTemplate()}
              autoFocus
            />
            <div className="cm-modal-actions">
              <button
                className="cm-btn"
                onClick={() => {
                  setShowTemplateModal(false);
                  setNewTemplateName("");
                }}
              >
                Cancel
              </button>
              <button
                className="cm-btn cm-btn-primary"
                onClick={handleCreateTemplate}
                disabled={!newTemplateName.trim()}
              >
                Create →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Character: template picker modal */}
      {showCharModal && (
        <div
          className="cm-modal-overlay"
          onClick={() => setShowCharModal(false)}
        >
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="cm-modal-title">Choose a Template</h2>
            <div
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
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
                    background:
                      pickedTemplate?.id === t.id
                        ? "var(--hi-bg)"
                        : "var(--surface-2)",
                    cursor: "pointer",
                    transition: "border-color 0.12s, background 0.12s",
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "var(--r-xs)",
                      background: "var(--hi-bg)",
                      color: "var(--hi)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 700,
                      fontSize: 14,
                      flexShrink: 0,
                    }}
                  >
                    {t.name[0]?.toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>
                      {t.name}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-2)" }}>
                      {t.fields.length} field{t.fields.length !== 1 ? "s" : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="cm-modal-actions">
              <button className="cm-btn" onClick={() => setShowCharModal(false)}>
                Cancel
              </button>
              <button
                className="cm-btn cm-btn-primary"
                onClick={handleCreateCharacter}
                disabled={!pickedTemplate}
              >
                Create Character →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
