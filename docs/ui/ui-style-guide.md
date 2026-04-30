# UI Style Guide

Applies to all React UI in this project. Light, Apple-inspired design language. When in doubt, use more whitespace and less decoration.

---

## Theme

- Background: white (`#ffffff`) or off-white (`#f9f9f9`) for page surfaces
- Panel fills: subtle warm grey (`#f2f2f2` / `#efefef`)
- Text primary: near-black (`#1a1a1a`)
- Text secondary: medium grey (`#6e6e73`) — Apple's secondary label color
- Error: soft red (`#ff3b30`)
- Success: soft green (`#34c759`)

---

## Typography

- Font stack: `"SF Pro Display", "SF Pro Text", system-ui, -apple-system, sans-serif`
- Hierarchy:
  - Page title: 22px, weight 600
  - Section heading: 15px, weight 600, letter-spacing 0.02em, uppercase
  - Body: 14px, weight 400, line-height 1.5
  - Caption / label: 12px, weight 400, color secondary
- No decorative fonts. No heavy weights except intentional emphasis.

---

## Colors

Single accent color throughout. Do not use multiple accent colors on the same surface.

| Token            | Value        | Use                                  |
|------------------|--------------|--------------------------------------|
| `--accent`       | `#0071e3`    | Buttons, active states, links        |
| `--accent-soft`  | `#e8f1fb`    | Hover fills, selected backgrounds    |
| `--border`       | `#d1d1d6`    | Borders, dividers                    |
| `--border-soft`  | `#e5e5ea`    | Subtle separators                    |
| `--surface`      | `#f2f2f7`    | Panel backgrounds                    |
| `--error`        | `#ff3b30`    | Error states only                    |
| `--success`      | `#34c759`    | Success / confirm flash              |

---

## Borders & Radius

- Border width: 1px, always `--border` or `--border-soft`
- Corner radius: 10px for cards and panels, 6px for inputs and small elements, 20px for pill buttons
- No drop shadows on flat surfaces. No harsh lines between content areas — use background color contrast instead.

---

## Shadows

Use sparingly. Only for elements that float above the page (modals, dropdowns, sticky panels).

```css
/* Floating panel */
box-shadow: 0 4px 24px rgba(0, 0, 0, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04);

/* Card hover lift */
box-shadow: 0 8px 28px rgba(0, 0, 0, 0.10), 0 2px 6px rgba(0, 0, 0, 0.05);
```

Never use colored shadows.

---

## Spacing

Base unit: 4px. All spacing is a multiple of 4.

| Token    | Value  | Use                              |
|----------|--------|----------------------------------|
| `xs`     | 4px    | Icon gaps, tight inline spacing  |
| `sm`     | 8px    | Between related elements         |
| `md`     | 16px   | Standard section padding         |
| `lg`     | 24px   | Between sections                 |
| `xl`     | 40px   | Page-level vertical rhythm       |

Generous padding inside cards and panels. Content should never feel cramped.

---

## Animations

All transitions should feel instant but smooth — never sluggish. Prefer ease-out curves.

| Event                        | Duration  | Curve      | Notes                                          |
|------------------------------|-----------|------------|------------------------------------------------|
| Page / view transition       | 150ms     | ease-out   | Fade + translateY(-6px -> 0)                   |
| Card entrance                | 200ms     | ease-out   | Fade + scale(0.97 -> 1.0)                      |
| Roster card hover lift       | 120ms     | ease-out   | translateY(-2px), shadow increase              |
| LLM suggestion arrival       | 180ms     | ease-out   | Slide in from left, staggered 40ms per card    |
| In-place field preview       | 120ms     | ease-in-out| Cross-fade or text morph on character card     |
| Accept suggestion flash      | 300ms     | ease-out   | Brief `--success` background, then fades       |
| Reject / revert flash        | 300ms     | ease-out   | Brief soft grey background, snaps to old value |
| Quote-to-input               | 150ms     | ease-out   | Quoted block slides into chat input with ring  |
| Modal open                   | 150ms     | ease-out   | Fade + scale(0.96 -> 1.0)                      |

Do not animate layout shifts (avoid animating `width`, `height`, or `margin`). Animate `transform` and `opacity` only.

---

## Buttons

- Primary: filled `--accent`, white text, 10px radius, 14px font weight 500
- Secondary: `--surface` fill, `--border` border, dark text
- Ghost: no fill, no border, `--accent` text — for low-emphasis actions
- Disabled: 40% opacity, no pointer events
- Min tap target: 36px height

---

## Inputs & Form Elements

- Border: 1px `--border`, radius 6px
- Focus ring: 2px `--accent` offset 1px (no outline replacement hacks)
- Placeholder color: `--border` (light grey, clearly non-content)
- Error state: border changes to `--error`, no icon required

---

## Chat / Conversation UI

- User messages: right-aligned, `--accent-soft` fill, 10px radius, 14px body
- LLM messages: left-aligned, white fill with `--border` border
- `FieldSuggestionCard`: distinct from regular message — pill-style field name label, proposed value block, accept/revert actions inline
- `QuotedContext`: indented block with left border in `--accent`, shown above the user's typed message in the input area
- No avatars required. Role is implied by alignment and fill.
