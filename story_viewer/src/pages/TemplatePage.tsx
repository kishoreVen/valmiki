import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  updateTemplate,
  createCharacter,
  deleteCharacter,
  type Project,
  type CharacterTemplate,
  type FieldDefinition,
  type FieldKind,
  type TextVariant,
} from "../lib/character-store";
import "../character.css";

// ── Field Definition Row ──────────────────────────────────────────────────────

function FieldRow({
  field,
  onUpdate,
  onDelete,
}: {
  field: FieldDefinition;
  onUpdate: (f: FieldDefinition) => void;
  onDelete: () => void;
}) {
  return (
    <div className="cm-field-row">
      <input
        className="cm-input"
        style={{ flex: 1 }}
        value={field.name}
        onChange={(e) => onUpdate({ ...field, name: e.target.value })}
        placeholder="Field name (e.g. Name, Backstory, Portrait)"
      />

      {/* Kind: text / image / 3d */}
      <select
        className="cm-select"
        style={{ width: 90 }}
        value={field.kind}
        onChange={(e) => {
          const kind = e.target.value as FieldKind;
          onUpdate({
            ...field,
            kind,
            textVariant: kind === "text" ? field.textVariant ?? "string" : undefined,
          });
        }}
      >
        <option value="text">Text</option>
        <option value="image">Image</option>
        <option value="3d">3D</option>
      </select>

      {/* Text variant — only when kind is text */}
      {field.kind === "text" && (
        <select
          className="cm-select"
          style={{ width: 120 }}
          value={field.textVariant ?? "string"}
          onChange={(e) =>
            onUpdate({ ...field, textVariant: e.target.value as TextVariant })
          }
        >
          <option value="string">String</option>
          <option value="list">List</option>
          <option value="dictionary">Dictionary</option>
        </select>
      )}

      <label className="cm-checkbox-label">
        <input
          type="checkbox"
          checked={field.required}
          onChange={(e) => onUpdate({ ...field, required: e.target.checked })}
        />
        Required
      </label>

      <button
        className="cm-btn cm-btn-danger-ghost"
        style={{ height: 32, padding: "0 10px", fontSize: 12 }}
        onClick={onDelete}
      >
        Remove
      </button>
    </div>
  );
}

// ── Template Page ─────────────────────────────────────────────────────────────

