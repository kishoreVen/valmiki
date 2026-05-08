# Task: Connect Character UI to Story Engine

## What

Wire characters designed in the Character Maker UI into the story engine's generation pipeline. When a user triggers story generation, they select which characters from a project to include. Those characters are serialized from the UI's `Character.values` schema into the engine's `CharacterConfig` format and passed through `Manager.produce_story()` — so the generated story uses the user-defined characters instead of generating them from scratch.

World context (description + confirmed rules) is also forwarded so the engine respects established canon throughout the pipeline. Out of scope: character sketching/image generation from the UI portrait field (handled separately by `CharacterDesigner.sketch_character`).

---

## Why

The story engine's `Manager.produce_story()` already accepts `List[character.Character]` and passes them through every pipeline step — concept, outline, script, illustrations. But `POST /api/generate` never populates this list; `characters: list = []` is stored in the manifest and then ignored. The result is that every generated story invents its own characters from scratch, making the Character Maker UI completely disconnected from actual story output.

---

## Data model

### Serialization contract (frontend → server)

Add to `CharacterSuggestRequest` is not the right place — instead, extend `GenerateRequest` in `server.py`:

```python
class CharacterInput(BaseModel):
    identifier: str           # character.id from the UI
    name: str
    gender: str = ""
    age: int | None = None
    backstory: str = ""
    goals: list[str] = []
    weaknesses: list[str] = []
    visual_description: str = ""
    voice_description: str = ""

class GenerateRequest(BaseModel):
    theme: str
    characters: list[CharacterInput] = []   # replaces untyped list
    age_range: str = "4-5"
    config_name: str = "v0"
    location_hint: str | None = None
    world_description: str = ""
    world_rules: list[str] = []             # confirmed rule texts only
```

### Field name → CharacterConfig mapping

The UI stores character values by arbitrary field IDs. The frontend must resolve field names to engine slots before sending. Mapping (case-insensitive field name match):

| UI field name (contains) | `CharacterInput` slot |
|---|---|
| `name` | `name` |
| `gender` | `gender` |
| `age` | `age` (parse int) |
| `backstory` | `backstory` |
| `goal` | `goals` (list field) |
| `weakness` | `weaknesses` (list field) |
| `visual` | `visual_description` |
| `voice` | `voice_description` |

Fields that don't match any slot are ignored for now.

Add a helper in `character-store.ts` (or a new `character-serializer.ts`):

```ts
export function characterToEngineInput(
  character: Character,
  template: CharacterTemplate
): CharacterEngineInput {
  // CharacterEngineInput mirrors CharacterInput from server
}
```

### Frontend type

```ts
export interface CharacterEngineInput {
  identifier: string;
  name: string;
  gender: string;
  age: number | null;
  backstory: string;
  goals: string[];
  weaknesses: string[];
  visual_description: string;
  voice_description: string;
}
```

---

## UI

**Where**: `ProjectPage` — add a "Generate Story" section at the bottom (or a dedicated `GeneratePage` at `/characters/:projectId/generate`).

**Flow**:
1. User sees a list of characters in the project with checkboxes. Max 2 can be selected (engine enforces this limit).
2. A theme text input.
3. Optional age range selector (default: 4-5).
4. "Generate" button calls `POST /api/generate` with the serialized characters and world context.
5. On success, show the `run_id` with a link to `/runs/:runId` (the existing pipeline inspector).

**Edge cases**:
- If no characters exist, show a prompt to create one first.
- If a selected character is missing required slots (`name` is empty), show an inline warning before send.

---

## Engine / server integration

**`POST /api/generate` changes** (`server.py`):

1. Accept typed `CharacterInput` objects (typed `GenerateRequest` as above).
2. Convert each `CharacterInput` → `character.CharacterConfig`.
3. For each config, call `CharacterDesigner.flesh_out_character(config)` to expand sparse fields via LLM (only if `age` or `gender` is missing; otherwise use as-is).
4. Instantiate `character.Character(config)` for each.
5. Instantiate `Manager` and call `manager.produce_story(characters, theme)`.
6. Persist the resulting `ManagerSnapshot` to `output/{run_id}/story.json`.
7. Return `{"run_id": run_id, "status": "queued"}` immediately (run async in a background thread/task).

**World context injection** (extends `world-builder` task):

Prepend to the system prompt context passed to `Manager` (or inject via `ManagerConfig`):

```
World: {world_description}
Canon rules: {newline-joined world_rules}
```

This mirrors what `POST /api/characters/suggest` already does for the character chat, making both surfaces consistent.

**Request/response**:

```
POST /api/generate
{
  "theme": "overcoming fear of the dark",
  "characters": [
    {
      "identifier": "uuid-from-ui",
      "name": "Mira",
      "age": 6,
      "gender": "female",
      "backstory": "Grew up in a lighthouse, afraid of the sea at night.",
      "goals": ["conquer her fear", "protect her little brother"],
      "weaknesses": ["freezes when startled"],
      "visual_description": "Small girl, red coat, dark curly hair"
    }
  ],
  "age_range": "4-5",
  "world_description": "A coastal town where the sea glows at night.",
  "world_rules": ["No electricity exists in this world", "Animals can speak but only to children"]
}

→ 200 { "run_id": "run_1746123456_abc123", "status": "queued" }
```

---

## Done when

- [ ] `POST /api/generate` accepts typed `CharacterInput` objects and no longer ignores them
- [ ] Characters are converted to `character.CharacterConfig` and passed to `Manager.produce_story()`
- [ ] `characterToEngineInput()` helper correctly maps UI field names to engine slots
- [ ] `ProjectPage` (or `GeneratePage`) lets the user select up to 2 characters and a theme, then calls `POST /api/generate`
- [ ] Characters with an empty `name` field are flagged in the UI before submission
- [ ] Generated story JSON in `output/{run_id}/story.json` reflects the input characters (character names appear in concept/script output)
- [ ] World description and confirmed rules are forwarded in the generate request and injected into the engine prompt context
- [ ] Pipeline runs asynchronously; the UI immediately receives a `run_id` and can poll or navigate to the run inspector

---

## Open questions

- Should `flesh_out_character` be called for every character, or only when `age`/`gender` are missing? (Calling it always would let the LLM expand sparse inputs, but risks overwriting carefully crafted values.)
- The engine enforces a max of 2 characters. Should the UI hard-block >2, or let the server reject and surface an error?
- Does the `world_description`/`world_rules` belong in `ManagerConfig` or as direct args to `produce_story()`? The former is cleaner for the pipeline internals.
- Should generation be truly async (background task) or synchronous with a long timeout? The pipeline can take several minutes.
