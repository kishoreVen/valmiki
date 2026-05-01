"""
Valmiki local development server.

Provides REST API for:
- Story snapshot management (local JSON files)
- Template browsing, editing, and preview
- Pipeline run inspection (prompt/response logs)
- Pipeline triggering

Run: uvicorn server:app --reload --port 8642
"""

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Valmiki Story Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path("output")
TEMPLATES_DIR = Path("story_engine/production/prompts")


# ── Story Snapshots ──────────────────────────────────────────────────────────


@app.get("/api/stories")
def list_stories():
    """List all story snapshots from output/."""
    stories = []
    if not OUTPUT_DIR.exists():
        return {"stories": []}

    for run_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        story_file = run_dir / "story.json"
        if story_file.exists():
            data = json.loads(story_file.read_text())
            stories.append({
                "id": run_dir.name,
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at", 0),
                "status": data.get("status", "unknown"),
            })
        else:
            # Run dir without story.json — might just have prompts
            stories.append({
                "id": run_dir.name,
                "title": "Run " + run_dir.name,
                "created_at": run_dir.stat().st_mtime,
                "status": "in_progress",
            })
    return {"stories": stories}


@app.get("/api/stories/{story_id}")
def get_story(story_id: str):
    """Read a story snapshot."""
    story_file = OUTPUT_DIR / story_id / "story.json"
    if not story_file.exists():
        raise HTTPException(404, f"Story {story_id} not found")
    return json.loads(story_file.read_text())


class StorySaveRequest(BaseModel):
    data: dict


@app.post("/api/stories/{story_id}")
def save_story(story_id: str, req: StorySaveRequest):
    """Save/update a story snapshot."""
    run_dir = OUTPUT_DIR / story_id
    run_dir.mkdir(parents=True, exist_ok=True)
    story_file = run_dir / "story.json"
    story_file.write_text(json.dumps(req.data, indent=2))
    return {"status": "saved", "id": story_id}


@app.get("/api/stories/{story_id}/stage/{stage}")
def get_story_stage(story_id: str, stage: str):
    """Get stage-specific data for a story."""
    story_file = OUTPUT_DIR / story_id / "story.json"
    if not story_file.exists():
        raise HTTPException(404, f"Story {story_id} not found")
    data = json.loads(story_file.read_text())
    stage_data = data.get("stages", {}).get(stage)
    if stage_data is None:
        raise HTTPException(404, f"Stage {stage} not found in story {story_id}")
    return stage_data


# ── Template Management ──────────────────────────────────────────────────────


@app.get("/api/templates")
def list_templates():
    """List all .j2 templates with metadata."""
    from story_engine.production.template_registry import TemplateRegistry
    registry = TemplateRegistry.get_instance(TEMPLATES_DIR)
    return {"templates": registry.list_templates()}


@app.get("/api/templates/{path:path}")
def get_template(path: str):
    """Read template source and metadata."""
    from story_engine.production.template_registry import TemplateRegistry
    registry = TemplateRegistry.get_instance(TEMPLATES_DIR)
    try:
        source = registry.get_template_source(path)
        variables = registry.get_template_variables(path)
        return {
            "name": path,
            "source": source,
            "variables": variables,
        }
    except FileNotFoundError:
        raise HTTPException(404, f"Template {path} not found")


class TemplateSaveRequest(BaseModel):
    source: str


@app.put("/api/templates/{path:path}")
def save_template(path: str, req: TemplateSaveRequest):
    """Save edited template source."""
    from story_engine.production.template_registry import TemplateRegistry
    registry = TemplateRegistry.get_instance(TEMPLATES_DIR)
    registry.save_template(path, req.source)
    return {"status": "saved", "name": path}


class TemplatePreviewRequest(BaseModel):
    context: dict


@app.post("/api/templates/{path:path}/preview")
def preview_template(path: str, req: TemplatePreviewRequest):
    """Render a template with sample context and return the result."""
    from story_engine.production.template_registry import TemplateRegistry
    registry = TemplateRegistry.get_instance(TEMPLATES_DIR)
    try:
        result = registry.render(path, **req.context)
        return {
            "base_instruction": result.base_instruction,
            "sections": result.sections,
            "critical_requirements": result.critical_requirements,
            "requirements": result.requirements,
            "flat": result.to_flat_prompt(),
        }
    except Exception as e:
        raise HTTPException(400, f"Template render error: {e}")


# ── Run / Prompt Inspection ──────────────────────────────────────────────────