export function TemplatePage() {
  const { projectId, templateId } = useParams<{
    projectId: string;
    templateId: string;
  }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [template, setTemplate] = useState<CharacterTemplate | null>(null);
  const [localFields, setLocalFields] = useState<FieldDefinition[]>([]);
  const [editingFields, setEditingFields] = useState(false);

  useEffect(() => {
    const p = getProject(projectId!);
    if (!p) {
      navigate("/characters");
      return;
    }
    const t = p.templates.find((x) => x.id === templateId);
    if (!t) {
      navigate(`/characters/${projectId}`);
      return;
    }
    setProject(p);
    setTemplate(t);
    setLocalFields(t.fields);
    if (t.fields.length === 0) setEditingFields(true);
  }, [projectId, templateId]);

  if (!project || !template) return null;

  const characters = project.characters.filter(
    (c) => c.templateId === templateId
  );
  const portraitField = template.fields.find((f) => f.kind === "image");
  const nameField = template.fields.find(
    (f) =>
      f.name.toLowerCase() === "name" ||
      f.name.toLowerCase() === "character name"
  );

  function uid() {
    return typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function addField() {
    setLocalFields((prev) => [
      ...prev,
      { id: uid(), name: "", kind: "text", textVariant: "string", required: false },
    ]);
  }

  function updateField(idx: number, field: FieldDefinition) {
    setLocalFields((prev) => prev.map((f, i) => (i === idx ? field : f)));
  }

  function removeField(idx: number) {
    setLocalFields((prev) => prev.filter((_, i) => i !== idx));
  }

  function saveTemplate() {
    const updated = { ...template!, fields: localFields };
    updateTemplate(project!.id, updated);
    setTemplate(updated);
    setEditingFields(false);
  }

  function cancelEdit() {
    setLocalFields(template!.fields);
    setEditingFields(false);
  }

  function handleAddCharacter() {
    const char = createCharacter(project!.id, template!.id);
    navigate(`/characters/${project!.id}/t/${template!.id}/c/${char.id}`);
  }

  function handleDeleteCharacter(e: React.MouseEvent, charId: string) {
    e.stopPropagation();
    if (!confirm("Delete this character?")) return;
    deleteCharacter(project!.id, charId);
    setProject(getProject(project!.id)!);
  }

  const kindLabel = (f: FieldDefinition) => {
    if (f.kind === "image") return "image";
    if (f.kind === "3d") return "3d";
    return f.textVariant ?? "string";
  };

  return (
    <div className="cm-root">
      <div className="cm-inner">
        {/* Breadcrumb */}
        <div className="cm-page-header">
          <div className="cm-breadcrumb">
            <button
              className="cm-btn cm-btn-ghost"
              onClick={() => navigate("/characters")}
            >
              ← Projects
            </button>
            <span className="cm-breadcrumb-sep">/</span>
            <button
              className="cm-btn cm-btn-ghost"
              onClick={() => navigate(`/characters/${projectId}`)}
            >
              {project.name}
            </button>
            <span className="cm-breadcrumb-sep">/</span>
            <span className="cm-breadcrumb-current">{template.name}</span>
          </div>
          <div className="cm-header-actions">
            {!editingFields && template.fields.length > 0 && (
              <button
                className="cm-btn"
                onClick={() => {
                  setLocalFields(template.fields);
                  setEditingFields(true);
                }}
              >
                Edit Fields
              </button>
            )}
            {!editingFields && template.fields.length > 0 && (
              <button
                className="cm-btn cm-btn-primary"
                onClick={handleAddCharacter}
              >
                + New Character
              </button>
            )}
          </div>
        </div>

        {/* Fields section */}
        <div className="cm-section">
          <div className="cm-section-header">
            <span className="cm-section-label">Fields</span>
            {editingFields && (
              <div style={{ display: "flex", gap: 8 }}>
                {template.fields.length > 0 && (
                  <button className="cm-btn" onClick={cancelEdit}>
                    Cancel
                  </button>
                )}
                <button
                  className="cm-btn cm-btn-primary"
                  onClick={saveTemplate}
                  disabled={
                    localFields.length === 0 ||
                    localFields.some((f) => !f.name.trim())
                  }
                >
                  Save Fields
                </button>
              </div>
            )}
          </div>

          {editingFields ? (
            <>
              {localFields.length === 0 && (
                <p
                  style={{
                    fontSize: 13,
                    color: "var(--text-2)",
                    marginBottom: 16,
                  }}
                >
                  Add fields to define what data each character will carry.
                </p>
              )}
              <div className="cm-field-list">
                {localFields.map((f, i) => (
                  <FieldRow
                    key={f.id}
                    field={f}
                    onUpdate={(updated) => updateField(i, updated)}
                    onDelete={() => removeField(i)}
                  />
                ))}
              </div>
              <button className="cm-btn" style={{ marginTop: 8 }} onClick={addField}>
                + Add Field
              </button>
              {localFields.some((f) => !f.name.trim()) && (
                <p style={{ marginTop: 8, fontSize: 12, color: "var(--error)" }}>
                  All fields must have a name.
                </p>
              )}
            </>
          ) : template.fields.length === 0 ? (
            <div className="cm-empty">
              <div className="cm-empty-icon">⊡</div>
              <p className="cm-empty-title">No fields defined</p>
              <p className="cm-empty-desc">
                Fields define the structure of every character in this template.
              </p>
              <button
                className="cm-btn cm-btn-primary"
                onClick={() => setEditingFields(true)}
              >
                Add Fields
              </button>
            </div>
          ) : (
            <div className="cm-field-chips">
              {template.fields.map((f) => (
                <span key={f.id} className="cm-field-chip">
                  <span
                    className={`cm-field-chip-kind cm-field-chip-kind-${f.kind}`}
                  >
                    {kindLabel(f)}
                  </span>
                  {f.name}
                  {f.required && (
                    <span className="cm-field-chip-req">*</span>
                  )}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Character Roster */}
        {!editingFields && template.fields.length > 0 && (
          <div className="cm-section">
            <div className="cm-section-header">
              <span className="cm-section-label">
                Characters ({characters.length})
              </span>
            </div>

            {characters.length === 0 ? (
              <div className="cm-empty">
                <div className="cm-empty-icon">✦</div>
                <p className="cm-empty-title">No characters yet</p>
                <p className="cm-empty-desc">
                  Create your first character using the {template.name} template.
                </p>
                <button
                  className="cm-btn cm-btn-primary"
                  onClick={handleAddCharacter}
                >
                  Create first character
                </button>
              </div>
            ) : (
              <div className="cm-roster-grid">
                {characters.map((c) => {
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
                          `/characters/${project.id}/t/${template.id}/c/${c.id}`
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
        )}
      </div>
    </div>
  );
}
