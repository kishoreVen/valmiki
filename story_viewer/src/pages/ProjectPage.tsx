import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  createTemplate,
  deleteTemplate,
  type Project,
} from "../lib/character-store";
import "../character.css";

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    const p = getProject(projectId!);
    if (!p) {
      navigate("/characters");
      return;
    }
    setProject(p);
  }, [projectId]);

  if (!project) return null;

  function handleCreate() {
    if (!newName.trim()) return;
    const t = createTemplate(project!.id, newName.trim());
    setShowModal(false);
    setNewName("");
    navigate(`/characters/${project!.id}/t/${t.id}`);
  }

  function handleDelete(e: React.MouseEvent, templateId: string) {
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

  return (
    <div className="cm-root">
      <div className="cm-inner">
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
          <button
            className="cm-btn cm-btn-primary"
            onClick={() => setShowModal(true)}
          >
            New Template
          </button>
        </div>

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
                A template defines the fields your characters will have. You can
                have multiple — e.g. Hero, NPC, Villain.
              </p>
              <button
                className="cm-btn cm-btn-primary"
                onClick={() => setShowModal(true)}
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
                      onClick={(e) => handleDelete(e, t.id)}
                    >
                      Delete
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {showModal && (
        <div
          className="cm-modal-overlay"
          onClick={() => {
            setShowModal(false);
            setNewName("");
          }}
        >
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="cm-modal-title">New Template</h2>
            <input
              className="cm-input"
              style={{ width: "100%" }}
              placeholder="e.g. Hero, NPC, Villain, Side Character"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <div className="cm-modal-actions">
              <button
                className="cm-btn"
                onClick={() => {
                  setShowModal(false);
                  setNewName("");
                }}
              >
                Cancel
              </button>
              <button
                className="cm-btn cm-btn-primary"
                onClick={handleCreate}
                disabled={!newName.trim()}
              >
                Create →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
