# STATE — as of 2026-07-11 (end of session 1)

**Phase:** P0 complete ✅ → next is P1 (walking skeleton)

## What exists and works
- Design docs (`docs/ARCHITECTURE.md`, `docs/FUNCTIONS.md`, `docs/UI_DESIGN_BRIEF.md`);
  `.agent/` management layer; CLAUDE.md.
- Backend scaffold, all green: `libkb/config.py`, `libkb/llm/client.py`
  (generate / generate_json / embed / load_prompt, retry+logging),
  `libkb/library/models.py` + `store.py` (fs tree, menus, TOC, pages, stats, see-also, move),
  `libkb/seed.py` + `libkb/cli.py` (`init`, `seed`).
- 25 unit tests + 2 real-API smoke tests pass; ruff clean.
  **Verified live: `gemini-3.5-flash` and `gemini-embedding-001` work with the .env key.**
- Demo library seeded at `library/`: AI → {RAG(3), LLM(2), CV(1)} = 6 books, 16 pages,
  discriminative descriptions + one see-also (RAG → LLM).
- venv at `.venv/` (python -m venv + pip, NO uv — D-011).

## Next actions (P1, in order — see ROADMAP)
1. `agent/tools.py` — 7 navigator tools with hard budgets (hops/pages/librarian, visited-set).
2. `agent/navigator.py` — isolated-context walk loop + `libkb ask --trace` end-to-end.
3. `library/views.py` — rebuild_description/propagate_up (then run on seed library).
4. `agent/answerer.py` + minimal orchestrator + `POST /api/query` SSE.
5. Wire minimal Ask UI once the user's Claude Design mockup is approved (parallel track).

## Blockers
- None. Mockup (user-driven, in progress at Claude Design) only gates frontend wiring.

## Watch out
- `.env` var is `Gemini_API_Key` (odd casing) — Settings reads case-insensitively; don't "fix" it.
- User's console codepage is cp932 → CLI reconfigures stdout to UTF-8 (D-012); any new entry
  point must do the same before printing "▸"/"·".
- Windows + no uv: invoke everything via `.venv\Scripts\python.exe -m …` (see CLAUDE.md commands).
- pytest default filters out `-m llm` tests (addopts) — they cost tokens, run explicitly only.
