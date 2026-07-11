# STATE — as of 2026-07-12 (session 5)

**Phase:** P1 ✅ + P2a (import) ✅ + P2b (document ingest) ✅. Next: P2c (question flywheel +
card catalog + ask_librarian), then P3 (classifier/synthesis/eval), P4 (maintenance).

## New this session — P2b document ingest (docs/INGEST.md, D-021)
- `ingest/parse.py` (md/txt/pdf[pymupdf4llm]/html+url[trafilatura], lazy deps), `split.py`
  (heading split + size fallback), `classify.py` (LLM top-down placement vs live tree,
  reconciled, confidence), `pipeline.py` (parse→split→classify→file; gate→_uncatalogued;
  list_uncatalogued + approve_placement). `libkb ingest <file|url> [--gate]`.
- API: `POST /api/ingest` (multipart file / url / text, SSE stepper) + `POST /api/import`
  (folder path, SSE) + `GET /api/ingest/review` + `POST /api/ingest/review/{id}/approve`.
- **Ingest UI wired to real backend** (off mock): document upload/URL with a live 4-stage
  stepper + outcome; folder-path import with strategy select + report; review queue with
  approve (edit domain/shelf). web builds clean.
- Verified live on gemini-3.5-flash: a Zero Trust doc → AI proposes NEW domain "Cybersecurity"
  (filed at conf 0.90); with a high gate it parked in Uncatalogued, then approve moved it to
  AI ▸ Security ▸ Zero Trust Architecture (confirmed in the tree). 55 unit tests green; ruff clean.
- Fix D-021: uvicorn worker must force UTF-8 stdout (structlog logging "▸" crashed ingest).

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

## Next actions (P2c — flywheel + catalog)
1. `ingest/questions.py` — generate 3–5 vi+en questions per page (prompt gen_questions.md).
   Hook it into `ingest/pipeline.py` + `ingest/importer.py` (after write_page).
2. `catalog/` — SQLite (WAL): `db.py` schema (questions+embeddings), `store.py` add/remove,
   `search.py` lookup (embed query, cosine over questions). `llm.embed` already works.
3. `agent/tools.ask_librarian` (cap max_ask_librarian) → wire into navigator TOOL_SPECS.
4. Lookup entry-point shortcut in orchestrator (catalog.lookup → navigate(entry_points)).
5. Wire the page reader's "generated questions" + Observatory later (P3).

## Watch out
- `web/src/api.ts` ↔ `libkb/api/events.py` are one contract — change both together (D-018).
- Answer is one SSE event (not token-streamed) — the walk is the live part.
- Everything Windows: `.venv\Scripts\...`, cp932 console (CLI forces UTF-8), no uv.
- `-m llm` tests + any `libkb ask`/API query spend real tokens — run deliberately.
- `recompute_stats` rewrites every `_meta.json` (updated_at) → git churn across `library/`; after
  a local import, `git checkout -- library/` before committing so only code/docs commit (D-020).
- Retail domain is on disk but gitignored; to re-import fresh: delete `library/domains/retail/`
  then `libkb import ... --domain Retail --shelves auto`.
- P2b document ingest REUSES `ingest/importer.get_or_create` + write_page (done).
- Parser deps (pymupdf4llm/trafilatura) are lazy-imported in parse.py — importing libkb.ingest
  doesn't require them; only actual pdf/html ingest does.
- Uncatalogued proposal is encoded in the parked book's description (`[proposed X ▸ Y · conf Z]`)
  and parsed back by list_uncatalogued (regex). If you add structured node metadata, migrate this.
- Windows port zombie: a killed uvicorn can leave port 8000 in LISTEN limbo (process gone,
  taskkill "not found"); it clears on its own. If dev.sh can't bind 8000, wait or use another port.
- The classify LLM call is slow (~11–20s). The ingest SSE "classify running" step sits there
  during that call — expected, not a hang.