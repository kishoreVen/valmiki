export type FieldKind = "text" | "image" | "3d";
export type TextVariant = "string" | "list" | "dictionary";
export type FieldValue = string | string[] | Record<string, string>;

export interface FieldDefinition {
  id: string;
  name: string;
  kind: FieldKind;
  textVariant?: TextVariant; // only when kind === "text"
  required: boolean;
}

export interface CharacterTemplate {
  id: string;
  name: string;
  fields: FieldDefinition[];
}

export interface Character {
  id: string;
  projectId: string;
  templateId: string;
  values: Record<string, FieldValue>;
  createdAt: string;
  updatedAt: string;
}

export interface Project {
  id: string;
  name: string;
  templates: CharacterTemplate[];
  characters: Character[];
}

export interface FieldSuggestion {
  fieldId: string;
  currentValue: string;
  proposedValue: string;
  rationale: string;
}

const STORAGE_KEY = "valmiki_projects";

function uid(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/** Migrate old single-template format to multi-template format. */
function migrate(raw: unknown[]): Project[] {
  return (raw as any[]).map((p) => {
    if (p.template && !p.templates) {
      const legacyId = uid();
      const migratedTemplate: CharacterTemplate = {
        id: legacyId,
        name: "Default",
        fields: (p.template.fields ?? []).map((f: any) => ({
          id: f.id ?? uid(),
          name: f.name ?? "",
          kind: f.type === "image" ? "image" : f.type === "audio" ? "3d" : "text",
          textVariant: "string" as TextVariant,
          required: f.required ?? false,
        })),
      };
      return {
        id: p.id,
        name: p.name,
        templates: [migratedTemplate],
        characters: (p.characters ?? []).map((c: any) => ({
          ...c,
          templateId: c.templateId ?? legacyId,
        })),
      } satisfies Project;
    }
    return p as Project;
  });
}

function load(): Project[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return migrate(raw);
  } catch {
    return [];
  }
}

function persist(projects: Project[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
}

// ── Projects ──────────────────────────────────────────────────────────────────

export function listProjects(): Project[] {
  return load();
}

export function getProject(id: string): Project | undefined {
  return load().find((p) => p.id === id);
}

export function createProject(name: string): Project {
  const project: Project = { id: uid(), name, templates: [], characters: [] };
  const projects = load();
  projects.push(project);
  persist(projects);
  return project;
}

export function updateProject(project: Project): void {
  const projects = load();
  const idx = projects.findIndex((p) => p.id === project.id);
  if (idx !== -1) projects[idx] = project;
  persist(projects);
}

export function deleteProject(id: string): void {
  persist(load().filter((p) => p.id !== id));
}

// ── Templates ─────────────────────────────────────────────────────────────────

export function createTemplate(
  projectId: string,
  name: string
): CharacterTemplate {
  const projects = load();
  const project = projects.find((p) => p.id === projectId);
  if (!project) throw new Error("Project not found");
  const template: CharacterTemplate = { id: uid(), name, fields: [] };
  project.templates.push(template);
  persist(projects);
  return template;
}

export function updateTemplate(
  projectId: string,
  template: CharacterTemplate
): void {
  const projects = load();
  const project = projects.find((p) => p.id === projectId);
  if (!project) return;
  const idx = project.templates.findIndex((t) => t.id === template.id);
  if (idx !== -1) project.templates[idx] = template;
  persist(projects);
}

export function deleteTemplate(projectId: string, templateId: string): void {
  const projects = load();
  const project = projects.find((p) => p.id === projectId);
  if (!project) return;
  project.templates = project.templates.filter((t) => t.id !== templateId);
  project.characters = project.characters.filter(
    (c) => c.templateId !== templateId
  );
  persist(projects);
}

// ── Characters ────────────────────────────────────────────────────────────────

export function createCharacter(
  projectId: string,
  templateId: string
): Character {
  const projects = load();
  const project = projects.find((p) => p.id === projectId);
  if (!project) throw new Error("Project not found");
  const character: Character = {
    id: uid(),
    projectId,
    templateId,
    values: {},
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  project.characters.push(character);
  persist(projects);
  return character;
}

export function updateCharacter(character: Character): void {
  const projects = load();
  const project = projects.find((p) => p.id === character.projectId);
  if (!project) return;
  const idx = project.characters.findIndex((c) => c.id === character.id);
  if (idx !== -1) {
    project.characters[idx] = {
      ...character,
      updatedAt: new Date().toISOString(),
    };
  }
  persist(projects);
}

export function deleteCharacter(projectId: string, characterId: string): void {
  const projects = load();
  const project = projects.find((p) => p.id === projectId);
  if (!project) return;
  project.characters = project.characters.filter((c) => c.id !== characterId);
  persist(projects);
}
