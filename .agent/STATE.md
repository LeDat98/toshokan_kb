# STATE — as of 2026-07-11 (end of session 3)

**Phase:** P1 complete ✅ — the librarian really walks the library, live in the browser.
Next: P2 (ingest pipeline + question flywheel + card catalog).

## What exists and works
- P0 backend + P1 navigator (commits `b7b0dfc`, `33c030c`): config, Gemini client with neutral
  tool-calling (D-016) + thought-signature round-trip (D-017), fs LibraryStore, seed library
  (6 books / 16 pages), `agent/` (tools with hard budgets, navigator, answerer, orchestrator),
  `library/views.py`. CLI `ask --trace`, `rebuild-views`, `seed`, `init`.
- **API** (`libkb/api/`): `POST /api/query` SSE (walk on a worker thread, D-018),
  `GET /api/library/tree|node|book|page`, `/api/health`. App = `libkb.api.main:app`.
- **Frontend wired to real backend**: Ask streams live walks (trace panel fills room-by-room
  as Gemini walks, backtracks with "why", FOUND/NOT_FOUND terminal, real citations);
  Library lazy-loads real tree → shelves → books → TOC → page. Ingest + Observatory still on
  `mock.ts` (they're P2/P3 features).
- Verified live end-to-end through the vite proxy: lookup → FOUND+citation; off-library →
  honest NOT_FOUND with backtracks. 39 unit tests green (LLM-free), ruff clean, web builds clean.

## How to run
- `./dev.sh` (Git Bash) — starts API on :8000 + vite on :5173, open http://localhost:5173.
  dev.sh now auto-detects the API and launches both. `./dev.sh check` = tests+lint+build.

## Next actions (P2 — ingest + flywheel)
1. `ingest/parse.py` (md/pdf/url) + `split.py` (structure-aware, 400–1200 tok/page).
2. `ingest/classify.py` + confidence gate → `_uncatalogued`; `ingest/questions.py` (vi+en).
3. `catalog/` (SQLite: questions+embeddings, `search.lookup`); `ingest/pipeline.py`.
4. `agent/tools.ask_librarian` (catalog shortcut) + lookup entry-point in orchestrator.
5. `POST /api/ingest` SSE stepper; wire Ingest UI tab + review queue off mock.

## Watch out
- `web/src/api.ts` ↔ `libkb/api/events.py` are one contract — change both together (D-018).
- Answer is one SSE event (not token-streamed) — the walk is the live part.
- Everything Windows: `.venv\Scripts\...`, cp932 console (CLI forces UTF-8), no uv.
- `-m llm` tests + any `libkb ask`/API query spend real tokens — run deliberately.