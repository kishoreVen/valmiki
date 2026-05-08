import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  updateCharacter,
  type Project,
  type Character,
  type CharacterTemplate,
  type FieldDefinition,
  type FieldValue,
  type FieldSuggestion,
  type World,
} from "../lib/character-store";
import "../character.css";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  suggestions?: FieldSuggestion[];
  resolved?: Record<string, "accepted" | "rejected">;
}

// ── API ───────────────────────────────────────────────────────────────────────

async function fetchSuggestions(
  message: string,
  character: Character,
  fields: FieldDefinition[],
  world?: World
): Promise<{ content: string; suggestions: FieldSuggestion[] }> {
  const res = await fetch("/api/characters/suggest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      character_values: character.values,
      template_fields: fields
        .filter((f) => f.kind === "text")
        .map((f) => ({
          id: f.id,
          name: f.name,
          type: f.textVariant ?? "string",
          options: undefined,
        })),
      world_description: world?.description ?? "",
      world_rules: world?.rules.map((r) => r.text) ?? [],
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Field display helper ──────────────────────────────────────────────────────

function valueToDisplay(value: FieldValue, field: FieldDefinition): string {
  if (!value) return "";
  if (field.kind === "image" || field.kind === "3d")
    return typeof value === "string" ? value : "";
  if (field.textVariant === "list") {
    return Array.isArray(value) ? value.filter(Boolean).join(", ") : "";
  }
  if (field.textVariant === "dictionary") {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value as Record<string, string>)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" · ");
    }
    return "";
  }
  return typeof value === "string" ? value : "";
}

// ── List Field Input ──────────────────────────────────────────────────────────

