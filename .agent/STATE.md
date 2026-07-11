# STATE — as of 2026-07-12 (session 4)

**Phase:** P1 ✅ + P2a (import) ✅ — the librarian walks BOTH the seed library and a real
imported retail corpus. Next: P2b (document/PDF ingest with LLM placement + confidence gate),
then P2c (question flywheel + card catalog).

## New this session — P2a import (docs/INGEST.md, D-019/D-020)
- Ingest reframed as ONE pipeline (survey → DraftTree(provided/missing) → resolve gaps → commit).
  `libkb/ingest/`: models (DraftTree), frontmatter, survey (folder→tree, depth rule), resolve
  (shelf strategies single/priority/auto-LLM), importer (get-or-create commit, idempotent).
- `libkb import <folder> --domain X --shelves single|priority|auto`. 8 LLM-free tests.
- **Imported the real retail corpus live**: 12 books / 92 pages; `--shelves auto` had Gemini group
  them into 3 discriminative shelves. Verified a retail `ask` walks Retail▸…▸KPI Dictionary▸
  Inventory Turnover and answers with a real citation.
- Retail content is PRIVATE → `library/domains/retail/` gitignored (D-020); source folder already
  gitignored. Only the AI seed stays in git.

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

## Next actions (P2b — document ingest, then P2c)
1. `ingest/parse.py` (pdf via pymupdf4llm, html/url via trafilatura) → markdown.
2. `ingest/split.py` (structure-aware on headings; LLM page-splitting when unstructured).
3. `ingest/classify.py` — top-down placement vs the live tree (create-if-missing), confidence
   = min over levels, gate → `_uncatalogued`. Reuse the DraftTree + commit from P2a.
4. `POST /api/ingest` SSE stepper; wire Ingest UI tab + review queue off mock.
5. P2c: `ingest/questions.py` (vi+en) + `catalog/` (SQLite embeddings, search.lookup) +
   `agent/tools.ask_librarian` + lookup shortcut in orchestrator.

## Watch out
- `web/src/api.ts` ↔ `libkb/api/events.py` are one contract — change both together (D-018).
- Answer is one SSE event (not token-streamed) — the walk is the live part.
- Everything Windows: `.venv\Scripts\...`, cp932 console (CLI forces UTF-8), no uv.
- `-m llm` tests + any `libkb ask`/API query spend real tokens — run deliberately.
- `recompute_stats` rewrites every `_meta.json` (updated_at) → git churn across `library/`; after
  a local import, `git checkout -- library/` before committing so only code/docs commit (D-020).
- Retail domain is on disk but gitignored; to re-import fresh: delete `library/domains/retail/`
  then `libkb import ... --domain Retail --shelves auto`.
- P2b document ingest should REUSE `ingest/models.DraftTree` + `ingest/importer.commit` — the
  classifier just fills the domain/shelf/page-split slots the raw doc leaves missing.