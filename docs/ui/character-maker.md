# Character Maker UI

## Overview

A flexible, project-scoped character creation system. The current engine assumes a fixed character shape (name, age, gender, backstory, goals, weaknesses). This feature moves the source of truth for character structure into user-defined templates, making the engine a consumer rather than a dictator of character schema.

---

## Problem Being Solved

`CharacterConfig` in `story_engine/elements/character.py` hard-codes every field a character can have. New character types require engine changes. The goal is to invert this: users define what fields matter for their project, and the engine works with whatever shape emerges.

---

## User Flow

### 1. Projects

The top-level concept is a **Project** — a container that is not specific to characters. A project holds:
- A character template (the schema)
- A roster of characters built from that template

Users land on a project list screen and can create or open a project.

### 2. Template Builder

Before creating characters, the user defines a **character template** for the project. The template is a list of fields, each with:
- Field name (e.g. "Name", "Archetype", "Fighting Style")
- Field type: `text` | `textarea` | `select` (with options) | `image` | `audio`
- Whether the field is required
- A display hint (shown on the character card)

The template also declares which fields map to the three special media slots:
- **Portrait** — the image shown on the character card
- **3D model** — optional spatial representation
- **Voice** — audio sample or voice config

Template setup is done once per project. It can be edited later, with a warning if existing characters have fields that no longer exist in the template.

### 3. Character Roster

Once a template exists, the user sees the character roster for the project. Each character is shown as a card. From here the user can:
- Add a new character
- Open an existing character

### 4. Character Editor

The main editing surface. Three-panel layout:

```
+-------------------------+----------------------------+
|                         |                            |
|   LLM Conversation      |    Character Card          |
|   (left panel)          |    (center, prominent)     |
|                         |                            |
|   Chat interface where  |  Portrait / 3D / Voice     |
|   user describes what   |  rendered per template     |
|   they want to change.  |  config                    |
|                         |                            |
|   LLM reads the current |  Field values shown as     |
|   character state and   |  a clean card below the    |
|   proposes edits.       |  media                     |
|                         |                            |
|   User can accept or    +----------------------------+
|   reject field-level    |                            |
|   suggestions.          |   Field Edit Panel         |
|                         |   (bottom-right, optional) |
+-------------------------+                            |
                          |  Direct field editing for  |
                          |  power users who don't     |
                          |  want to go through chat   |
                          +----------------------------+
```

The LLM conversation panel:
- Has context of the full character (all field values) and the template schema
- Understands what each field represents
- Suggests structured edits (not free text) — it proposes new values for specific fields
- Suggested changes are applied **in-place** on the character card as a live preview — the card reflects the proposed state immediately so the user can see the effect before committing
- The user confirms or reverts each suggestion; reverting snaps the card back to the previous value
- Clicking any field value on the character card (or any message in the conversation) **quotes it** into the chat input, letting the user refer to it directly in their next message

See [ui-style-guide.md](ui-style-guide.md) for typography, color, spacing, and animation conventions.

---

## Component Map

```
ProjectListPage
  ProjectCard
  NewProjectModal

ProjectPage
  TemplateBuilder         (first-time setup or edit mode)
    FieldDefinitionRow
    MediaSlotPicker
  CharacterRoster
    CharacterCard (roster variant)
    AddCharacterButton

CharacterEditorPage
  ConversationPanel
    MessageBubble
    FieldSuggestionCard   (LLM proposes: field name + new value + accept/revert; triggers in-place card preview)
    QuotedContext         (inline quote block shown in chat input when user clicks a field or message)
    ChatInput
  CharacterCard (editor variant)
    MediaDisplay          (portrait / 3d / audio, per template config)
    FieldValueList
  FieldEditPanel          (direct edit, collapsible)
    FieldInput            (renders correct input type per template field definition)
```

---

## Data Model (Frontend)

```ts
// The schema for a project — defined once by the user
type FieldDefinition = {
  id: string;
  name: string;
  type: "text" | "textarea" | "select" | "image" | "audio";
  options?: string[];       // for select type
  required: boolean;
  mediaSlot?: "portrait" | "model3d" | "voice";
};

type CharacterTemplate = {
  fields: FieldDefinition[];
};

// A single character — values are a free-form map keyed by field id
type Character = {
  id: string;
  projectId: string;
  values: Record<string, string | string[]>;   // field id -> value
  createdAt: string;
  updatedAt: string;
};

type Project = {
  id: string;
  name: string;
  template: CharacterTemplate;
  characters: Character[];
};

// LLM suggestions arrive as a list of proposed field changes
type FieldSuggestion = {
  fieldId: string;
  currentValue: string | string[];
  proposedValue: string | string[];
  rationale: string;
};
```

---

## Engine Compatibility Notes

The current `CharacterConfig` dataclass will not be changed as part of this UI feature. The UI operates on its own data model. When the engine needs to consume a character built in the new UI, a mapping layer will translate the free-form field values into whatever the engine currently expects, or the engine will be updated separately (tracked in `docs/engine/`).

The template system's `media slot` concept maps to the engine's `Capability` enum:
- `portrait` -> `Capability.IMAGE_GEN`
- `voice` -> `Capability.AUDIO_GEN`

---

## Open Questions

- Should projects support multiple templates (e.g. heroes vs NPCs use different schemas)?
- Does the LLM conversation persist across sessions, or reset each time the character is opened?
- For 3D model slot: are we generating or uploading? Generation pipeline is not yet defined. **Note: any 3D visualization will use Three.js.**