function ListInput({
  value,
  onChange,
}: {
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const list = Array.isArray(value) ? value : [];

  return (
    <div className="cm-list-input">
      {list.map((item, i) => (
        <div key={i} className="cm-list-input-row">
          <input
            className="cm-input"
            style={{ flex: 1 }}
            value={item}
            onChange={(e) => {
              const next = [...list];
              next[i] = e.target.value;
              onChange(next);
            }}
            placeholder="Item…"
          />
          <button
            className="cm-btn cm-btn-ghost"
            style={{ width: 32, padding: 0, fontSize: 16 }}
            onClick={() => onChange(list.filter((_, idx) => idx !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        className="cm-btn"
        style={{ height: 28, fontSize: 12, padding: "0 10px", marginTop: 4 }}
        onClick={() => onChange([...list, ""])}
      >
        + Add Item
      </button>
    </div>
  );
}

// ── Dictionary Field Input ────────────────────────────────────────────────────

function DictInput({
  value,
  onChange,
}: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const dict =
    value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const entries = Object.entries(dict);

  function updateKey(oldKey: string, newKey: string) {
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(dict)) {
      next[k === oldKey ? newKey : k] = v;
    }
    onChange(next);
  }

  function addEntry() {
    let key = "key";
    let i = 1;
    while (dict[key] !== undefined) key = `key${i++}`;
    onChange({ ...dict, [key]: "" });
  }

  return (
    <div className="cm-dict-input">
      {entries.map(([k, v]) => (
        <div key={k} className="cm-dict-input-row">
          <input
            className="cm-input"
            style={{ width: 110 }}
            value={k}
            onChange={(e) => updateKey(k, e.target.value)}
            placeholder="key"
          />
          <span className="cm-dict-sep">:</span>
          <input
            className="cm-input"
            style={{ flex: 1 }}
            value={v}
            onChange={(e) => onChange({ ...dict, [k]: e.target.value })}
            placeholder="value"
          />
          <button
            className="cm-btn cm-btn-ghost"
            style={{ width: 32, padding: 0, fontSize: 16 }}
            onClick={() => {
              const next = { ...dict };
              delete next[k];
              onChange(next);
            }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        className="cm-btn"
        style={{ height: 28, fontSize: 12, padding: "0 10px", marginTop: 4 }}
        onClick={addEntry}
      >
        + Add Entry
      </button>
    </div>
  );
}

// ── Generic Field Input ───────────────────────────────────────────────────────

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FieldDefinition;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
}) {
  if (field.kind === "image" || field.kind === "3d") {
    return (
      <input
        className="cm-input"
        style={{ width: "100%" }}
        type="url"
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder="https://…"
      />
    );
  }

  if (field.textVariant === "list") {
    return (
      <ListInput
        value={(value as string[]) ?? []}
        onChange={onChange as (v: string[]) => void}
      />
    );
  }

  if (field.textVariant === "dictionary") {
    return (
      <DictInput
        value={(value as Record<string, string>) ?? {}}
        onChange={onChange as (v: Record<string, string>) => void}
      />
    );
  }

  // default: string
  return (
    <textarea
      className="cm-input"
      style={{ width: "100%", minHeight: 56, resize: "vertical" }}
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={`Enter ${field.name.toLowerCase()}…`}
    />
  );
}

// ── Suggestion Card ───────────────────────────────────────────────────────────

function SuggestionCard({
  suggestion,
  field,
  status,
  onAccept,
  onReject,
}: {
  suggestion: FieldSuggestion;
  field: FieldDefinition | undefined;
  status: "accepted" | "rejected" | undefined;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <div
      className={`cm-suggestion-card ${
        status === "accepted"
          ? "cm-accepted"
          : status === "rejected"
            ? "cm-rejected"
            : ""
      }`}
    >
      <div className="cm-suggestion-header">
        <span className="cm-suggestion-field-pill">
          {field?.name ?? suggestion.fieldId}
        </span>
      </div>
      <div className="cm-suggestion-body">
        {suggestion.currentValue && (
          <div className="cm-suggestion-value-row">
            <span className="cm-suggestion-value-label">Current</span>
            <span className="cm-suggestion-value">{suggestion.currentValue}</span>
          </div>
        )}
        <div className="cm-suggestion-value-row">
          <span className="cm-suggestion-value-label">Proposed</span>
          <span className="cm-suggestion-value cm-proposed">
            {suggestion.proposedValue}
          </span>
        </div>
        {suggestion.rationale && (
          <span className="cm-suggestion-rationale">{suggestion.rationale}</span>
        )}
      </div>
      {status ? (
        <div className={`cm-suggestion-status ${status}`}>
          {status === "accepted" ? "✓ Accepted" : "↩ Reverted"}
        </div>
      ) : (
        <div className="cm-suggestion-actions">
          <button
            className="cm-btn cm-btn-primary"
            style={{ height: 28, fontSize: 12, padding: "0 10px" }}
            onClick={onAccept}
          >
            Accept
          </button>
          <button
            className="cm-btn"
            style={{ height: 28, fontSize: 12, padding: "0 10px" }}
            onClick={onReject}
          >
            Revert
          </button>
        </div>
      )}
    </div>
  );
}

// ── Character Card ────────────────────────────────────────────────────────────

function CharacterCard({
  character,
  template,
  pendingSuggestions,
  onUpdate,
  flashMap,
}: {
  character: Character;
  template: CharacterTemplate;
  pendingSuggestions: FieldSuggestion[];
  onUpdate: (fieldId: string, value: FieldValue) => void;
  flashMap: Record<string, "accept" | "reject">;
}) {
  const portraitField = template.fields.find((f) => f.kind === "image");
  const nameField = template.fields.find(
    (f) => f.name.toLowerCase() === "name" || f.name.toLowerCase() === "character name"
  );
  const charName = nameField
    ? ((character.values[nameField.id] as string) || "Unnamed")
    : "New Character";
  const portraitUrl = portraitField
    ? (character.values[portraitField.id] as string) || null
    : null;

  const pendingFieldIds = new Set(pendingSuggestions.map((s) => s.fieldId));

  return (
    <div className="cm-character-card">
      <div className="cm-char-portrait">
        {portraitUrl ? (
          <img src={portraitUrl} alt={charName} />
        ) : (
          <div className="cm-char-portrait-placeholder">
            {charName[0]?.toUpperCase() ?? "?"}
          </div>
        )}
      </div>

      <div className="cm-char-fields">
        {template.fields.map((f) => {
          const flash = flashMap[f.id];
          return (
            <div
              key={f.id}
              className={`cm-char-field ${
                flash === "accept"
                  ? "cm-char-field-flash-accept"
                  : flash === "reject"
                    ? "cm-char-field-flash-reject"
                    : ""
              }`}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span className="cm-char-field-name">{f.name}</span>
                {pendingFieldIds.has(f.id) && (
                  <span style={{ fontSize: 9, background: "var(--hi-bg)", color: "var(--hi)", padding: "1px 5px", borderRadius: 4 }}>
                    pending
                  </span>
                )}
                {f.kind !== "text" && (
                  <span style={{ fontSize: 9, background: "var(--surface-3, var(--surface-2))", color: "var(--text-3)", padding: "1px 5px", borderRadius: 4 }}>
                    {f.kind}
                  </span>
                )}
              </div>
              <FieldInput
                field={f}
                value={character.values[f.id] ?? (f.textVariant === "list" ? [] : f.textVariant === "dictionary" ? {} : "")}
                onChange={(v) => onUpdate(f.id, v)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Character Editor Page ─────────────────────────────────────────────────────

export function CharacterEditorPage() {
  const { projectId, templateId, characterId } = useParams<{
    projectId: string;
    templateId: string;
    characterId: string;
  }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [template, setTemplate] = useState<CharacterTemplate | null>(null);
  const [character, setCharacter] = useState<Character | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [quotedContext, setQuotedContext] = useState<string | null>(null);
  const [pendingSuggestions, setPendingSuggestions] = useState<FieldSuggestion[]>([]);
  const [flashMap, setFlashMap] = useState<Record<string, "accept" | "reject">>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    const c = p.characters.find((x) => x.id === characterId);
    if (!c) {
      navigate(`/characters/${projectId}/t/${templateId}`);
      return;
    }
    setProject(p);
    setTemplate(t);
    setCharacter(c);
  }, [projectId, templateId, characterId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const flash = useCallback((fieldId: string, type: "accept" | "reject") => {
    setFlashMap((m) => ({ ...m, [fieldId]: type }));
    setTimeout(() => {
      setFlashMap((m) => {
        const next = { ...m };
        delete next[fieldId];
        return next;
      });
    }, 400);
  }, []);

  function updateCharacterField(fieldId: string, value: FieldValue) {
    if (!character) return;
    const updated: Character = {
      ...character,
      values: { ...character.values, [fieldId]: value },
    };
    setCharacter(updated);
    updateCharacter(updated);
  }

  function handleAcceptSuggestion(msgId: string, s: FieldSuggestion) {
    if (!character || !template) return;
    const field = template.fields.find((f) => f.id === s.fieldId);
    let value: FieldValue = s.proposedValue;
    if (field?.textVariant === "list" || field?.textVariant === "dictionary") {
      try { value = JSON.parse(s.proposedValue); } catch { /* keep as string */ }
    }
    const updated: Character = {
      ...character,
      values: { ...character.values, [s.fieldId]: value },
    };
    setCharacter(updated);
    updateCharacter(updated);
    setPendingSuggestions((prev) => prev.filter((x) => x.fieldId !== s.fieldId));
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId
          ? { ...m, resolved: { ...(m.resolved ?? {}), [s.fieldId]: "accepted" } }
          : m
      )
    );
    flash(s.fieldId, "accept");
  }

  function handleRejectSuggestion(msgId: string, s: FieldSuggestion) {
    setPendingSuggestions((prev) => prev.filter((x) => x.fieldId !== s.fieldId));
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId
          ? { ...m, resolved: { ...(m.resolved ?? {}), [s.fieldId]: "rejected" } }
          : m
      )
    );
    flash(s.fieldId, "reject");
  }

  function handleQuote(text: string) {
    setQuotedContext(text);
    inputRef.current?.focus();
  }

  async function handleSend() {
    if (!input.trim() || isLoading || !character || !template) return;

    const userText = quotedContext
      ? `> ${quotedContext}\n\n${input.trim()}`
      : input.trim();

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: userText };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setQuotedContext(null);
    setIsLoading(true);

    try {
      const { content, suggestions } = await fetchSuggestions(
        userText,
        character,
        template.fields,
        project.world
      );
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content,
        suggestions,
        resolved: {},
      };
      setMessages((prev) => [...prev, assistantMsg]);
      if (suggestions.length > 0) {
        setPendingSuggestions((prev) => {
          const existing = new Set(prev.map((s) => s.fieldId));
          return [...prev, ...suggestions.filter((s) => !existing.has(s.fieldId))];
        });
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            "Couldn't reach the server. Make sure it's running and ANTHROPIC_API_KEY is set.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (!project || !template || !character) return null;

  const nameField = template.fields.find(
    (f) =>
      f.name.toLowerCase() === "name" ||
      f.name.toLowerCase() === "character name"
  );
  const charName = nameField
    ? ((character.values[nameField.id] as string) || "New Character")
    : "New Character";

  return (
    <div className="cm-root" style={{ paddingTop: 0, paddingBottom: 0, minHeight: "unset", marginTop: "-1.5rem", marginBottom: "-1.5rem" }}>
      {/* Topbar */}
      <div className="cm-editor-topbar">
        <div className="cm-breadcrumb">
          <button
            className="cm-btn cm-btn-ghost"
            style={{ height: 30, fontSize: 12 }}
            onClick={() =>
              navigate(`/characters/${projectId}/t/${templateId}`)
            }
          >
            ← {template.name}
          </button>
          <span className="cm-breadcrumb-sep">/</span>
          <span className="cm-editor-topbar-name">{charName}</span>
        </div>
        <span className="cm-editor-topbar-meta">
          {template.fields.length} field{template.fields.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* 3-panel layout */}
      <div className="cm-editor-layout">
        {/* Left: Conversation */}
        <div className="cm-conversation-panel">
          <div className="cm-panel-header">
            <span className="cm-panel-title">Character Chat</span>
            <span className="cm-panel-badge">claude-sonnet-4-6</span>
          </div>

          <div className="cm-message-list">
            {messages.length === 0 && (
              <p
                style={{
                  color: "var(--text-3)",
                  fontSize: 13,
                  textAlign: "center",
                  marginTop: 24,
                  lineHeight: 1.6,
                  padding: "0 8px",
                }}
              >
                Describe what you want. I'll suggest edits to specific fields
                that you can accept or revert.
              </p>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`cm-message cm-message-${msg.role}`}>
                <div
                  className="cm-message-bubble"
                  onClick={() =>
                    msg.role === "assistant" && handleQuote(msg.content)
                  }
                  title={
                    msg.role === "assistant" ? "Click to quote" : undefined
                  }
                >
                  {msg.content}
                </div>
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="cm-suggestions">
                    {msg.suggestions.map((s) => (
                      <SuggestionCard
                        key={s.fieldId}
                        suggestion={s}
                        field={template.fields.find((f) => f.id === s.fieldId)}
                        status={msg.resolved?.[s.fieldId]}
                        onAccept={() => handleAcceptSuggestion(msg.id, s)}
                        onReject={() => handleRejectSuggestion(msg.id, s)}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="cm-message cm-message-assistant">
                <div className="cm-message-thinking">
                  <div className="cm-thinking-dot" />
                  <div className="cm-thinking-dot" />
                  <div className="cm-thinking-dot" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat input */}
          <div className="cm-chat-input-area">
            {quotedContext && (
              <div className="cm-quoted-context">
                <span className="cm-quoted-text">"{quotedContext}"</span>
                <button
                  className="cm-quoted-remove"
                  onClick={() => setQuotedContext(null)}
                >
                  ×
                </button>
              </div>
            )}
            <div className="cm-chat-row">
              <textarea
                ref={inputRef}
                className="cm-chat-input"
                placeholder="Describe what you want…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
              />
              <button
                className="cm-chat-send"
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                title="Send"
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                  <path
                    d="M1.5 7.5L13.5 2L9 13L7.5 9L1.5 7.5Z"
                    fill="white"
                    stroke="white"
                    strokeWidth="0.8"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Right: Character card (directly editable) */}
        <div className="cm-right-panel">
          <div className="cm-character-card-panel">
            <CharacterCard
              character={character}
              template={template}
              pendingSuggestions={pendingSuggestions}
              onUpdate={updateCharacterField}
              flashMap={flashMap}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
