# LibraryKB — Architecture

> An AI knowledge base organized like a physical library. The AI does not "search an index";
> it **walks the library**: domain hall → shelf → book → table of contents → page.
> Two founding requirements: (1) the AI is an **active seeker**, not a passive similarity consumer;
> (2) retrieval is **layered** so context is loaded progressively, never in bulk.

## 1. Core principles (settled in design rounds 1–2)

These are load-bearing. Do not violate them casually; record any change in `.agent/DECISIONS.md`.

| # | Principle | Consequence |
|---|-----------|-------------|
| P1 | **Leaf pages are the single source of truth.** Every description above (book summary, shelf card, domain card, TOC one-liners) is a *materialized view*, regenerated from its children — never hand-patched. | Full rebuild is always possible; summary drift is impossible by construction. |
| P2 | **The question flywheel.** At ingest, every page gets 3–5 auto-generated questions (VI + EN) it can answer. One artifact, four uses: routing eval set, O(1) entry points (card catalog), user-vocabulary ↔ taxonomy bridge, regression tests for tree refactors. | Every ingest makes the system smarter and testable. |
| P3 | **Front-door query classifier.** `lookup` / `synthesis` / `exploratory` decide the retrieval strategy. There is no single navigation strategy good for all three. | Lookup uses catalog shortcuts; synthesis uses map-reduce coverage scan; exploratory walks the tree. |
| P4 | **Storage is a strict tree; cross-links are childless aliases.** One canonical location per content; `see-also` redirects carry no children. | Update propagation stays a tree operation (no diamond problem). |
| P5 | **Node IDs are immutable and never reused. Moves/splits leave redirects** (HTTP-301 style tombstones). | Caches, citations, and agent memory survive refactors. |
| P6 | **Honest terminal states + path citations.** Every answer cites its walk (`Domain ▸ Shelf ▸ Book ▸ p.N`). `NOT_FOUND` is a first-class, user-visible outcome — never improvise an answer without pages. | Auditability is the killer feature over flat RAG. |
| P7 | **Navigator is context-isolated.** It walks in its own context and returns only `(path, pages, status)`. The answering context never sees rejected menus. | No context pollution; token budget stays honest. |
| P8 | **Tree refactors are eval-gated.** Split/merge/move runs the routing eval (from P2) before/after; regression ⇒ revert. Rebalance offline, in batches. | The taxonomy can evolve without silently breaking routing. |
| P9 | **Aliases and description rewrites are demand-driven** — created from observed misroutes in trajectory logs, not speculatively. | Cross-links stay few and useful; descriptions stay discriminative. |
| P10 | **Confidence-gated ingest.** Low-confidence classification goes to the `_uncatalogued` shelf for review, never force-filed. | Misfiled books (permanent, silent errors) are prevented at the gate. |

## 2. System overview

```
                 ┌──────────────────────────────────────────────┐
 User query ───► │ Orchestrator                                 │
                 │  1. classify_query()  (P3)                   │
                 │  2. pick strategy:                           │
                 │     lookup      → catalog.lookup → navigate  │
                 │     synthesis   → coverage_scan  → navigate* │
                 │     exploratory → navigate from root         │
                 │  3. compose_answer()  (P6 citations)         │
                 └───────┬──────────────────────┬───────────────┘
                         │ isolated (P7)        │
                 ┌───────▼────────┐    ┌────────▼────────┐
                 │ Navigator      │    │ Card Catalog    │
                 │ (Gemini + tools│    │ SQLite +        │
                 │  browse/open/  │    │ embeddings over │
                 │  read/back/ask │    │ generated Qs    │
                 │  /found/       │    │ (P2)            │
                 │  not_found)    │    └────────▲────────┘
                 └───────┬────────┘             │
                 ┌───────▼──────────────────────┴───────────────┐
                 │ LibraryStore (filesystem tree, P1/P4/P5)     │
                 │ domain/ → shelf/ → book/ → toc.json + pages  │
                 └───────▲──────────────────────────────────────┘
                         │
                 ┌───────┴────────┐   ┌─────────────────┐
                 │ Ingest pipeline│   │ Trajectory log +│
                 │ parse→split→   │   │ Eval runner +   │
                 │ classify(P10)→ │   │ Maintenance     │
                 │ file→questions │   │ (P8, P9)        │
                 │ →views(P1)     │   └─────────────────┘
                 └────────────────┘
```

