# valmiki

AI-assisted story engine with a character maker, model router, and quality control pipeline.

---

## Requirements

- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js 18+ and npm
- Python 3.11+

---

## Setup

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd valmiki
```

### 2. Install Python dependencies

```bash
uv sync --extra dev
```

This creates `.venv/`, installs the `valmiki` package in editable mode, and pulls all runtime and dev dependencies (FastAPI, Uvicorn, Anthropic SDK, OpenAI, Gemini, Pillow, pytest, ruff, etc.) in one step.

### 4. Set up environment variables

```bash
cp .env.example .env
```

Then edit `.env` and fill in the keys you need:

| Key | Required for |
|-----|-------------|
| `ANTHROPIC_API_KEY` | Character maker chat, Claude-based story generation |
| `OPENAI_API_KEY` | OpenAI model routing |
| `GEMINI_API_KEY` | Gemini model routing |
| `ELEVENLABS_API_KEY` | TTS / SFX generation |
| `RUNWARE_API_KEY` | Image generation via Runware |
| `TOGETHER_API_KEY` | Together AI model routing |

At minimum you need `ANTHROPIC_API_KEY` to use the character maker.

### 5. Install frontend dependencies

```bash
cd story_viewer
npm install
cd ..
```

---

## Running

### Option A — everything at once (recommended)

```bash
./deploy.sh
```

This starts both servers and keeps them running together. Press `Ctrl+C` to stop both.

- Backend API: `http://localhost:8642`
- Frontend: `http://localhost:5173`

### Option B — run separately

**Backend:**

```bash
source .venv/bin/activate   # or: .venv/bin/uvicorn directly
uvicorn server:app --reload --port 8642
```

**Frontend:**

```bash
cd story_viewer
npm run dev
```

> **WSL users:** open `http://localhost:5173` in your Windows browser — port forwarding is automatic.

---

## Docs and tribal knowledge

The `docs/` directory is where we capture design intent, architecture decisions, and the "why" behind large features — the kind of context that doesn't belong in code comments but is essential for anyone (human or agent) picking up the work cold.

Each major feature gets its own doc that covers the problem being solved, the data model, the component map, open questions, and any non-obvious constraints. Before building something significant, write the doc first. Before reading a file, read the doc for that area first.

**`docs/todos/`** holds individual task files — one file per task, named for what it does (e.g. `world-builder.md`, `character-export.md`). Each task is written at a level of specificity that an agent can pick it up and execute it without needing to ask clarifying questions: what it is, why it exists, what done looks like, and any constraints or open questions. When a task is complete, delete or archive the file. When new work is discovered mid-task, create a new file for it rather than appending to the current one.

---

## Project structure

```
valmiki/
├── server.py              # FastAPI dev server
├── deploy.sh              # One-command startup script
├── pyproject.toml         # Python package config
├── .env.example           # Environment variable template
├── story_engine/          # Core Python package
│   ├── elements/          # Data models (Character, etc.)
│   ├── interfaces/        # Shared interfaces
│   ├── lib/               # Pipeline, model router, QC, utils
│   └── production/        # Director, illustrator, scripter, etc.
├── story_viewer/          # React + Vite frontend
│   └── src/
│       ├── pages/         # Route-level page components
│       ├── lib/           # character-store, API client
│       └── character.css  # Character maker design system
├── docs/                  # Design specs, tribal knowledge, agent todo
│   ├── ui/
│   │   ├── character-maker.md
│   │   └── ui-style-guide.md
│   ├── engine/            # Engine architecture and design notes
│   └── todos/             # One file per pending task (agent-ready)
└── output/                # Pipeline run outputs (gitignored)
```
