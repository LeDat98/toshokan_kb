# LibraryKB

AI knowledge base organized like a physical library: the AI **walks** domain → shelf → book →
TOC → page to answer, instead of one-shot vector similarity. Founding requirements: the AI is an
**active seeker**, and context loads **progressively** (never bulk-dump into the window).

## Session protocol — do this first
1. Read `.agent/STATE.md` (where we are, next actions, watch-outs).
2. Before any design change, check `.agent/DECISIONS.md` — it is append-only and settles debates.
3. End of session: rewrite `STATE.md`, append `JOURNAL.md`, tick `ROADMAP.md` boxes.

## Map
- `docs/SCORECARD.md` — **what the system actually does, measured.** Every number with its `n`, its
  regime and the command that produced it; what is NOT measured; the metric bugs that fooled us; the
  ranked backlog. **Rewrite it after every major change** — it is how a future version gets compared
  to this one honestly.
- `docs/ARCHITECTURE.md` — principles **P1–P10** (source of truth for *why*), phases P0–P4.
  Written in Vietnamese with Mermaid diagrams (D-015) — keep it that way when editing.
- `docs/FUNCTIONS.md` — module/function specs (source of truth for *what to build*).
- `docs/UI_DESIGN_BRIEF.md` — mockup context for Claude Design (UI source of truth).
- `.agent/CONVENTIONS.md` — coding conventions (uv, ruff, pydantic v2, prompt/store discipline).
- `libkb/` — backend package · `web/` — frontend (from P1) · `library/` — the knowledge content itself.

## Hard rules
- **Leaf pages are the single source of truth**; ancestor descriptions are regenerated views
  (`library/views.py`) — never hand-edit or incrementally patch them.
- Only `libkb/llm/client.py` imports `google.genai`. Prompts are files in `libkb/llm/prompts/`.
- Navigation budgets are enforced in `agent/tools.py` code, not prompts.
- Answers cite their walk path; no evidence ⇒ honest NOT_FOUND (never improvise).
- Never touch `.env` (contains `Gemini_API_Key`; Settings reads case-insensitively). Never commit it.
- Model IDs come from config, two tiers by measured difficulty (D-027): `gemini-3.5-flash` for
  navigation/answering, `gemini-3.1-flash-lite` for bulk question generation. No hardcoding elsewhere.

## Commands (venv + pip — no uv, see D-011)
- Setup: `python -m venv .venv` then `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- CLI: `.venv\Scripts\libkb.exe init|seed [--force]|ask "<q>" --trace|ingest <src>|eval`
- Tests: `.venv\Scripts\python.exe -m pytest -q` (unit, LLM-free) ·
  `... -m pytest tests/llm -m llm` (spends tokens — explicit only)
- Lint: `.venv\Scripts\python.exe -m ruff check --fix .` + `... -m ruff format .`
- API dev (P1): `.venv\Scripts\python.exe -m uvicorn libkb.api.main:app --reload` · Web: `cd web && npm run dev`

## Language
Durable artifacts (code/docs/commits) in English; converse with the user in Vietnamese;
**UI copy English-only (D-013)**. Generated questions stay vi+en (retrieval data, not UI).
