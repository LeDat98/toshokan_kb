# STATE — as of 2026-07-11 (end of session 2)

**Phase:** P0 complete ✅ · UI implemented on mock data ✅ → next is P1 (walking skeleton backend, then wire UI)

## What exists and works
- Backend P0 (commit `b7b0dfc`): config, Gemini client (validated live: `gemini-3.5-flash`,
  `gemini-embedding-001`), fs LibraryStore, seed library (6 books / 16 pages, English one-liners),
  CLI init/seed. 25 unit + 2 LLM smoke tests green, ruff clean.
- **Frontend `web/`** (Vite + React + TS strict, builds clean): full implementation of the
  approved Claude Design mockup — Ask (animated walk engine: staged reveal, backtrack + "why",
  parallel synthesis branches, FOUND/NOT_FOUND terminals, stop, trace collapse), Library
  (miller columns, book spines + sparklines, TOC reader, page reader + generated questions),
  Ingest (dropzone, pipeline stepper, interactive classify w/ confidence gate, retry, review
  queue), Observatory (KPIs, trajectories + trace replay, eval chart, misroutes, suggested
  fixes w/ approve/dismiss), sidebar/topbar/theme toggle/toasts. All data from
  `web/src/data/mock.ts`, which mirrors the future API contract.
- Design source of truth: Claude Design project `LibraryKB UI Design Brief`
  (b5cfb445-fadd-435b-be2a-2b7b9857b10e), file `LibraryKB.dc.html` (D-014).

## Next actions (P1)
1. `agent/tools.py` — 7 navigator tools, hard budgets, visited-set (D-008).
2. `agent/navigator.py` + `libkb ask --trace` end-to-end on the seed library.
3. `library/views.py` (rebuild_description / propagate_up) — run once on seed.
4. `answerer.py` + minimal orchestrator + `api/` `POST /api/query` SSE + `GET /api/library/*`.
5. Swap `web/src/data/mock.ts` behind a real client for Ask + Library (vite proxy → :8000 ready).

## Blockers
- None.

## Watch out
- Run frontend: `cd web && npm run dev` (or `npm run build` to verify). Node 25 present.
- UI copy is English-only (D-013); no Tailwind — styling goes through tokens.css/ui.ts (D-014).
- `.env` var casing, cp932 console, no-uv — see D-011/D-012 and session-1 notes.
- pytest default excludes `-m llm` (token cost); run explicitly when needed.
