# ROADMAP

Phase details and rationale: `docs/ARCHITECTURE.md` §8. Function specs: `docs/FUNCTIONS.md`.

## P0 — Scaffold ✅ (2026-07-11)
- [x] `pyproject.toml` — venv+pip (D-011), deps: fastapi, uvicorn, pydantic v2, pydantic-settings, google-genai, numpy, httpx, python-ulid, structlog; dev: ruff, pytest
- [x] `libkb/config.py` (Settings, case-insensitive .env) + test
- [x] `libkb/llm/client.py` (generate/generate_json/embed/load_prompt, retries) + smoke test `tests/llm/test_smoke.py` — **passed against real API: gemini-3.5-flash + gemini-embedding-001 validated**
- [x] `libkb/library/models.py`, `store.py` + unit tests (no LLM) — 25 unit tests green
- [x] `libkb/cli.py`: `init`, `seed` — demo library seeded: AI→{RAG,LLM,CV}, 6 books, 16 pages
- [x] First commit

## P1 — Walking skeleton ✅ (2026-07-11)
- [x] `agent/tools.py` (6 tools, hard budgets, visited-set) + unit tests with real seed store
- [x] `agent/navigator.py` (isolated context, event_cb) — `libkb ask --trace` end-to-end
- [x] `library/views.py` (rebuild_description, propagate_up, rebuild_all) + `libkb rebuild-views`
- [x] `agent/answerer.py` (citations, insufficient→not_found) + `orchestrator.py`
- [x] `api/`: `POST /api/query` SSE + `GET /api/library/tree|node|book|page` + `/health`
- [x] Ask UI wired to real streaming query; Library UI wired to real tree/node/book/page
- [x] **DoD met**: "reranking in RAG" walks AI▸RAG▸Advanced RAG▸p.12 with a path citation;
  "quantum error correction" → honest NOT_FOUND with backtracks — both live in the browser
  via the vite proxy. 39 unit tests green; frontend builds clean.
- [~] Note: token-level answer streaming deferred (answer arrives as one SSE event after the walk)

## P2 — Ingest + flywheel   (design: docs/INGEST.md · one pipeline, DraftTree, D-019)
### P2a — Import (structure-preserving, deterministic core)
- [ ] `ingest/models.py` (DraftTree/DraftBook/DraftPage) + frontmatter parsing (pyyaml)
- [ ] `ingest/survey.py` (folder → DraftTree; detect provided/missing levels; depth rule)
- [ ] `ingest/resolve.py` (shelf strategies: single / by-priority / auto-LLM grouping)
- [ ] `ingest/importer.py` (get-or-create commit into store; idempotent re-runs)
- [ ] `libkb import <folder> --domain X` + tests (LLM-free fixture) + import retail corpus
### P2b — Ingest a document
- [ ] `ingest/parse.py` (pdf via pymupdf4llm, html/url via trafilatura) · `split.py` (structure-aware)
- [ ] `ingest/classify.py` (top-down placement, create-if-missing) + confidence gate + `_uncatalogued`
- [ ] `POST /api/ingest` SSE stepper + Ingest UI tab (off mock) + review queue UI
### P2c — Flywheel + catalog
- [ ] `ingest/questions.py` (vi+en) · `catalog/` (db, store, search.lookup)
- [ ] `agent/tools.ask_librarian` + lookup entry-point shortcut in orchestrator

## P3 — Strategies + measurement
- [ ] `agent/classifier.py` (front door) · `synthesizer.py` (coverage_scan, map-reduce)
- [ ] `trajectory/logger.py` + `analyzer.py` (misroutes → suggested fixes)
- [ ] `evals/runner.py` + `gates.py` + `libkb eval`
- [ ] Observatory UI: KPIs, trajectories table + trace replay

## P4 — Maintenance loop
- [ ] `maintenance/rebalance.py` (suggest/apply split, merge; eval-gated, auto-revert)
- [ ] `library/aliases.py` demand-driven creation from analyzer fixes
- [ ] Observatory: misroute panel + fix approval cards + eval history chart
- [ ] Full Library explorer UI (miller columns, book view, page reader)

## Parallel track — UI
- [x] Mockup via Claude Design from `docs/UI_DESIGN_BRIEF.md` (user-driven) — project
  `LibraryKB UI Design Brief` (b5cfb445-fadd-435b-be2a-2b7b9857b10e), file `LibraryKB.dc.html`
- [x] Implement design as `web/` app (2026-07-11): tokens light+dark, icon set, PathChip,
  TracePanel (walk engine incl. backtrack/why, parallel branches, FOUND/NOT_FOUND), Library
  miller columns + book/page reader, Ingest stepper + review queue, Observatory (KPIs,
  trajectories + replay, eval chart, misroutes, fixes), toasts — all on `src/data/mock.ts`
- [ ] Wire real backend per phase: Ask SSE (P1) → Library GETs (P1) → Ingest (P2) → Observatory (P3)
