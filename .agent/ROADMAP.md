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
### P2b — Ingest a document ✅ (2026-07-12)
- [x] `ingest/parse.py` (pdf via pymupdf4llm, html/url via trafilatura, md/txt) · `split.py` (heading-based + size fallback)
- [x] `ingest/classify.py` (top-down placement, create-if-missing, reconciled) + confidence gate + `_uncatalogued`
- [x] `ingest/pipeline.py` (ingest_document + list_uncatalogued + approve_placement); `libkb ingest <src>`
- [x] `POST /api/ingest` + `/api/import` (SSE) + `/api/ingest/review` + approve; Ingest UI wired off mock
  (file/URL upload + folder-path import + live stepper + review queue). Verified live end-to-end.
### P2c — Flywheel + catalog ✅ (2026-07-12)
- [x] `ingest/questions.py` (bilingual 4×2 questions/page + `index_page`) · `catalog/` (db WAL, store
  brute-force cosine, `search.lookup`); flywheel hooks in importer/pipeline/approve (best-effort)
- [x] `agent/tools.ask_librarian` (budgeted, hints not teleport) + answerer-gated lookup shortcut in
  orchestrator; CLI `reindex`/`--index`; API `/query` shortcut + index-on-ingest/approve
- [x] **DoD met (live, gemini-3.5-flash)**: reindex AI → 240 q/30 pages; a reranking paraphrase
  answered via shortcut in 0 hops with citation; an off-library query declined the shortcut, used
  ask_librarian twice, honest NOT_FOUND. 66 unit tests green; ruff clean.

## P3 — Strategies + measurement
- [x] `evals/` (dataset from catalog, runner with level scoring, gates) + `libkb eval` (D-024);
  LLM-free tests (build_cases/score_case/aggregate/gates). Modes: walk / assisted / shortcut.
- [x] Free diagnostics, no LLM: `libkb probe-catalog` (D-028 — the shortcut gate was HARMFUL; gate on
  MARGIN, not cosine) · `libkb probe-separability` (D-029 — sibling books are only 82.3% separable)
- [x] **Routing redesign** (D-029): the book is storage, not routing. `open_shelf()` union TOC,
  `routing_mode=shelf` default, `book` kept for the A/B.
- [x] **§0a + metric fixes** (D-030): `one_line` capped at render + ingest (menus −77% tokens); scale
  guard budgets tokens AND options; **`answer_acc` LLM judge is the primary metric** (`page_acc` is
  biased against shelf routing); `mean_input_tokens` reported; gates DISARMED until a real baseline.
- [x] `libkb make-holdout` — held-out paraphrase set, saved to disk (both A/B arms need identical
  questions). `evals/` gitignored: the questions are generated from the private corpus (D-020).
- [x] **THE A/B (D-031): `book` vs `shelf`, 30 held-out cases/arm — route B WON on every axis.**
  answer_acc 90.0% → **96.7%**; page_acc 66.7% → 80.0%; hops 5.2 → 4.3; backtracks 2.1 → **0.9**;
  tokens −9%. Paired: **6 rescues, 0 losses.** Gate armed at `min_answer_acc=0.90`.
- [x] **PART II** (D-032), all reproduced before building, 137 tests green:
  - [x] `probe-recall` — embedding is a bad ORACLE (LOI top-1 39.3%) and a good SIEVE (top-10 90.7%)
  - [x] `probe-misshelved` + `build-crosslinks` — 49% of pages fit another book better; the answer is
        a cross-reference, not a move. One location, many access points.
  - [x] Page digest — the librarian puts the book back. Conversation plateaus instead of growing.
  - [x] Shelf shortlist with a REAL escape hatch (fixed: `open_book` used to loop back into it)
  - [x] `reframe` — the query evolves with the vocabulary the walk teaches it (Bates 1989)
  - [x] **Trajectory logger + `libkb harvest`** — the demand-side flywheel. Generated questions are
        the cold start; the head of a Zipf query distribution can only be learned from traffic.
  - [x] Entry vocabulary (term ring, `kind='term'`) — built, **unmeasured on purpose**; needs reindex
  - [x] ~~hybrid BM25~~ **REFUTED by measurement** (recall down on both query distributions) — off
  - [x] ~~`routing_mode="auto"`~~ **DROPPED on the doc's own test** (0 losses on well-separated shelves)