@app.get("/api/runs")
def list_runs():
    """List all pipeline runs that have prompt logs."""
    runs = []
    if not OUTPUT_DIR.exists():
        return {"runs": []}

    for run_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        prompts_file = run_dir / "prompts.json"
        if prompts_file.exists():
            data = json.loads(prompts_file.read_text())
            runs.append({
                "run_id": data.get("run_id", run_dir.name),
                "started_at": data.get("started_at", 0),
                "status": data.get("status", "unknown"),
                "stages": list(data.get("stages", {}).keys()),
            })
    return {"runs": runs}


@app.get("/api/runs/{run_id}/prompts")
def get_run_prompts(run_id: str):
    """Get all prompt/response logs for a run."""
    prompts_file = OUTPUT_DIR / run_id / "prompts.json"
    if not prompts_file.exists():
        raise HTTPException(404, f"No prompt logs for run {run_id}")
    return json.loads(prompts_file.read_text())


@app.get("/api/runs/{run_id}/prompts/{stage}")
def get_run_stage_prompts(run_id: str, stage: str):
    """Get prompt/response logs for a specific stage."""
    prompts_file = OUTPUT_DIR / run_id / "prompts.json"
    if not prompts_file.exists():
        raise HTTPException(404, f"No prompt logs for run {run_id}")
    data = json.loads(prompts_file.read_text())
    stage_data = data.get("stages", {}).get(stage)
    if stage_data is None:
        raise HTTPException(404, f"Stage {stage} not found in run {run_id}")
    return stage_data


# ── Pipeline Control ─────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    theme: str
    characters: list = []
    age_range: str = "4-5"
    config_name: str = "v0"
    location_hint: Optional[str] = None


@app.post("/api/generate")
def trigger_generate(req: GenerateRequest):
    """Trigger a story generation pipeline run.

    This is a placeholder — actual integration with the story engine
    will be connected when the engine is runnable with dependencies.
    """
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save the request as a manifest
    manifest = {
        "run_id": run_id,
        "request": req.model_dump(),
        "created_at": time.time(),
        "status": "queued",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return {"run_id": run_id, "status": "queued"}


# ── Character Maker ──────────────────────────────────────────────────────────


class CharacterSuggestRequest(BaseModel):
    message: str
    character_values: dict
    template_fields: list


@app.post("/api/characters/suggest")
def character_suggest(req: CharacterSuggestRequest):
    """Get Claude suggestions for character field edits.

    Returns a conversational message plus a list of structured field suggestions
    that the UI can apply as previews and allow the user to accept/reject.
    """
    import os
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    editable_fields = [
        f for f in req.template_fields if f.get("type") not in ("image", "audio")
    ]

    fields_context = "\n".join(
        f"- id={f['id']} | name={f['name']} | type={f['type']}"
        + (f" | options={f['options']}" if f.get("options") else "")
        + f" | current={req.character_values.get(f['id'], '[empty]')!r}"
        for f in editable_fields
    )

    system_prompt = f"""You are a creative writing assistant helping to develop a character.

The character template has these fields (with their current values):
{fields_context}

When the user asks for changes or ideas, respond in EXACTLY this format — no deviations:

CONTENT: <one or two sentence conversational reply>
SUGGESTIONS: <a JSON array of suggestion objects, or [] if none>

Each suggestion object must have:
  - "field_id": the exact id string from the field list above
  - "proposed_value": the suggested new value (string)
  - "rationale": a brief one-sentence explanation

Example response:
CONTENT: Here's a name and backstory that fits your description.
SUGGESTIONS: [{{"field_id": "abc123", "proposed_value": "Aria Voss", "rationale": "Strong, memorable, fits the mercenary tone."}}]

Only suggest fields that exist in the field list. Keep proposed values concise and creative."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": req.message}],
    )

    text = response.content[0].text.strip()

    content = ""
    suggestions = []

    if "CONTENT:" in text and "SUGGESTIONS:" in text:
        try:
            content_part, suggestions_part = text.split("SUGGESTIONS:", 1)
            content = content_part.replace("CONTENT:", "").strip()
            raw = json.loads(suggestions_part.strip())
            field_ids = {f["id"] for f in req.template_fields}
            suggestions = [
                {
                    "fieldId": s["field_id"],
                    "currentValue": req.character_values.get(s["field_id"], ""),
                    "proposedValue": s["proposed_value"],
                    "rationale": s.get("rationale", ""),
                }
                for s in raw
                if isinstance(s, dict) and s.get("field_id") in field_ids
            ]
        except (ValueError, json.JSONDecodeError, KeyError):
            content = text
    else:
        content = text

    return {"content": content, "suggestions": suggestions}


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "templates_dir": str(TEMPLATES_DIR),
        "output_dir": str(OUTPUT_DIR),
        "templates_count": len(list(TEMPLATES_DIR.rglob("*.j2"))) if TEMPLATES_DIR.exists() else 0,
    }
