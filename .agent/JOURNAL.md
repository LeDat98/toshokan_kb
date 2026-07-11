# JOURNAL (append-only, newest last)

## 2026-07-11 — Design session (no code)
- Two analysis rounds on the library-walk concept: challenges at scale (routing error
  compounding, hop latency, non-tree taxonomy, branching vs depth, summary maintenance,
  vocabulary mismatch, cross-branch synthesis) and second-round critique that produced
  principles P1–P10 — captured in `docs/ARCHITECTURE.md`.
- Wrote `docs/FUNCTIONS.md` (full module/function specs, P0–P4 tags) and
  `docs/UI_DESIGN_BRIEF.md` (complete mockup context for Claude Design).
- Scaffolded `.agent/` management layer, `CLAUDE.md`, `.gitignore` (protects `.env`),
  `.env.example`; `git init` done, no commits yet.
- Key insight to remember: the question flywheel (D-005) and materialized-view descriptions
  (D-004) carry most of the system's long-term quality; don't cut them when simplifying.
- Handoff: next session can start P0 immediately (see `.agent/STATE.md`); mockup is user-driven
  in parallel.

## 2026-07-11 — P0 implementation (same day, session continued)
- Built the full P0 scaffold: pyproject, config (case-insensitive .env), Gemini client
  (generate/generate_json/embed/load_prompt + retries + usage logging), library models + fs
  store (menus, TOC, frontmatter pages, stats, see-also, move), seed (6 books / 16 pages,
  discriminative descriptions), CLI init/seed. 25 unit tests + ruff clean.
- **Live validation**: smoke tests against the real API passed — `gemini-3.5-flash` and
  `gemini-embedding-001` are valid model IDs with the user's key.
- Deviations recorded: D-011 (user declined uv → venv+pip), D-012 (console cp932 →
  CLI forces UTF-8 stdout; found via a real UnicodeEncodeError on `·`).
- Surprise worth remembering: user's terminal is Japanese-locale cp932 — always assume
  legacy codepage on this machine's consoles.
- Handoff: start P1 at `agent/tools.py` (budgets in code, not prompts — D-008).

## 2026-07-11 — UI implementation from Claude Design (session 2)
- User made the mockup in Claude Design (scoping answers: interactive app, pre-animated walks,
  Ask+Library focus, global theme toggle). Imported `LibraryKB.dc.html` via DesignSync from
  project b5cfb445-fadd-435b-be2a-2b7b9857b10e and implemented it 1:1 as `web/` (Vite+React+TS).
- Decisions: D-013 UI English-only (seed one-liners translated); D-014 no Tailwind — tokens.css
  + typed inline styles ported from the design file, which stays the styling source of truth.
- All four screens + walk engine + theme + toasts implemented on `src/data/mock.ts` (shapes
  mirror the future API). `npm run build` clean on first run; backend tests still green.
- Gotcha logged: PowerShell 5.1 `Get-Content` without `-Encoding UTF8` mangled the design file
  (cp932 mojibake) — re-extracted with explicit UTF-8. Same cp932 theme as D-012.
- Handoff: P1 backend next; then replace mock layer with SSE client (vite proxy to :8000 ready).

## 2026-07-11 — P1 walking skeleton, backend + API + UI wiring (session 3, on Opus)
- Built the whole walking loop: extended llm/client with neutral tool-calling types translated
  to genai (D-016); agent/tools (6 tools, budgets in code), navigator (isolated context),
  answerer, orchestrator, library/views; cli `ask --trace`. Then api/ (SSE query on a worker
  thread D-018, library endpoints), and wired the Ask + Library screens to the real backend.
- Verified LIVE on gemini-3.5-flash, twice: CLI and browser (via vite proxy). The reranking
  lookup walks AI▸RAG▸Advanced RAG▸p.12 and cites the path; QEC returns honest NOT_FOUND after
  backtracking out of Uncatalogued and AI. Committed navigator core as `33c030c`.