## P3.5 — RETRIEVAL REDESIGN: the LLM was the sieve; it should be the oracle (D-034/D-035)
- [x] Diagnosis: a walk sees **8,601 tokens** of distinct information and we pay **45,268** — O(T²).
  And greedy tree descent is provably **not Bayes-optimal** (Zhuo et al., ICML 2020).
- [x] The hierarchy does **not** accelerate search (I claimed it did; it does not). ANN does.
- [x] PageIndex read from source: **2 LLM calls, no embeddings, no agent, no rollback**; and their
  98.7% is **90.7%** by their own judge. We were losing on architecture, not quality.
- [x] `libkb/agent/cascade.py` — propose (free) → triage on **section headers** → open the **basket**
  once → re-open in full → widen. `libkb/library/sections.py` (a section is **13.5×** cheaper than a
  page). `LIBKB_RETRIEVAL_MODE=cascade`.
- [x] **`libkb eval --save` + `libkb rejudge`** — the answers are the expensive artifact; grading them
  is not. Three times this session the METRIC was the broken thing. Never again.
- [x] Ingest: `clean_title` strips markdown emphasis (`**2 Related Work**` was riding into titles,
  TOCs, citations and triage cards)
- [x] **The fair A/B**: both arms, corrected judge, answers saved. **Cascade wins; it is the default**
  (D-036) — same accuracy, better routing at every level, **14× cheaper**.

## P3.6 — INGEST IS A RULE, NOT A PILE OF CASES (D-037/D-038)
*"If every new document type needs a code change, that is not a product."* — the user, and he was right.
- [x] **The ingest contract** (`ingest/questions.py`) — every leaf gets title + one_line + keywords +
  questions whatever it came from; missing fields are generated **in the lite call already being made**.
  Frontmatter is a shortcut, never a dependency. **A new source format costs zero lines of code.**
- [x] **The recursive splitter** (`ingest/split.py`) — structure → recurse into an oversized piece at
  ITS own structure → size only when structure runs out → merge strays. Budgets in `Settings`.
  Killed a 9,992-char page that had **12 unused sub-headings inside it**.
- [x] **Back matter is kept but never indexed** (`indexable: false`) **and never cut** — our largest
  page in the library was a *bibliography*, indexed and retrievable as evidence.
- [x] **Furniture is not structure** — a document's own title is not one of its chapters; a heading
  that dominates its level is a PDF running header (≥4 occurrences AND ≥40% of the level).
- [x] **`libkb probe-granularity`** — Ekimetrics' loop, not their metric: theirs scores whether a chunk
  *looks* well-formed, ours scores whether the librarian *finds* it. Ground truth fixed OUTSIDE the cut
  (the source file) or a coarser cut wins for free. Verdict on AI-news: **`default` cut nothing.**
- [x] AI-News imported as its own domain — 116 pages, 3 shelves. Library now **231 pages / 3 domains**.
- [ ] **Decide: do the 138 AI-news files go into git?** (Retail is gitignored by D-020; this is not.)
- [ ] Re-ingest the mis-parsed PDF book — **destructive** (delete the book + its catalog rows first);
  needs the user to say so.
- [ ] `survey_folder` silently drops `.md` files at the ROOT of an imported folder. Right by luck here
  (`README.md`, `_TEMPLATE.md`); a flat folder of loose pages would vanish without a word.
