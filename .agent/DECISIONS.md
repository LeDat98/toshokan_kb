# DECISIONS (append-only)

## D-001 · 2026-07-11 · Library-walk architecture over flat RAG
AI navigates a layered library (domain→shelf→book→TOC→page) as an active seeker; embedding
similarity is a supporting tool ("librarian"), not the backbone. Rationale + challenge analysis:
`docs/ARCHITECTURE.md` §1 (P1–P10). Alternatives (flat vector RAG, GraphRAG-only) rejected as
primary: user's founding requirements are agency + progressive context loading.

## D-002 · 2026-07-11 · Stack: Python 3.11+/FastAPI + React(Vite+TS+Tailwind); SQLite; fs-as-library
Backend Python (AI ecosystem, user familiarity), `google-genai` SDK only inside `llm/client.py`.
Library content = markdown/JSON on filesystem (human-inspectable, git-versionable, matches
metaphor). SQLite (WAL) for regenerable/binary data only: catalog embeddings, trajectories, eval
runs — gitignored. No external vector DB until >~100k questions (then sqlite-vec behind the same
`catalog.search` signature).

## D-003 · 2026-07-11 · Models via .env, defaults gemini-3.5-flash + gemini-embedding-001
User-specified Gemini; IDs are config, never hardcoded outside `config.py`. Two logical tiers
(`LIBKB_MODEL`, `LIBKB_MODEL_LITE`) even while both point to the same model — later per-node
assignment must be by *measured difficulty* (eval per-node accuracy), not by tree depth.

## D-004 · 2026-07-11 · Leaf pages are the single source of truth (P1)
All ancestor descriptions/TOC lines are materialized views regenerated from children, never
incrementally patched (patching → laundry-list drift → routing decay). `store.set_description`
is callable only from `views.py` (convention + test).

## D-005 · 2026-07-11 · Question flywheel at ingest (P2)
3–5 questions per page, vi+en, phrased in user vocabulary. One artifact = catalog entry points
+ routing eval set + vocabulary bridge + refactor regression tests. This is the system's main
compounding asset.

## D-006 · 2026-07-11 · Strict tree + childless see-also aliases (P4); stable IDs + redirects (P5)
No DAG storage (diamond update problem). Aliases created demand-driven from misroute logs (P9),
not speculatively. Node IDs are ULIDs, never reused; move/split/merge writes redirects.

## D-007 · 2026-07-11 · Honest NOT_FOUND + mandatory path citations (P6); navigator context isolation (P7)
Answers only from read pages; insufficient evidence → designed not-found state with closest
shelves. Navigator returns (path, pages, status) — answering context never sees rejected menus.

## D-008 · 2026-07-11 · Budgets enforced in tool layer, not prompts
max_hops=12, max_pages=6, ask_librarian≤2, visited-set loop detection — hard-coded guards in
`agent/tools.py`; prompts merely explain them.

## D-009 · 2026-07-11 · Durable docs & code in English; user-facing chat in Vietnamese
Design docs, code, comments, commits: English (tooling/AI-design compatibility). Conversation
with the user and UI sample content: Vietnamese-first.

## D-010 · 2026-07-11 · UI mockup via Claude Design from docs/UI_DESIGN_BRIEF.md
Colors intentionally unspecified (semantic roles only) — chosen in the Design tool. Frontend
implements the approved mockup; Ask screen (chat + navigation trace) ships first.

## D-011 · 2026-07-11 · venv + pip instead of uv
User declined installing uv. Environment manager is standard `python -m venv .venv` +
`pip install -e ".[dev]"`. CONVENTIONS.md and CLAUDE.md command sections updated. Supersedes
the uv references in D-002-era docs.

## D-012 · 2026-07-11 · CLI forces stdout/stderr to UTF-8
The user's Windows console defaults to a legacy codepage (cp932) that cannot print "▸"/"·"
used in citations and menus. `cli.main()` calls `sys.stdout.reconfigure(encoding="utf-8")`
at startup. Any future entry point (API logs, scripts) must not assume console UTF-8.