- Two real gotchas, both logged as decisions:
  * D-017 — Gemini 3 rejects a function-call turn echoed back without its `thought_signature`;
    had to capture it from response parts and re-attach it. Cost one failed live run to find.
  * D-018 — SSE-over-POST needs a worker thread + asyncio.Queue bridge; EventSource can't POST
    so the frontend parses the stream by hand.
- 39 unit tests (14 new for tools+navigator, all LLM-free via a scripted fake LLM); ruff clean;
  web builds clean. Ingest + Observatory intentionally left on mock.ts (P2/P3).
- Handoff: P2 = ingest pipeline + question flywheel + card catalog (see STATE.md). The
  ask_librarian tool + lookup shortcut plug into the navigator once the catalog exists.

## 2026-07-12 — P2a import + ingest design (session 4, Opus)
- User has a private, well-structured retail knowledge folder (12 topic folders, 92 md files, all
  with rich YAML frontmatter incl. a hand-written question-phrased `description`). Discussed how to
  ingest it AND raw PDFs. Their insight reframed the whole thing: don't build separate paths — have
  ONE pipeline where a rulebase defines the 5 slots and the AI only fills what the source lacks.
- Wrote `docs/INGEST.md` (the rulebase: provided-vs-missing per source shape, folder depth rule,
  physical storage = copy into canonical library, shelf strategies, confidence gate). Updated
  FUNCTIONS §8 pointer, ROADMAP P2→P2a/b/c, DECISIONS D-019/D-020.
- Built P2a import: survey/resolve/importer + `libkb import`. Imported the real retail corpus;
  `--shelves auto` had Gemini group 12 books into 3 clean thematic shelves; a retail `ask` then
  walked into the imported KPI Dictionary and answered with a real citation. 8 new LLM-free tests
  (55 total... actually 47 pass + 2 llm deselected); ruff clean.
- Gotchas: (1) retail content is private but library/ is git-tracked → gitignored
  `library/domains/retail/` (D-020); (2) recompute_stats churns every _meta.json → revert library/
  before committing. Committed code/docs only; retail stays local.
- Handoff: P2b (PDF/doc ingest) reuses DraftTree + importer.commit; the LLM classifier fills the
  domain/shelf/page-split slots a raw doc leaves missing, gated by confidence → _uncatalogued.

## 2026-07-12 — P2b document ingest + Ingest UI wiring (session 5, Opus)
- User noticed the Ingest screen was a non-functional mockup (only a fake link box). Built P2b:
  parse (md/txt/pdf/html/url, lazy deps), split (heading + size fallback), classify (LLM top-down
  placement vs the live tree, create-if-missing, reconciled to reality, confidence), pipeline
  (parse→split→classify→file; low confidence → _uncatalogued; list/approve for review). Then the
  API (ingest/import SSE + review + approve) and a full rewrite of the Ingest screen off mock.
- Verified LIVE, twice: a Zero Trust markdown doc, ingested into a library that only had AI,
  had Gemini propose a NEW "Cybersecurity" domain + "Zero Trust" shelf and file 5 pages; with a
  high gate it parked in Uncatalogued and the API review→approve moved it to AI ▸ Security. This
  is the "AI builds the hierarchy from a raw doc" story the user asked about, working.
- Gotcha D-021: the uvicorn worker inherits cp932; structlog logging a path with "▸" crashed the
  ingest request. Fixed by forcing UTF-8 stdout in api/main.py (same as CLI). Found via a real
  failing SSE run — the error came back as an `error` event my curl parser had filtered out.
- Also: Windows left port 8000 in a zombie LISTEN state after killing a --reload uvicorn; verified
  the API on 8001 instead. Frontend builds clean; 55 backend tests green; ruff clean.
- 3 commits: b33f0b9-ish chain … P2b backend e860bf8, then P2b API+UI (this).
- Handoff: P2c = question flywheel + SQLite card catalog + ask_librarian (see STATE.md).