- [ ] The **AI-textbook ⇄ AI-news collision** now has a price: `AI` loses **11.7%** of its top-1s to
  another domain (9× Retail's rate). Merge, rename, or accept — but no longer guess.
- [ ] `tight` granularity (500t) is a real trade: reading **4.5× cheaper**, R@1 **−6.3**. Refused for
  now — LOO regime. Settle it on the held-out set before believing either number.

## P3.8 — SESSION 8: a 2,000-page corpus, Qwen, and the first EXTERNAL numbers (D-043/D-044)
See `docs/SCORECARD.md` — the living measured-truth doc. All numbers there carry their regime + n.
- [x] Imported **MultiHop-RAG** (609 articles → 2,079 pages) into its own library (`benchmarks/multihop/`)
- [x] Wired **Qwen/DashScope** as a 2nd provider — route by model name, tool-calling Gemini-only,
  catalog locked to one embedder, UI model picker + `/model`, per-request `with_model`
- [x] **8 defects the big corpus exposed** (SCORECARD §7): title-twice, slug cap, 21% silent catalog
  loss, Qwen content refusal, **generate_json fail-open = P6 violation**, embed no-retry, DashScope
  no-timeout (30-min hang), FiQA empty-doc. ALL fixed; principle: fail CLOSED, never OPEN.
- [x] **`bench-multihop`**: text-index ≥ question-index on EVERY external metric, 0 generation cost
- [x] **`bench` (FiQA)**: first external number, **verified by pytrec_eval** — nDCG@10 0.621, R@10 0.701
- [x] **P6 at n=301**: 92.7% honest refusals (fail-closed). Measured at scale for the first time.
- [x] **Split the basket knob** (D-046/D-049) — `cascade_min_confidence` split from `cascade_max_pages`.
  Gate ships default-OFF (refuted on qwen — overconfident; 26/28 improvised nulls labelled "high").
  Basket raised to 10 anyway; honesty holds at 91% because it is bought by evidence, not self-report.
- [x] **`index_kind` configurable, default `text`** (D-045) — live library reindexed, held-out 96.7%,
  0 generation. Catalog locked to one representation (bug-6.6 guard). Flywheel kept for §5.1.
- [~] **CONCURRENCY** (D-047) — `libkb/concurrency.py::parallel_map`; **eval-multihop now 8-wide**
  (3h→15min). thread-safe token counter + `busy_timeout`. REMAINING: `runner.run_eval` + INGEST
  (needs a catalog write-lock). Backlog #1, half done.
- [ ] **Settle the vocabulary bridge** before retiring the flywheel — MultiHop says text wins, our
  colloquial-VI held-out says questions win R@1 83.3% vs 60.0%. Measure a colloquial set at n≫30.
- [ ] **BSARD** for later phases — 1,108 real citizen legal Qs, 6-lawyer labels, 22,633 hierarchical
  statute articles (FRENCH → text-index). The legal-domain + near-dup-flood benchmark. CC BY-NC-SA.

## P3.9 — SESSION 9: the scale question, answered (D-045…D-049) · see SCORECARD §1.1, §2.4
- [x] **The FiQA scale curve** (free, model-free): R@50/R@100 near scale-flat 2k→10k; R@1/R@10 collapse.
  The scale problem is the NARROW window, not the sieve. Retrieval IS scale-invariant if you read wide.
- [x] ~~**Cross-encoder rerank**~~ **REFUTED** (D-048): qwen3-rerank HURT FiQA R@1 5–9 pts at every
  scale — a strong embedder (gemini) leaves a reranker nothing to add. The de-facto reranker is the
  LLM triage; the lever is widening its window, not a cross-encoder. Joins NMS/BM25/digest/auto/gate.
- [x] **Retrieval DEPTH — 3 tiers** (D-049): `cascade_depth` minimum/default/deep (20/50/100), new
  defaults basket=10/fetch=50. MEASURED 73.9%→84.0% answer, honesty 92.7%→91.0%, 2.4× tokens.
- [x] **`answer_query_safe` fails CLOSED on any exception** + logs traceback — a bare TypeError would
  else 500 a real request. + the `{"basket": null}` slice-of-None fix.

## P3.7 — the remaining queue
- [x] ~~Cross-encoder rerank~~ — REFUTED above (D-048). The wider window (D-049) is the fix instead.
- [ ] Shelf hygiene (land separately): merge `Root Cause Analysis` + `KPI Interpretation`; split
  `Retail ▸ KPIs & Performance Analytics`
- [x] **Front door = the orchestrator's ROUTE decision** (D-061, not a separate classifier): greetings/
  meta → Concierge, compute → Calculator, else the cascade. Registry-driven, biased to cascade.
- [x] `synthesizer.py` (scan → map-reduce) — the AGGREGATIVE-question path the cascade's basket can't
  reach (MultiHop: no multi-hop past the basket). A registry ROUTE (D-061): router → aggregative-
  detect (lite) → wide scan → parallel lite MAP per page → strong REDUCE over compact findings, cited;
  empty harvest = honest NOT_FOUND. Defers to cascade on a single-fact question. 9 tests, ruff clean.
  UNMEASURED on purpose — needs an aggregative held-out set before believing it (SCORECARD backlog).
- [x] **Multi-turn chat history + context management** (the user asked "vẫn chưa có db lưu lịch sử
  chat nhỉ?"). Two mechanisms that keep the cascade SINGLE-SHOT: (1) `conversation/store.py` — a
  transcript store (conversations + messages, same gitignored db) that persists every turn; (2)
  `agent/contextualize.py` — a lite call that rewrites a follow-up ("tell me more about it") into a
  STANDALONE query BEFORE retrieval, so history never enters the expensive calls (the O(T²) trap the
  redesign avoids). `answer_query(history=…)`, `/api/query` threads a `conversation_id`, GET/DELETE
  `/api/conversations`; UI threads the id + a "New" button. Default-on knob `enable_context_rewrite`
  (no-op + free when there's no history — CLI/eval unchanged). 10 tests. Live-verified: "tell me more
  about it" rewrote to "…how reranking works in RAG?" and answered, same conversation threaded.
- [x] **`decompose.py` — query decomposition for COMPOUND multi-hop** (user asked how the system
  copes with "compare policy before vs after X, and which applies to Y"). Attacks the MEASURED cause
  (SCORECARD §2.3/§3: sieve has AllGold@20=93.5% but @3=29.6% — one blurred query can't rank all
  parts into a small basket; comparison/temporal stuck ~60-70%). A registry ROUTE: lite SPLIT into
  standalone sub-questions → SHARP parallel retrieve per sub-q (`parallel_map` = the Step-Functions
  Map fan-out, home-grown) → union → ONE combine call reasoning across the parts, cited; empty =
  NOT_FOUND. Cheaper than synthesize (no per-page map). Defers on non-compound (double-safe). Fixes
  the RETRIEVAL layer, unlike `triage_coverage` (D-051, refuted at the selection layer). 8 tests.
  Live-verified: a 3-part RAG question split → 3 sharp retrievals → 4-source cited comparison, and it
  HONESTLY flagged the part the corpus doesn't cover. **MEASURED & REFUTED** (SCORECARD §3.2, n=80,
  qwen-plus): vs the cascade baseline it LOST comparison 74.1%→63.0% and temporal 83.3%→66.7%; NOT
  starvation (at `per_q=6` it reads MORE than baseline and still loses, give-ups turning into wrong
  answers). The split-recombine throws away the joint signal a wide single-query basket keeps. Joins
  the measured-refuted list. **The route is now UNREGISTERED by default** (`enable_decompose_route`,
  `LIBKB_ENABLE_DECOMPOSE=true` to re-register) — the router cannot pick it and it costs nothing;
  engine + prompts + tests stay so the measurement reproduces. Added `force_route` knob (measurement,
  auto-enables routing).
- [ ] `trajectory/analyzer.py` — a failed walk names the description that lied; feed the view queue
- [~] Observatory UI wired to REAL traffic: KPIs (queries/answer-rate/honest-NOT_FOUND/avg-hops with
  real rolling sparks) + trajectories table + trace replay, from `GET /api/observatory` over the
  TrajectoryStore (new `reason`/`recent()`/`status_counts()`, `reason` logged per query). Live-verified
  (345 logged, 96% answer). REMAINING (need `analyzer.py`): misroute heatmap, suggested-fixes,
  eval-history chart — shown as a labelled PREVIEW, never fabricated numbers.
- [ ] Date-awareness in the catalog (recency + supersession) — fatal for a legal corpus with
  superseded articles; the sieve has no date column today

## P4.5 — MULTI-AGENT ARCHITECTURE (D-061, session 10) — see `docs/AGENT_ARCHITECTURE.md`
Home-grown runtime, conform to open protocols (MCP/A2A/AG-UI) — **no framework in deps**. Built +
tested (**203 tests**), NOT committed, all default-safe.
- [x] **Phase A — narration:** cascade emits read/compose + a first-person `thought` piggybacked on
  triage/answer (near-free). `ThinkingTimeline.tsx` — CoT timeline, live timer, auto-collapse, "hmm"
  escalation beats, NOT_FOUND terminal. Live-verified.
- [x] **Phase B — agent roles + registry:** `libkb/agent/roles/` (AgentCard A2A-shaped, AgentRegistry,
  Librarian/Answerer/Verifier). The cascade resolves librarian+answerer from the registry. `/api/agents`.
  Falsifiable test: a 5th agent registers + dispatches with **no orchestrator edit**.
- [x] **Phase C — MCP/A2A seam:** `libkb/tools/mcp.py` (MCP tool → CapabilityAgent + `ToolSpec`); `mcp`
  is an OPTIONAL extra. `/api/a2a/agent-card`. **C.2:** `calculator.py` — deterministic `safe_eval`
  (AST, never `eval()`), a dispatchable tool AND a compute route.
- [x] **Front-door routing:** the orchestrator decides the route per message (registry-driven, biased to
  cascade, fail-safe). Concierge (greetings/meta from persona + a TRUE overview), Calculator (compute).
  `LIBKB_ENABLE_ROUTER` default-off. Live-verified: a meta query answered directly, 0 cascade actions.
- [x] **Commit** the session (D-061 + narration + A/B/C + routing) — `0da0915`, 119 files, unpushed.
- [ ] Real MCP subprocess round-trip (needs `pip install -e ".[mcp]"`).
- [ ] LLM tool-calling INSIDE the answerer (mid-compose) — deferred (native tool-calling is Gemini-only).

## P4.9 — AGENT TOOLS OVER THE CANDIDATE POOL (D-066/D-067, session 13) — built, UNMEASURED
The scope rule: a method is a TOOL over the 50–100 candidates, never a change to the sieve.
- [x] `agent/pooltools.py` — `coverage_map` (parts → which candidate covers which → the hole → a
  greedy covering set) and `find_in_candidates` (literal/regex, returns the SECTION of each hit).
  Both 0 LLM.
- [x] `triage_mode=trace` — set-selection with the coverage map handed to it; same call count.
- [x] `triage_mode=agent` — ReAct loop over the pool + `ask_page`; budgets in CODE; forced-`select`
  close-out; falls back to shipped triage if it still selects nothing.
- [x] Tool calling on DashScope (the Gemini-only refusal removed) — **verified live on qwen-plus**.
- [x] 28 LLM-free tests + `tests/llm/test_tool_calling.py -m llm` (4/4 live).
- [ ] **RUN the arms.** `probe-selection` now has 9; none has run. Then the cheap-tier question:
  does `agent` hold up on qwen-plus at 6× less?
- [ ] If `agent` wins: wire the tool trace into the UI timeline (the events already exist).

## P4.8 — HYBRID BM25, RE-TRIED AND CLOSED (D-065, session 13) — see SCORECARD §2.5
D-032 refuted BM25 fusion on two query sets that were adversarial to BM25 by construction. Fair
challenge; re-run properly.
- [x] `libkb/evals/lexical.py` — BM25 as SQLite FTS5 would run it (k1=1.2, b=0.75, `unicode61
  remove_diacritics 2`, no stemming), RRF, a rare-term gate, and a **complementarity** report.
- [x] `beir.score_rankings()` split out so dense/BM25/hybrid are scored by literally the same code.
- [x] `libkb probe-lexical` — FREE (cached vectors, 0 generation). Two built-in correctness checks.
- [x] **RUN on FiQA.** D-032 replicates (−0.18 nDCG@10); stopword filtering +0.001; rare-term gating
  −0.004; BM25 finds **0.6%** of gold that dense misses at k=100 → no complement to escalate to.
- [x] 25 LLM-free tests. `hybrid_shortlist` stays OFF, now on external evidence.
- [ ] ~~Fix the FTS source (it indexes an empty column under a text index)~~ **DROPPED** — it would
  only make a dead signal reachable. Revisit only with an identifier-dense corpus (article numbers,
  SKUs, error strings), which is a different population and the one lexical search exists for.

## P4.7 — THE SELECTION LAYER (D-064, session 13) — built, UNMEASURED
The step the project is named for is the one that loses: triage keeps 69% of the gold, the
embedder's own top-10 keeps 75% (probe 2c). A reranker is not the fix — refuted (D-048). So attack
the axes a reranker never touched: what the selector SEES, and what it is ASKED.
- [x] **Tier 0 — `triage_card=rich`** (`cascade.build_card`): `triage_passages` query-relevant spans
  instead of one, passage AND matched catalog row together, section titles whose *body* overlaps the
  query marked `▸`. Model-free (`query_passages`, `relevant_sections`); zero new LLM calls.
- [x] **Tier 2 — `triage_mode=set`** (`cascade._triage_set` + `prompts/select_set.md`): one call over
  the same cards asking for a COVERING SET; each pick states what it adds; `missing` names the hole.
  Section naming kept (D-053's `read` lost partly by taking whole pages).
- [x] **The deciding experiment — `libkb probe-selection`** (`evals/selection.py`): arms
  `embedder|headers|rich|set|set+rich|read` over ONE shared candidate pool; headline metric
  **retention**; preflight prices the run on 3 real pools and stops without `--yes`. 25 LLM-free tests.
- [x] SCORECARD reconciled with D-048 (§5 and the backlog still called the reranker "not run").
- [ ] **RUN THE ARMS.** Nothing above is a claim until this produces a column of numbers. Then either
  flip a default and confirm on `eval-multihop`, or write the null result down and go to Tier 3.
- [ ] Tier 1 (setwise) deliberately skipped — k calls vs one; revisit only if Tier 2 wins but is noisy.
- [ ] **Tier 0b** — ingest-time contextual summary (real Contextual Retrieval, moves the SIEVE not the
  selector) · **Tier 3** — IRCoT loop + note compression, gated by a CRAG-style evaluator.
- [ ] FiQA *selection* vs qrels — needs a `load_fiqa` loader; the probe is dataset-agnostic by design.

## P4.6 — PRODUCT SESSION + PUBLISHED (D-062) — see SCORECARD §3.2
Product-level capabilities, then a public release.
- [x] **Multi-turn chat + history** — `conversation/store.py` (transcripts, same gitignored db) +
  `agent/contextualize.py` (a lite call rewrites a follow-up into a STANDALONE query BEFORE retrieval,
  so history never enters the expensive cascade — the O(T²) trap the redesign avoids). Sidebar: title =
  first question, editable/deletable, pin ≤5. `enable_context_rewrite` default-on, free with no history.
- [x] **Semantic answer cache** (`cache/`) default-ON — a grounded, confident answer returns for a
  paraphrase with **0 LLM calls**. Honesty rules: never cache NOT_FOUND / uncited / low-confidence;
  precision-first threshold **0.92** (a cross-topic near-neighbour sits at 0.875). Curatable + toggle in
  the Observatory. Transparent ("from cache" + citations).
- [x] **Synthesis route** (`agent/synthesizer.py`) for aggregative questions — registry route, wide scan
  → parallel lite MAP → strong REDUCE, cited; empty = NOT_FOUND. **UNMEASURED on purpose** (needs an
  aggregative held-out set; SCORECARD §5.6).
- [x] ~~**Query decomposition**~~ **BUILT, MEASURED, REFUTED** (SCORECARD §3.2). Split→retrieve-per-part
  →combine lost comparison 74.1%→63.0%, temporal 83.3%→66.7% on qwen-plus, and NOT from starvation. The
  split discards the joint signal a wide single-query basket keeps. UNREGISTERED by default
  (`enable_decompose_route`); engine + prompts + tests kept so it reproduces. Added `force_route` knob.
- [x] **Observatory wired to REAL traffic** — KPIs + trajectories + trace replay from `GET /api/observatory`
  over the TrajectoryStore (`reason`/`recent()`/`status_counts()`). REMAINING: analyzer-driven misroute
  heatmap + suggested fixes (shown as a labelled PREVIEW, never fabricated).
- [x] **PUBLISHED** — repo public at `github.com/LeDat98/toshokan_kb`, **PolyForm Noncommercial 1.0.0**
  (source-available; MIT intended later), measured-numbers README. The private-client, retail,
  ai-news, benchmark and eval data + the proposal deck gitignored and **verified absent** (D-020).
- [x] **Client data pulled out of the repo (housekeeping).** `library/domains/<client>/` moved to a
  sibling folder outside the project; the `.gitignore` entry that named the client removed. Tracked
  tree is now client-name-free. (Name persists in older git history on the remote → history-rewrite is
  the user's call.)
- [~] **A cost-accounting feature was built this session, then REMOVED at the user's request** (billing
  must not reach the public repo). Its removal also dropped the cache-off-in-eval fix, so that
  eval-integrity bug (a re-run replays cached answers to the judge, inflating the score) is live again
  — re-apply as a standalone correctness fix if wanted. Incident recorded only in the gitignored
  `.agent/private/COST_LEDGER.md`.

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
