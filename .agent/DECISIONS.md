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

## D-013 · 2026-07-11 · UI copy is English-only
User decision: no Vietnamese in the UI. Supersedes the "UI copy Vietnamese-first" part of
D-009 (docs/code English + chat with the user in Vietnamese still stand). Seed page one-liners
switched to English accordingly. The vi+en *generated questions* flywheel (D-005) is unaffected —
that is retrieval data (user-vocabulary bridge), not UI chrome.

## D-014 · 2026-07-11 · Frontend styling: CSS custom properties + typed inline styles (no Tailwind)
The approved design (Claude Design project "LibraryKB UI Design Brief",
b5cfb445-fadd-435b-be2a-2b7b9857b10e, file `LibraryKB.dc.html`) is authored entirely as design
tokens + computed inline styles. Porting 1:1 preserves fidelity; re-authoring in Tailwind would
be lossy and slower. So: tokens live in `web/src/tokens.css` (light+dark via `data-theme`),
shared style factories in `web/src/ui.ts`, hover states as small utility classes. The design
file is the styling source of truth — visual changes go through the Design project first.
TanStack Query / openapi-typescript adoption deferred to P1 API wiring.

## D-016 · 2026-07-11 · Tool-calling stays behind neutral types in llm/client.py
The navigator needs Gemini function-calling but only `llm/client.py` may import google.genai
(convention test). So the client exposes neutral dataclasses — `ToolSpec`, `ToolCall`, `Turn`,
`ToolResponse` — and translates them to/from genai types internally (`_to_genai_*`). The agent
package works purely in neutral types. `generate()` now accepts `str | list[Turn]` and disables
automatic function calling (we drive the loop for budgets/events/context isolation).

## D-017 · 2026-07-11 · Gemini 3 thought signatures must round-trip
Gemini 3.x rejects (400) a function-call turn echoed back without its `thought_signature`.
`ToolCall.thought_signature` carries the opaque bytes (captured from response parts in
`_to_result`, re-attached in `_to_genai_contents`). It is bytes, not a genai type, so the
boundary holds. Any future manual conversation replay must preserve it.

## D-021 · 2026-07-12 · The API server must force UTF-8 stdout too (extends D-012)
The uvicorn worker inherits the cp932 console, so structlog logging a library path with "▸"
crashed the ingest request (UnicodeEncodeError surfaced as an SSE error event). `api/main.py`
now reconfigures sys.stdout/stderr to UTF-8 at import, same as the CLI. /query didn't hit this
because it never logs "▸"; classify does. Rule stands: every entry point forces UTF-8.
Also: FastAPI's `File()`/`Form()`/`Depends()` in argument defaults is idiomatic → ruff B008 is
per-file-ignored for `libkb/api/routes.py`.

## D-020 · 2026-07-12 · Imported-from-private-source domains are gitignored
The retail corpus source (`Knowledge_Research-main/`) is private (user: don't push). Import COPIES
it into `library/domains/retail/`, and `library/` markdown is normally git-tracked (D-002) — so the
imported copy would leak the private content to GitHub. Fix: `.gitignore` excludes
`/library/domains/retail/`; the publishable AI seed (`library/domains/ai/`) stays tracked. General
rule: content imported from a gitignored source stays local. If a corpus is meant to be shared,
un-ignore its domain deliberately.
Caveat found: `store.recompute_stats` rewrites `updated_at` on every node each run → churns all
tracked `library/**/_meta.json` in git. For now, don't commit that churn (revert `library/` after
a local import). Future fix: only rewrite `_meta.json` when its content actually changed.

## D-019 · 2026-07-12 · Ingest is one pipeline that fills missing structural slots (docs/INGEST.md)
Reframed from "several ingest paths" to ONE pipeline: survey → DraftTree(provided/missing) →
resolve gaps → commit. The rulebase defines the 5 slots (domain▸shelf▸book▸toc▸page); the AI only
fills what a source doesn't already provide, so a clean folder imports ~deterministically (AI touches
only the shelf slot) while a raw PDF leans on the AI + confidence gate. `import` (folders) and
`ingest` (documents) are two entry points into the same pipeline. Import COPIES content into the
canonical `library/` store (not in-place); page body = source prose with YAML frontmatter stripped
(title/description/keywords lifted into TOC + page frontmatter). Shelf slot is always missing
(VALID_CHILD[domain]={shelf}) → strategies single/by-priority/auto-LLM. Supersedes the flat ingest
plan in FUNCTIONS.md §8. Delivery split P2a (import) / P2b (doc ingest) / P2c (flywheel+catalog).

## D-018 · 2026-07-11 · Query streaming = SSE over POST, walk on a worker thread
`POST /api/query` returns `text/event-stream`. The orchestrator is synchronous/blocking (LLM
calls), so the route runs it on a `threading.Thread` and bridges NavEvents to the async
generator via `loop.call_soon_threadsafe` + an `asyncio.Queue`. Events: `nav` (per step),
`answer` (once, whole answer), `done`, `error`. The browser can't POST with EventSource, so the
frontend (`web/src/api.ts`) parses the stream manually via fetch + ReadableStream. Token-level
answer streaming is deferred — the walk is the live part; the answer lands as one event.
`web/src/api.ts` is the frontend half of the contract in `libkb/api/events.py` — keep them in sync.

## D-015 · 2026-07-11 · docs/ARCHITECTURE.md is maintained in Vietnamese with Mermaid diagrams
User request: the architecture doc is Vietnamese (exception to D-009's English-docs rule, for
this file only) and all diagrams are Mermaid fenced blocks so they render in Markdown preview
(GitHub natively; VS Code needs the `bierner.markdown-mermaid` extension). Diagrams were
syntax-validated via the Mermaid tool before committing. Other docs (FUNCTIONS.md, UI brief,
.agent/*) stay English until asked. Content parity with the old English version preserved;
the phase table now tracks live status.
