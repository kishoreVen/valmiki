---
name: new-task
description: Use when the user asks to create a task, todo, or work item document. Creates a docs/todos/<task-name>.md file following the valmiki task spec format.
---

# Create Task Document

The user wants to capture a new task as an agent-ready spec in `docs/todos/`.

## Steps

1. Determine the task name from the user's request. Convert it to kebab-case for the filename (e.g. "character export" → `character-export`).

2. Gather everything you need to write a complete spec. If the user's request is vague, ask one focused question to clarify scope before writing.

3. Create `docs/todos/<task-name>.md` with the following sections. Include only sections that are relevant — omit sections that genuinely don't apply.

---

## Template

```markdown
# Task: <Title>

## What

One paragraph. What is being built, from the user's perspective. Be concrete about the scope — what's in and what's out.

---

## Why

One paragraph. Why does this matter? What breaks or degrades without it?

---

## Data model

What types/interfaces need to be added or changed? Show TypeScript for frontend changes, Python for backend changes. Be specific — show field names and types, not just descriptions.

---

## UI

Which page(s) are affected? What components need to be added or changed? Describe layout, interactions, and any edge cases. Reference existing component patterns (e.g. `.cm-card`, `.cm-btn`) where relevant.

---

## Engine / server integration

What API endpoints are needed? Show the request/response shape. What does the LLM prompt look like if one is involved?

---

## Done when

- [ ] Checkbox list of concrete, testable acceptance criteria.
- [ ] Each item should be specific enough that an agent can verify it without asking.

---

## Open questions

- Unresolved decisions that a human should answer before or during implementation.
- If there are none, omit this section.
```

---

## Rules

- Write at the level of specificity where an agent can pick up the task cold and execute without asking clarifying questions.
- Don't pad sections. A short, accurate section is better than a long vague one.
- Omit the "Engine / server integration" section if the task is purely frontend.
- Omit the "Data model" section only if there are truly no type changes.
- The Done checklist is required — never omit it.
