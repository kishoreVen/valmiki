# Task: World Builder

## What

Add a **World** concept to the character maker. A project can have one world — a shared container that describes the setting all characters and stories inhabit.

A world has two layers:

1. **Description** — freeform text written by the user. The name, geography, history, tone, factions, rules of magic/technology — whatever the author wants to define explicitly.

2. **Inferred rules** — structured facts derived automatically by the LLM from the characters and stories already in the project. Things like: "characters don't appear to age", "the world seems to have no electricity", "all named villains have a connection to the founding event". These are surfaced as suggestions the user can confirm, edit, or dismiss. Confirmed rules become part of the world's canon and get injected into future LLM prompts as hard constraints.

---

## Why

Right now each character is an island. There's no shared context that says "these characters all live in the same world with these rules." The LLM generating character suggestions has no awareness of world constraints, so it can produce contradictory or off-tone suggestions. The world object fixes this by giving the LLM a grounding document it always reads before suggesting anything.

---

## Data model

Add to `Project` in `character-store.ts`:

```ts
interface WorldRule {
  id: string;
  text: string;               // e.g. "No electricity exists in this world"
  source: "user" | "inferred";
  confirmed: boolean;         // inferred rules start unconfirmed
  derivedFrom?: string[];     // character/story ids that surfaced this rule
}

interface World {
  description: string;        // freeform markdown
  rules: WorldRule[];
}

// Project gets:
world?: World;
```

---

## UI

Add a **World** tab or section to `ProjectPage`. Two panels:

- **Left / top**: Freeform description editor (textarea or simple markdown input).
- **Right / bottom**: Rule list. Confirmed rules shown as solid chips. Unconfirmed inferred rules shown as dashed chips with "Confirm / Dismiss" inline actions.

A "Infer rules" button triggers an LLM call that reads all character field values across all templates in the project and extracts implicit world rules, returning them as unconfirmed suggestions.

---

## Engine / server integration

**Extend existing endpoint** — when `POST /api/characters/suggest` is called, include world context in the system prompt so Claude's suggestions respect established canon.

Extend `CharacterSuggestRequest` in `server.py`:

```python
class CharacterSuggestRequest(BaseModel):
    message: str
    character_values: dict
    template_fields: list
    world_description: str = ""
    world_rules: list[str] = []  # confirmed rule texts only
```

Prepend to the system prompt:

```
The story world context:
{world_description}

Established rules (treat these as hard constraints):
{world_rules joined by newline}
```

**New endpoint** — infer rules from existing characters:

```
POST /api/projects/{project_id}/world/infer-rules
```

Body: all character values across all templates in the project.
Returns: list of `{ text, derivedFrom[] }` rule suggestions.
The frontend stores them as unconfirmed `WorldRule` objects.

---

## Done when

- [ ] `World` is persisted in localStorage alongside the project
- [ ] User can write and save a world description
- [ ] "Infer rules" call works and returns plausible rules given the existing characters
- [ ] Unconfirmed rules can be confirmed or dismissed
- [ ] Confirmed rules and world description are injected into character chat prompts
- [ ] World UI is reachable from `ProjectPage`

---

## Open questions

- Should world be per-project or shared across projects? (Assume per-project for now.)
- Do stories (future feature) also contribute to rule inference, or only characters?
- Should the inferred rules run automatically on character save, or only on explicit user request? (Start with explicit to avoid surprise API calls.)
