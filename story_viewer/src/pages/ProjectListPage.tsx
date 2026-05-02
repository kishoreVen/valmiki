import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  listProjects,
  createProject,
  deleteProject,
  type Project,
} from "../lib/character-store";
import "../character.css";

export function ProjectListPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    setProjects(listProjects());
  }, []);

  function handleCreate() {
    if (!newName.trim()) return;
    const project = createProject(newName.trim());
    setShowModal(false);
    setNewName("");
    navigate(`/characters/${project.id}`);
  }

  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!confirm("Delete this project and all its characters?")) return;
    deleteProject(id);
    setProjects(listProjects());
  }

  return (
    <div className="cm-root">
      <div className="cm-inner">
        <div className="cm-page-header">
          <div className="cm-page-title-group">
            <h1 className="cm-page-title">Character Projects</h1>
            <p className="cm-page-subtitle">
              Define templates and build your cast, one project at a time.
            </p>
          </div>
          <button
            className="cm-btn cm-btn-primary"
            onClick={() => setShowModal(true)}
          >
            New Project
          </button>
        </div>

        {projects.length === 0 ? (
          <div className="cm-empty">
            <div className="cm-empty-icon">✦</div>
            <p className="cm-empty-title">No projects yet</p>
            <p className="cm-empty-desc">
              A project holds a character template and the roster built from it.
            </p>
            <button
              className="cm-btn cm-btn-primary"
              onClick={() => setShowModal(true)}
            >
              Create your first project
            </button>
          </div>
        ) : (
          <div className="cm-project-grid">
            {projects.map((p, i) => (
              <div
                key={p.id}
                className="cm-project-card"
                style={{ animationDelay: `${i * 30}ms` }}
                onClick={() => navigate(`/characters/${p.id}`)}
              >
                <div className="cm-project-card-dot">
                  {p.name[0]?.toUpperCase()}
                </div>
                <div className="cm-project-card-name">{p.name}</div>
                <div className="cm-project-card-meta">
                  {p.characters.length} character
                  {p.characters.length !== 1 ? "s" : ""} ·{" "}
                  {p.templates.length} template
                  {p.templates.length !== 1 ? "s" : ""}
                </div>
                <button
                  className="cm-btn cm-btn-danger-ghost cm-project-delete"
                  onClick={(e) => handleDelete(e, p.id)}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
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
            <h2 className="cm-modal-title">New Project</h2>
            <input
              className="cm-input"
              style={{ width: "100%" }}
              placeholder="e.g. Epic Fantasy, Sci-Fi Crew, Season 2 Cast"
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
