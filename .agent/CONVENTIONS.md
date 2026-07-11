# CONVENTIONS

Changes to this file require a `DECISIONS.md` entry.

## Python (backend)
- Python 3.11+, standard **venv + pip** (`python -m venv .venv`, `pip install -e ".[dev]"`) —
  no uv (D-011). Package `libkb/` at repo root; run tools via `.venv\Scripts\python.exe -m …`.
- **Type hints mandatory**; data structures are **pydantic v2** models (`BaseModel`), config via
  `pydantic-settings`. No bare dicts across module boundaries.
- Lint/format: **ruff** (line length 100, `ruff check --fix` + `ruff format` before commit).
- Tests: **pytest**, `tests/` mirrors package layout.
  - Unit tests must not call the LLM (fake `LLM` via dependency injection).
  - LLM smoke/golden tests live in `tests/llm/`, run only via explicit `pytest tests/llm -m llm`.
  - Eval runs cost tokens → only via `libkb eval`, never in CI defaults.
- Logging: **structlog**, no `print` outside `cli.py`. Every LLM call logs model, tokens, latency.
- Errors: exception tree rooted at `LibKBError` (`NodeNotFound`, `LLMError`, `IngestError`,
  `InsufficientEvidence`…). API layer maps them to HTTP; internals never raise bare `Exception`.
- **LLM discipline**: only `llm/client.py` imports `google.genai`. Prompts live in
  `libkb/llm/prompts/*.md` — versioned, reviewed like code, never inline f-strings.
- **Store discipline**: `store.set_description` called only by `views.py` (enforced by a test
  grepping call sites). Page markdown is written once at ingest; edits go through re-ingest.
- Async: FastAPI routes async; navigator loop sync-per-call is fine (isolated), fan-out uses
  `asyncio.gather` with concurrency caps from config.
- Money guard: any code path that can spend >~50 LLM calls in one action must take an explicit
  `budget`/`sample` parameter with a safe default.

## TypeScript (frontend, from P1)
- Vite + React + TS `strict`; Tailwind. Components: function components only, named exports
  (default export only for route pages).
- Server state via TanStack Query; SSE handled in one `useQueryStream` hook shared by Ask/Ingest.
- API types generated from FastAPI OpenAPI (`openapi-typescript`) — no hand-written mirrors.
- Components follow the shared inventory in `docs/UI_DESIGN_BRIEF.md` §8 (PathChip, TraceStep…);
  one component per file under `web/src/components/`.

## Git
- Conventional commits: `feat: | fix: | docs: | refactor: | test: | chore:`, imperative, ≤ 72 chars
  subject. Small, single-purpose commits; commit only when tests pass.
- Branch per phase-feature (`p1/navigator`), merge to `main` when its ROADMAP box ticks.
- **Never commit `.env`** (gitignored — keep it that way). `library/` content IS committed
  (markdown/JSON); `library/_catalog/*.db` is not (regenerable).

## Naming
- NodeID: `nd_<ULID>`; slugs: kebab-case ASCII (Vietnamese titles transliterated for slugs,
  original title kept in `title`).
- SSE event names: snake_case, versioned in `api/events.py` — the single contract file with the UI.

## Language
- Code, comments, docs, commits: **English**. User-facing strings (UI, answers): **Vietnamese-first**
  (answer language follows the query language).
