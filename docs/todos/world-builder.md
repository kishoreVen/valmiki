# Task: World Builder

## What

Add a **World** to each project — a living document that captures the evolving state of the story universe. A world has:

1. **Description** — freeform text the user writes directly. The name, geography, tone, history, rules of magic/technology, etc.
2. **Rules** — structured canon facts (e.g. "no electricity", "animals can speak only to children"). Users add/edit/delete these directly.
3. **Characters** — the project's characters are displayed here as first-class members of the world (read-only list; editing still happens in the character editor).
4. **Stories** — generated story runs associated with this world (read-only list linking to the pipeline inspector).

The world evolves automatically via two **compaction prompts** that the user can trigger:
- **Character compaction** — reads all character values and updates the world description/rules to reflect what the characters collectively imply about the world.
- **Story compaction** — reads generated story outputs and updates the world description/rules to reflect what happened and what was learned.

The user can always edit the world description and rules directly, before or after compaction.

---

## Why

Right now each character and each story is an island. There's no shared context that says "these characters live in the same world with these rules." The world object fixes this in two ways: it gives the LLM a grounding document injected into every character suggestion and every story generation call, and it accumulates knowledge over time so each new story builds on the last.

---

## Data model

Add to `Project` in `character-store.ts`:

```ts
interface WorldRule {
  id: string;
  text: string;               // e.g. "No electricity exists in this world"
  source: "user" | "character_compaction" | "story_compaction";
  createdAt: string;
}

interface World {
  description: string;        // freeform, user-editable
  rules: WorldRule[];
  lastCharacterCompactionAt: string | null;
  lastStoryCompactionAt: string | null;
}

// Project gets:
world: World;  // initialized to { description: "", rules: [], ... } on project create
```

Rules have no confirmed/unconfirmed state — every rule is live canon once it exists. The user removes rules they don't want.

---

## UI

`ProjectPage` becomes the World view. Layout:

**Top section — World**
- Editable textarea for the world description (auto-saves on blur).
- Rule list: each rule shown as a chip with an inline delete (×) button.
- "+ Add Rule" inline text input to add a user rule.
- Two action buttons:
  - "Update from Characters" — triggers character compaction.
  - "Update from Stories" — triggers story compaction (disabled if no stories exist).
- Both buttons show a loading spinner while the LLM call is in flight; on completion, the world description and rules update in place.

**Middle section — Characters**
- Existing character grid (unchanged from current `ProjectPage` layout).

**Bottom section — Stories**
- Flat list of story runs associated with this project (run id, timestamp, status).
- Each row links to `/runs/:runId` in the pipeline inspector.
- "Generate Story" button → opens a modal to pick characters + theme and calls `POST /api/generate`.

---

## Engine / server integration

### Inject world into character suggestions (existing endpoint, extend)

Extend `CharacterSuggestRequest` in `server.py`:

```python
class CharacterSuggestRequest(BaseModel):
    message: str
    character_values: dict
    template_fields: list
    world_description: str = ""
    world_rules: list[str] = []  # rule texts only
```

Prepend to the system prompt:

```
World context:
{world_description}

Canon rules (treat as hard constraints):
{newline-joined world_rules}
```

### Character compaction — new endpoint

```
POST /api/projects/compact/characters
```

Body:
```python
class CharacterCompactionRequest(BaseModel):
    world_description: str
    world_rules: list[str]
    characters: list[dict]   # [{name, field_name: value, ...}] — all characters in the project
```

The LLM prompt instructs Claude to:
- Read the existing world description and rules
- Read all character data
- Return an updated world description and a new/updated rule list that captures what the characters collectively imply

Response:
```json
{
  "description": "updated world description",
  "rules": ["rule text 1", "rule text 2"]
}
```

The frontend replaces the world description and replaces all `source: "character_compaction"` rules with the new ones (user rules are preserved).

### Story compaction — new endpoint

```
POST /api/projects/compact/stories
```

Body:
```python
class StoryCompactionRequest(BaseModel):
    world_description: str
    world_rules: list[str]
    stories: list[dict]   # [{title, concept, script_summary}] — story outputs
```

Same response shape as character compaction. The frontend replaces `source: "story_compaction"` rules; user rules and character-compaction rules are preserved.

### Compaction prompts (LLM instructions)

**Character compaction system prompt:**
```
You are maintaining a world bible for a story universe.

Current world description:
{world_description}

Current canon rules:
{world_rules}

Here are all the characters that exist in this world:
{characters_json}

Based on what these characters collectively imply — their backgrounds, goals, weaknesses, and traits — update the world description and extract canon rules.

Return ONLY valid JSON: {"description": "...", "rules": ["...", "..."]}
Keep the description concise (2-4 sentences). Rules should be specific, falsifiable facts.
Preserve any rules that are still supported. Add new ones you observe. Do not invent rules not evidenced by the characters.
```

**Story compaction system prompt:**
```
You are maintaining a world bible for a story universe.

Current world description:
{world_description}

Current canon rules:
{world_rules}

Here are the stories that have been told in this world:
{stories_json}

Based on what happened in these stories — events, resolutions, character actions — update the world description and extract new canon rules about what is established as true.

Return ONLY valid JSON: {"description": "...", "rules": ["...", "..."]}
```

---

## Done when

- [ ] `World` is persisted in localStorage alongside the project (initialized on project create)
- [ ] User can edit the world description directly; changes save on blur
- [ ] User can add and delete rules directly
- [ ] "Update from Characters" calls the character compaction endpoint and updates the world in place
- [ ] "Update from Stories" calls the story compaction endpoint and updates the world in place (disabled when no stories)
- [ ] Character-compaction and story-compaction rules are tagged by source; user rules survive compaction
- [ ] World description and rules are injected into `POST /api/characters/suggest` (character chat respects the world)
- [ ] World description and rules are forwarded in `POST /api/generate` (story generation respects the world)
- [ ] Story runs linked to the project are listed in the World view
- [ ] "Generate Story" modal on the World view lets the user pick characters + theme and fires generation

---

## Open questions

- How do we associate story run IDs with a project? Currently `POST /api/generate` returns a `run_id` but doesn't store it on the project. The frontend should persist `run_id` in the project's world after a successful generate call.
- Should compaction run automatically on character save / story complete, or only on explicit user trigger? (Start with explicit to avoid surprise API calls.)
- If the world description is empty, should compaction seed it from scratch or require the user to write a starting description?
