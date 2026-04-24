const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// Stories
export const listStories = () => request<{ stories: Story[] }>("/stories");
export const getStory = (id: string) => request<StoryData>(`/stories/${id}`);

// Templates
export const listTemplates = () =>
  request<{ templates: TemplateMeta[] }>("/templates");
export const getTemplate = (path: string) =>
  request<TemplateDetail>(`/templates/${path}`);
export const saveTemplate = (path: string, source: string) =>
  request(`/templates/${path}`, {
    method: "PUT",
    body: JSON.stringify({ source }),
  });
export const previewTemplate = (path: string, context: Record<string, string>) =>
  request<TemplatePreview>(`/templates/${path}/preview`, {
    method: "POST",
    body: JSON.stringify({ context }),
  });

// Runs / Prompt Inspection
export const listRuns = () => request<{ runs: RunSummary[] }>("/runs");
export const getRunPrompts = (runId: string) =>
  request<RunPrompts>(`/runs/${runId}/prompts`);
export const getRunStagePrompts = (runId: string, stage: string) =>
  request<StagePrompts>(`/runs/${runId}/prompts/${stage}`);

// Pipeline
export const triggerGenerate = (params: GenerateParams) =>
  request<{ run_id: string; status: string }>("/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });

// Health
export const health = () => request<{ status: string }>("/health");

// Types
export interface Story {
  id: string;
  title: string;
  created_at: number;
  status: string;
}

export interface StoryData {
  title: string;
  pitch?: string;
  stages?: Record<string, unknown>;
  pages?: unknown[];
  [key: string]: unknown;
}

export interface TemplateMeta {
  name: string;
  type: string;
  description: string;
  path: string;
}

export interface TemplateDetail {
  name: string;
  source: string;
  variables: string[];
}

export interface TemplatePreview {
  base_instruction: string;
  sections: Record<string, string>;
  critical_requirements: string[];
  requirements: string[];
  flat: string;
}

export interface RunSummary {
  run_id: string;
  started_at: number;
  status: string;
  stages: string[];
}

export interface PromptEntry {
  timestamp: number;
  stage: string;
  step: string;
  template_name: string;
  system_prompt: string;
  user_prompt: string;
  response_text: string;
  model_interface: string;
  usage?: { input_tokens: number; output_tokens: number };
  cost?: number;
  iteration: number;
}

export interface StagePrompts {
  stage: string;
  status: string;
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  entries: PromptEntry[];
}

export interface RunPrompts {
  run_id: string;
  started_at: number;
  status: string;
  stages: Record<string, StagePrompts>;
}

export interface GenerateParams {
  theme: string;
  characters?: string[];
  age_range?: string;
  config_name?: string;
  location_hint?: string;
}
