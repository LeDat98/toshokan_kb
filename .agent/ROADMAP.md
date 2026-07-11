# ROADMAP

Phase details and rationale: `docs/ARCHITECTURE.md` §8. Function specs: `docs/FUNCTIONS.md`.

## P0 — Scaffold ✅ (2026-07-11)
- [x] `pyproject.toml` — venv+pip (D-011), deps: fastapi, uvicorn, pydantic v2, pydantic-settings, google-genai, numpy, httpx, python-ulid, structlog; dev: ruff, pytest
- [x] `libkb/config.py` (Settings, case-insensitive .env) + test
- [x] `libkb/llm/client.py` (generate/generate_json/embed/load_prompt, retries) + smoke test `tests/llm/test_smoke.py` — **passed against real API: gemini-3.5-flash + gemini-embedding-001 validated**
- [x] `libkb/library/models.py`, `store.py` + unit tests (no LLM) — 25 unit tests green
- [x] `libkb/cli.py`: `init`, `seed` — demo library seeded: AI→{RAG,LLM,CV}, 6 books, 16 pages
- [x] First commit

## P1 — Walking skeleton
- [ ] `agent/tools.py` (budget enforcement + visited-set) + unit tests with fake store
- [ ] `agent/navigator.py` (isolated context, event_cb) — `libkb ask --trace` end-to-end
- [ ] `library/views.py` (rebuild_description, propagate_up) on seed library
- [ ] `agent/answerer.py` (citations, InsufficientEvidence) + minimal `orchestrator.py`
- [ ] `api/`: `POST /api/query` SSE + `GET /api/library/*` + health
- [ ] Minimal chat UI from approved mockup (Ask screen: conversation + trace panel only)
- [ ] **DoD**: seed-library lookup answers with path citation; off-library query → honest NOT_FOUND; both visible in UI

## P2 — Ingest + flywheel
- [ ] `ingest/parse.py` (md, pdf, url) · `split.py` (structure-aware)
- [ ] `ingest/classify.py` + confidence gate + `_uncatalogued`
- [ ] `ingest/questions.py` (vi+en) · `catalog/` (db, store, search.lookup)
- [ ] `ingest/pipeline.py` + `POST /api/ingest` SSE stepper + Ingest UI tab
- [ ] `agent/tools.ask_librarian` + lookup entry-point shortcut in orchestrator
- [ ] Review queue UI

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