## 3. On-disk layout

```
library/
  _meta.json                     # library root card
  domains/
    ai/
      _meta.json                 # NodeMeta: id, title, description(rev), stats, see_also
      shelves/
        rag/
          _meta.json
          shelves/               # shelves may nest (created by splits)
          books/
            advanced-rag-techniques/
              _meta.json         # book card: summary, source, ingest report ref
              toc.json           # chapters → pages: {page_id, title, one_line, keywords}
              pages/
                001-what-is-rag.md
                012-reranking.md
  _uncatalogued/                 # P10 review queue (books await placement)
  _catalog/
    catalog.db                   # SQLite: questions+embeddings, redirects, trajectories, eval runs
```

Markdown + JSON on the filesystem is deliberate: human-inspectable, git-versionable, and the
library *is* its own storage metaphor. SQLite holds only regenerable/binary data (gitignored).

## 4. Query strategies

| Type | Path | Latency target |
|------|------|----------------|
| `lookup` | catalog.lookup(query) → top entry points → navigate with hints (verify + read) → answer | ≤ ~5 s |
| `synthesis` | coverage_scan: parallel cheap "do you hold content on X?" per top node → navigate each hit (parallel, capped) → reduce with per-source citations | ≤ ~20 s |
| `exploratory` | full walk from root, wider read budget, beam ≤ 2 on close calls | best-effort |

Fallback ladder (all types): navigation `NOT_FOUND` → direct catalog nearest-pages check → honest
`NOT_FOUND` answer with closest shelves listed (P6).

## 5. Models & budgets

All models configurable via `.env` (see `.env.example`); defaults:

- `LIBKB_MODEL` = `gemini-3.5-flash` — navigator, answerer, synthesis reduce.
- `LIBKB_MODEL_LITE` = `gemini-3.5-flash` — query classify, ingest classify, question gen, description rebuild. (Split later per-node by measured difficulty, not by depth — see DECISIONS.)
- `LIBKB_EMBED_MODEL` = `gemini-embedding-001` — catalog embeddings.

Hard budgets enforced by the tool layer, not by prompting: `MAX_HOPS=12`, `MAX_PAGES_PER_NAV=6`,
`ask_librarian ≤ 2` per navigation, visited-set loop detection.

## 6. Scale posture

Cold start (< ~200 docs): tree is 1–2 levels; navigation is trivially short; split/alias/eval
machinery stays dormant (thresholds in config). The same tools work at depth 1 and depth 5 —
mechanisms activate by size, code paths do not change.

Growth pressure points and their valves: routing error compounding → P2 eval + P9 rewrites;
menu bloat → branching factor 10–50 with P8 splits; latency → catalog shortcuts (P2) + per-node
model assignment; staleness → P1 rebuilds.

## 7. Security note

Book content is untrusted input (may come from the web). The navigator must treat page text as
data: prompt-injection phrases inside pages must never redirect the walk or alter tool behavior.
Page content is only ever shown to the *answerer* wrapped in delimited evidence blocks.

## 8. Delivery phases

| Phase | Goal | Proves |
|-------|------|--------|
| P0 | Scaffold: config, LLM client, store skeleton, seed script | Gemini call works; tree CRUD works |
| P1 | **Walking skeleton**: seeded mini-library + navigator + tools + `POST /api/query` (SSE) + minimal chat UI | The core loop end-to-end |
| P2 | Ingest pipeline + question flywheel + card catalog + lookup shortcuts | P2/P10 principles live |
| P3 | Query classifier + synthesis map-reduce + trajectory logging + eval runner | P3/P6/P8 measurable |
| P4 | Maintenance (split/merge, demand-driven aliases) + Observatory UI | P8/P9 closed loop |

UI mockup runs in parallel via Claude Design using `docs/UI_DESIGN_BRIEF.md`; the real frontend
is wired from the approved mockup starting P1 (chat only) and grows per phase.
