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

## 2026-07-12 — P2c question flywheel + card catalog (session 6, Opus)
- Long design chat first: user pushed on the hard product question — at 10⁷ pages, does the librarian
  pick the right book, what does the embedding model actually do, and can we beat PageIndex. Reframed:
  the tree walk keeps each menu ~O(branching), so the real levers are per-hop accuracy (p^d), balanced
  tree, and recovery (backtrack/beam). Corrected the number — PageIndex/Mafin 2.5 is **98.7%** on
  FinanceBench (per-document), and our edge is exactly what they lack: a learned question flywheel,
  hybrid embedding-shortlist, and eval-gated maintenance. That motivated building P2c.
- Built the flywheel + catalog: `ingest/questions.py` (bilingual 4×2 questions/page + index_page),
  `catalog/{db,store,search}.py` (SQLite WAL, brute-force cosine, embeddings as shortlist not backbone
  — D-022), `ask_librarian` tool (budgeted, hints not teleport), orchestrator answerer-gated shortcut
  (D-023). CLI `reindex`/`--index`/`--no-index`; API `/query` shortcut + index-on-ingest/approve.
- **Verified live twice on gemini-3.5-flash**: reindex AI → 240 questions/30 pages; a reranking
  paraphrase answered via the shortcut in **0 hops** with the right citation; an off-library turbo
  question declined the shortcut, used ask_librarian twice (budget held), and honest-NOT_FOUND'd after
  10 hops. The "no walk needed for a known question" and "hints don't fabricate" stories both work.
- 11 new LLM-free tests (catalog CRUD/search/lookup, question expansion, index_page idempotency,
  ask_librarian budget, shortcut gating) — 66 total green; ruff clean; app exposes all 10 routes.
- Gotcha: `check_same_thread=False` on the sqlite connection so the API's worker threads (D-018) can
  read the catalog; orchestrator closes any catalog it auto-opened (no per-query connection leak).
- Handoff: P3 — the generated questions ARE the routing eval set; build `evals/runner.py` + `libkb
  eval` to measure top-hop + end-to-end accuracy (the real "beat 98.7%" number) and to CALIBRATE
  `catalog_shortcut_threshold` (0.82 is a guess). Then classifier/synthesizer + Observatory.

## 2026-07-12 — P3 eval slice (session 6, continued)
- User: "reindex nốt + chạy P3 luôn". Reindexed the Retail domain → catalog now 920 questions / 115
  pages (AI 30 + Retail 85). Then built the first P3 slice: `libkb/evals/` (dataset samples the catalog
  = the flywheel doubles as the labelled eval set, D-024; runner scores by deepest level reached
  page⊃book⊃shelf⊃domain⊃miss; three modes walk/assisted/shortcut; gates) + `libkb eval`. 8 LLM-free
  tests; 74 total green; ruff clean.
- **First live baseline** (`eval --limit 8 --mode walk --seed 7`, leak-free pure routing, AI+Retail):
  page **75%** · book 75% · shelf 87.5% · domain 100% · found 100% · avg 4.6 hops / 1.0 backtracks.
  6/8 bullseye; the 2 misses stayed in the right domain (one right shelf, wrong book). Gate FAILs on
  the placeholder min_book_acc=0.80 — that's the gate working, not the system; recalibrate off a bigger
  sample. Notable misroute: a vi question on inventory-days↔turnover landed on a sibling page (FOUND but
  wrong book) — exactly the kind of signal the P3 trajectory analyzer will turn into a description/alias fix.
- **Stable baseline** (`eval --limit 50 --mode walk --seed 7`, superset of the n=8 pilot): page **86%**
  · book 86% · shelf 96% · domain **100%** · found 90% · avg 5.3 hops / 2.1 backtracks. **Gate PASS.**
  The n=8 75% was small-sample noise. Misroute analysis (7/50, all in Retail): every miss stayed in the
  right DOMAIN; 5 reached the right shelf but wrong BOOK (sibling-book confusion), 2 only domain-level.
  Misroutes correlate with long thrashing walks (two hit 12 hops / 7–10 backtracks) → the librarian
  wanders when neighbouring books' descriptions aren't discriminative. Concrete offenders: the three
  "Inventory & Demand Planning" books (Homecenter Inventory Patterns vs Inventory Management vs Demand
  Planning) and the KPI Dictionary vs KPI Interpretation split. vi questions slightly over-represented
  in misses (4/7). This is exactly what P3's trajectory analyzer + view-regeneration (D-004) should fix.
- Handoff: calibrate the 0.82 shortcut threshold + gate minima off this baseline; compare `--mode
  shortcut` vs walk to quantify catalog lift (leak caveat); add a held-out/paraphrased set; then
  trajectory logger → discriminative-description regen → classifier → synthesizer → Observatory.
  `eval` exit code 2 = gate fail (for CI); exit 0 = pass.

## 2026-07-12 — Description root-cause, shortcut lift, and a model-cost experiment (session 6, cont.)
- **Shortcut-mode eval**: 100% every level, 0 hops. Correct but LEAKY (cases come from the catalog,
  D-024) — it proves the flywheel nails a question it has seen and answers it in ~2 calls, no walk.
- **Root-caused the sibling-book misroutes** and fixed them properly (D-025): `rebuild_description`
  only ever regenerated root/domain/shelf, so imported books kept the placeholder
  `"7 topics: <first 3 page titles>…"` — two inventory books read identically, so the librarian
  thrashed (12 hops) and picked wrong. A book IS a non-leaf whose children are its pages ⇒ it's a view
  too. Extended views to books, added `rebuild-views --domain`, regenerated Retail (17 descriptions).
  They now discriminate AND cross-point ("for EOQ/safety stock, see *Inventory Management*"). 3 tests.
- **Model cost experiment** (user flagged ~$10–15/day): switched everything to `gemini-3.1-flash-lite`
  (D-026) and re-ran the same 50 cases → page **54%** vs **86%**. A 32-point collapse — and that was
  *with* the improved descriptions helping it. The trace stats diagnose it precisely: backtracks
  2.1 → 0.4, hops 5.3 → 3.4, found-rate UP 90% → 96%. **The lite model stops deliberating**: it grabs a
  plausible page and declares FOUND instead of reconsidering — confidently wrong. Reverted to the
  two-tier split D-003 always intended (D-027): strong model navigates/answers; flash-lite runs bulk
  **question generation** (1 call/page — the biggest one-off cost). Embeddings unchanged.
- **Left unmeasured (deliberately, to stop spend):** strong-model + NEW descriptions — the D-025 A/B.
  We have 86% (strong+old) and 54% (lite+new); the (strong+new) cell is missing. One 50-case walk closes it.
- Gotchas: (1) a *background* PowerShell command starting with `.venv\` dies with "The module '.venv'
  could not be loaded" — use the Bash tool for background runs; (2) "fixing" that by calling python via
  an ABSOLUTE path breaks `.env` loading, because `Settings` reads `.env` relative to the CWD.
- 77 tests green; ruff clean. Handoff unchanged, plus: close the description A/B first — it is the one
  experiment whose result we paid for but didn't collect.

## 2026-07-12 — The user's best question broke the catalog gate (session 6, cont.)
- User asked the sharp one: *does generating questions at ingest actually help?* The question space is
  unbounded, so a catalog can only ever match near-paraphrases — is this real, or theatre? I had to admit
  the shortcut's 100% score proved nothing (it was leak-by-construction) and the real generalisation
  number had **never been measured**.
- Measured it for **FREE** — no LLM calls, pure cosine over vectors already in the catalog. Built
  `evals/catalog_probe.py` + `libkb probe-catalog`. On the live 920q/115p catalog: LOO (paraphrase)
  **70.9%** top-1 page, LOI (a question we never thought of) **39.3%**. And the killer: top-1 cosine
  **crowds at 0.88–0.90**, so the shipped absolute gate (0.82) fired on **99.9%/92.6%** of queries at
  **70.9%/40.1%** precision ⇒ est. end-to-end **71%/43%** — **WORSE than the 86% of having no catalog**.
  The shortcut we shipped was actively HARMFUL. The user's instinct was right and my gate was wrong.
- Fix (D-028): gate on the **MARGIN** over the runner-up PAGE, not absolute cosine. `catalog_margin=0.05`
  → LOO fires 34% at **95.5%** precision (est 89.3% > 86%); LOI fires only **12.6%** (est 84.2% ≈ neutral).
  The catalog now **knows when it doesn't know**. `ask_librarian` keeps NO margin gate (hints may be
  uncertain; the walk verifies them). 3 new tests; 80 green.
- Bonus measurement: the **vi↔en bridge is real** — a VI question finds its page from EN-only rows
  **98.3%** of the time. Storing both languages is largely redundant (a free ingest-cost halving).
- Lesson to carry: an absolute similarity threshold on a modern embedding is meaningless — everything
  scores ~0.9. Always gate on a RELATIVE signal (margin / rank gap), and always probe held-out before
  believing a retrieval component helps. The probe is free; there is no excuse not to run it.
- Handoff: the flywheel's supply side (guessed questions) is a cold start and cannot cover the tail —
  build the **demand side** (P3 trajectory logger: log real queries + resolved page, index those). That
  is what actually makes the catalog earn its keep.

## 2026-07-12 — Routing redesign: the book stops being a decision (session 6, cont. · D-029)
- User brought `docs/ROUTING_REDESIGN.md` — their own review/analysis pass. It is the sharpest artifact
  in the repo so far. I re-derived every number from scratch (`evals/separability.py`, a fresh
  implementation) and **reproduced them exactly**: 904 decisions, 82.3% sibling-book separability,
  route A 68.3% vs route B 76.4%, 91 rescues / 17 losses, +8.2%. The evidence survives independent check.
- The insight I had missed: decompose the 86% baseline into CONDITIONAL per-hop accuracy and the whole
  14-point loss sits on **one hop** — shelf→book (89.6%). Page-picking inside a book is already **100%**.
  And it cannot be fixed by writing better descriptions: sibling books are only 82.3% separable by their
  own CONTENT, so the LLM+descriptions (89.6%) is already beating the tree's intrinsic ceiling. RCA ⇄ KPI
  Interpretation confusing each other in BOTH directions is one book split in two — no prose fixes that.
- Mechanism (the real argument): `open_book` is an irreversible commitment. Wrong book ⇒ the right page
  is in no menu the agent can see; the only escape is the 12-hop thrash we kept logging. `open_shelf()`
  never commits. It is also the librarianship answer — a real librarian scans the whole shelf's TOCs at
  once. And vs PageIndex: their 98.7% is WITHIN one document; they have no book hop at all. We weren't
  losing on depth, we invented a lossy commitment. **Compete by having fewer committed decisions.**
- Fixed the 4 prerequisite bugs first (two corrupt the eval): score_case didn't credit ancestors of
  touched nodes; **hop-budget exhaustion threw away pages already read** (a product bug — the librarian
  read the answer then discarded it); `_scan()` cleared the index in place under worker threads;
  `_resolve_child` matched substrings both ways with first-in-dict winning. Gates raised 0.55→0.78.
  One old test FAILED and was right to: it had encoded bug #1 ("visiting ai/llm = miss" — no, reaching
  LLM means you reached the AI domain).
- Shipped `routing_mode=shelf` (default) + `open_shelf` + `route_shelf.md` + scale guard; `book` mode
  kept alive for the A/B. 89 tests green. Live smoke: the vi inventory question that used to misroute
  now answers in 3 hops / 0 backtracks with a correct citation.
- **Caveat discovered in the smoke, important for reading the A/B:** the eval's ground truth is the page
  a question was GENERATED from — but a DIFFERENT page can answer it perfectly (the smoke read
  "Inventory Turnover" instead of "Inventory Days" and was completely correct). Strict page-identity
  scoring UNDERSTATES real quality. Don't over-trust a small delta either way.
- Handoff: run the A/B (`LIBKB_ROUTING_MODE=book` vs `shelf`, same seed, same cases) — it is the only
  thing that settles this. Prediction to falsify: page_acc UP **and** hops/backtracks DOWN.

## 2026-07-12 — The user reviewed the redesign and found 2 blockers + a bad metric (D-030)
- The A/B I was about to run would have been rigged **against** the design it was testing. The user's
  own review pass (`docs/ROUTING_REDESIGN.md` §0a/§2.5/§3.0) caught it. Everything below is free.
- **`one_line` was 8x its budget, and I had walked past it twice.** MEASURED over all 125 live TOC
  entries: median **1013** chars, max **1436**. `library/models.py` has had `one_line_of()` all along;
  `ingest/survey.py` simply wasn't using it — it copied each source file's whole frontmatter
  `description:` (an abstract) into `TOCEntry.one_line` (a spine label). Retail only; the hand-written
  seed is fine (max 160). A menu is **resent on every later turn**, so this taxed every hop — and when
  every option is a 1000-char paragraph, *everything sounds relevant*, which is exactly the
  ambiguous-boundary failure Lu et al. name as the cause of LLM mis-selection.
  Capped at **render** (all three renderers — never trust the stored value, so the live library is
  fixed with **no migration**) and at **ingest** (the source), plus `views.py` prompts and the API TOC.
  **MEASURED: union-TOC menus 28,032 → 6,319 tokens (−77%);** worst shelf 14,221 → **2,584** (−82%).
  The doc's independent estimate (13,999 → 2,364) was accurate.
- **The scale guard counted the wrong unit** — rows, not tokens. The KPIs shelf (50 pages) sailed
  through a 60-row guard while emitting a 14,221-token menu. Kept BOTH ceilings, because they are
  different failures: rows bound the option count (an LLM can't rank 200 titles however short), tokens
  bound the cost. Note the ordering trap: had the token guard shipped **without** the cap, that shelf
  would have fallen back to book mode — and route B would never have been tested on the one shelf it
  exists to fix.
- **The metric was punishing route B for being right.** `page_acc` asks "did you reach the exact page
  the question was generated from". Route A picks among ~8 pages inside a book; route B sees ~42 at
  once, so it far more often lands on a **sibling page that answers perfectly** — scored a MISS. I had
  *observed* this in the last session's smoke (answered from "Inventory Turnover" instead of
  "Inventory Days", completely correctly) and written it down as a caveat instead of fixing it. Now:
  `answer_acc` — an LLM judge over the final answer on `model_lite`, told to judge the answer and not
  its provenance — is the primary metric; `page_acc` is a diagnostic. `mean_input_tokens` is reported
  too, turning §2.4's cost model into a measurement. Every eval mode now runs through `answer_query`,
  so what gets graded is the answer a reader would actually have received.
- **Disarmed the gates.** I had *raised* them to 0.78/0.80 last session, feeling responsible. They were
  calibrated in book mode, on the leaked set, against `page_acc` — all three premises are now false. A
  stale gate is worse than no gate: it fails honest work and waves through real regressions.
- Built `libkb make-holdout` (paraphrase each question the way a reader who never read the page would
  ask it; **save it to disk** so both arms score byte-identical questions). Not run — it costs tokens.
- 104 tests green (89 → +15), ruff clean. **Next: the A/B, and it is the one thing that settles this.**

## 2026-07-12 — The A/B: route B won on every axis (D-031)
- Ran it exactly as §3.1 specified: `make-holdout` (30 questions restated on `model_lite` the way a
  reader who never read the page would ask them, saved to disk so both arms score byte-identical
  input), then two `--mode walk` arms on the same file. `evals/` gitignored first — the questions are
  generated FROM the private retail corpus (D-020), so they carry private content.
- **book → shelf: answer_acc 90.0% → 96.7%, page_acc 66.7% → 80.0%, hops 5.2 → 4.3, backtracks
  2.1 → 0.9 (−57%), tokens 53,941 → 49,120.** Paired: **6 rescues, 0 losses.** Not one regression.
- The falsifiable prediction (accuracy UP **and** hops/backtracks DOWN) held. Gate armed:
  `min_answer_acc=0.90`. `min_page_acc` deliberately left None — gating it would punish the system
  for answering correctly from a sibling page.
- **Where I must not oversell:** the accuracy delta is **2 flipped cases**; McNemar p≈0.5. At n=30 it
  is not significant on its own. What actually carries the conclusion is convergence — the free
  904-question centroid proxy (+8.2%), the backtrack collapse (the *direct* fingerprint of the
  premature-commitment mechanism), and 0 losses. Three independent measurements, one story.
- **Two surprises, neither of them in the plan:**
  1. **§2.4's cost model was wrong by 7x** — it predicted −63% tokens, reality is −9%. It modelled the
     *menu*, but after the D-030 cap the menu is ~2.5k of a **~50k** bill. The real driver is the
     **pages the librarian reads** (2.1–2.3 per walk, full markdown, resent on every later turn).
     That is now the biggest untouched lever in the system. Nobody had looked at it. The cost case for
     route B was therefore never the point — accuracy and thrash were.
  2. **The leak was worth ~20 points of page_acc.** Held-out book-mode page_acc is **66.7%**, not the
     86% we had been quoting. Strip the generator's jargon and routing gets much harder — the old
     number was measuring memory. But `answer_acc` is 90%, so the system was serving readers far
     better than page_acc ever admitted. Both facts were invisible until the metric was fixed.

## 2026-07-12 — PART II built; two more of the doc's recommendations died on contact with a probe
- Order of work taken from §9. Every claim reproduced BEFORE building. 137 tests green.
- **`routing_mode="auto"`: dropped, on the doc's own test.** §9 asked how many A/B cases even landed
  on a well-separated shelf. **9 of 30** — and shelf mode lost **0** of them; on `Merchandising`
  (92.7% separable) flattening actually *improved* things. There is no cow to build a fence around.
- **§8.1 cross-references: reproduced EXACTLY (56/115 = 49%, top delta +0.078)** — but only after
  finding the pooling the doc used, which is §7.2 applied consistently: a page is ONE topic (mean of
  its vectors), a book is a UNION (max over its rows). Max on both sides gives 58% and inflated
  deltas. Shipped as `probe-misshelved` → `build-crosslinks`. The link is written on the book a
  reader would *search*, pointing at the page that lives *elsewhere* — the reverse of what feels
  natural, and the only direction that rescues the walk that would otherwise fail.
  **The dry run caught a privacy bug I would have shipped:** a link from a *tracked* AI book to a
  *private, gitignored* Retail page — a private page title, into git. Cross-domain links refused.
- **§7 shortlist: shipped, and the test written to enforce §7.4 caught me violating §7.4.** In shelf
  mode `open_book` was an alias for `open_shelf`, so on a too-wide shelf the escape hatch looped
  straight back into the shortlist. The menu *promised* an exit that did not exist. That is precisely
  "a shortlist the librarian cannot escape is `open_book` all over again" — I had rebuilt the trap
  while implementing the section that forbids it.
- **§7.3 hybrid BM25: MEASURED AND REFUTED.** Textbook-correct reasoning; the mechanism is even real
  (a unit test shows BM25 rescuing "GMROI" from an embedder blind to it). But fused into retrieval it
  loses on BOTH query distributions, at EVERY fusion weight, monotonically — generated-question LOI
  page R@10 90.7% → 78.6%; held-out colloquial paraphrases R@1 83.3% → 43.3%. A reader's paraphrase
  reuses almost none of the library's exact words, so BM25 grabs the common ones and drags noise up.
  Kept behind a flag; the day real traffic shows SKU codes and rare terms, switch it on and re-probe.
  (While measuring, found the FTS index had been silently EMPTY: `count(*)` on an external-content
  FTS5 table is delegated to the content table, so it reported every row as indexed when none was.)
- **§6 page digest: shipped, but the doc's cost diagnosis was wrong.** It called page text "the
  largest untouched lever", reading the 49k bill as "2.5k menu + 46k pages". A menu is resent every
  turn too: menu 2,707 × 5 = **13,535, i.e. 49% of the bill**; pages ≈30%. Digest is worth −8%;
  §0a's spine cap was worth −62%. Per-turn it does exactly what it should (the conversation stops
  growing and plateaus) — but the first eval cases show the librarian then reads MORE pages, which is
  the risk §6 itself named. The aggregate is what settles it.
- **§8.2 entry vocabulary: built, deliberately UNMEASURED** (term ring in the same generation call,
  `kind='term'` so it can be A/B'd rather than quietly mixed in). After two refutations, a new
  retrieval signal does not get shipped on theory.
- **§8.4 trajectory logger: shipped — and it is the real answer to the founding worry.** Generated
  questions cover an unanticipated intent 39.3% of the time at top-1. They were never meant to be
  enough; they are the cold start. `libkb harvest` feeds real (question → landed page) pairs back in.

## 2026-07-12 — PART II eval: accuracy held, cost regressed 17%. The digest is off. (D-033)
- Same 30 held-out questions, same shelf routing, everything from PART II on.
  **answer_acc 96.7% → 96.7% (Gate PASS). Tokens 49,120 → 57,667 (+17%).** Hops 4.3 → 4.5.
- **The page digest — whose only purpose was to cut cost — made queries dearer.** And the mechanism
  is right there in the log, turn by turn. With it on, a walk's per-turn input **plateaus**
  (8,009 → 8,525 → 8,531 → 8,426 → 8,919) where before it **climbed** (4,999 → 7,018 → 8,644 →
  10,941 → 13,660). The compression does exactly what it was designed to do. But the librarian,
  robbed of the full text, **compensates**: 6 pages read instead of 5 — hitting `max_pages_per_nav` —
  and 13 turns instead of 11. The saving is eaten by the behaviour it induces.
  §6 wrote its own falsifier for this ("what it could cost is the navigator's own *have I got
  enough?* judgement") and that is precisely what it cost. Defaulted to OFF. Code, tests, knob kept.
- **A real bug, found by reading the eval log rather than the code:** `read_page` had no re-read
  guard. A page read twice went into the evidence twice — `compose_answer` would see one source as
  two — and burned a second slot of the page budget. Harmless until now; a live trap the moment the
  digest exists, because digesting a page is exactly what makes the librarian want it back. A
  re-read is now free: full text returned, no budget slot, no duplicated evidence. That attacks the
  compensation mechanism head-on and is the one change that might make the digest pay. It is
  unmeasured, so the digest stays off. Hope is not a measurement.
- **What I must not claim:** the +17% is not attributed. The bundle was evaluated as a bundle, and
  cross-references (which add readable pages to a menu) and a longer prompt are in it too. The digest
  is the prime suspect on mechanism, not on arithmetic. An isolation run — 30 walks — would settle it.
- Standing count for the session: of the doc's recommendations, **three were refuted by measurement**
  (hybrid BM25, `routing_mode="auto"`, the page digest) and every one of them was theoretically
  sound. The discipline earned its keep three times.

## 2026-07-13 — The user tore the architecture down, and he was right (D-034)
- *"The whole knowledge base is ~200k tokens and one answer burns 50k — a quarter of the corpus.
  This librarian is not professional; he is wasteful."* He was right, and I had been patching around
  it for a full session. **The agentic tree-walk is the wrong shape of machine.**
- **The number that ends the argument:** a walk sees **8,601 tokens** of distinct information and we
  pay **45,268**. Four fifths of the bill is rent on things already seen. Every turn resends the
  whole conversation → O(T²). It explains everything: the spine cap won (−62%) because it shrank a
  thing multiplied by T; the digest lost (+17%) because it attacked a symptom. **You cannot patch
  your way out of a quadratic.** I should have measured "distinct vs paid" on day one.
- **Then a theorem finished it.** Zhuo et al. (ICML 2020): greedy/beam tree descent is **not
  Bayes-optimal even with perfectly trained node scorers** — a wrong turn at depth 1 is
  unrecoverable. That is D-029, generalised. We deleted the book hop; the theorem says the descent
  itself was the disease.
- **And I had to eat a claim I made two messages earlier.** I told the user the tree "prunes 79% of
  the library for free". It does not. To score a container by max you must first score every page in
  it. The sound version (cone bounds) dies exponentially in dimension — which is why the ANN field
  abandoned trees for HNSW. **The hierarchy is for citation, curation and people. It is not a search
  accelerator.** (Nearly shipped a worse bug: the *element-wise* max of leaf vectors is not an upper
  bound at all — fails 80.8% of the time. Verified before anyone "optimised" it.)
- **PageIndex — the thing we set out to beat — does not walk either.** Read from their source: 2 LLM
  calls, whole tree in one prompt, no embeddings, no agent, no rollback. The MCTS is marketing. And
  their 98.7% is soft — **their own judge scores 136/150 = 90.7%**; the rest is humans re-labelling
  misses. **Our 96.7% already beat their honest number.** We were losing on architecture only.
- **The user then supplied the structural insight himself:** don't read a page to decide you didn't
  need it — read its description, keep it in a *basket*, open the basket at the end. The reason it
  works is where the text SITS: in the navigator's conversation a page is re-billed every turn; in
  the answerer's call it is billed once. **Don't read-then-shrink. Don't read.**
  (His 2.7× estimate was optimistic — measured, section-reading alone is −21%, because page text is
  only 30% of the bill. But the *structural* half of his idea is worth far more than the arithmetic.)
- **Shipped the cascade** (propose → triage on section headers → open the basket once → expand only
  if insufficient). **Live smoke: 2 calls, 2,462 tokens vs 49,120 — 20× cheaper** — correct answer,
  citing two *different shelves*, which the walk could only have reached by backtracking.
- **A fourth theoretically-sound idea died on measurement:** I proposed NMS/diversification for the
  user's (correct) worry about near-duplicate documents flooding the list. **It costs 10 points of
  recall** (96.7% → 86.7%) — it suppresses the right page for being *similar to* a good one, and that
  similarity was corroboration. The answer to his worry is dedupe at ingest and K=3, not filtering.
- Running the A/B on the same 30 held-out questions now. Prediction to falsify: **answer_acc ≥ 96.7%
  at ≤ 15k tokens and ≤ 3 calls.**

## 2026-07-13 — The cascade's A/B, and three bugs that decided it (D-035)
- First cascade run: **83.3% vs the walk's 96.7%**, at **2,010 vs 49,120 tokens**. The prediction in
  RETRIEVAL_REDESIGN §6 was **falsified**. Before accepting it, I asked the one diagnostic question
  that mattered: **did the SIEVE fail, or the ORACLE?**
- **In all four losses, the sieve had ranked the target page #1.** Every time. So the embedder was
  never what lost — three bugs were, and two of them were in the measurement.
  1. *(mine)* On "insufficient", the code went looking for **other pages** — throwing away the one
     the sieve had ranked #1 because it had been opened at the wrong chapter. Now it **re-opens what
     it holds, in full, before widening.**
  2. *(mine)* The triage prompt **taught the librarian to give up**, and his card was thin. He
     returned an empty basket on a page ranked #1 at cosine **0.845**. The card now carries the
     catalog question that MATCHED — a signal that was sitting unused in `Hit.text`.
  3. **The judge failed a BETTER answer.** The cascade hands the answerer pages from across the
     library — its whole advantage. The judge saw one reference page, found "external concepts", and
     marked it wrong. Case 13 gave the reference's own point **plus** a correct second point from
     another page and was graded incorrect **for being richer**. Fixed: *the reference is a floor,
     not a fence.* Re-judged: **2 of 4 flip.**
- **Third time this session the METRIC was the broken thing.** Each time, finding out cost a full
  re-run — walks included. So `libkb eval --save` now persists every answer and `libkb rejudge`
  re-grades a saved run for almost nothing. The answers are the expensive artifact. This should have
  existed since the first eval; I built the grader before I built the ability to re-grade.
- **The fair A/B (same judge, same 30 questions):** walk **93.3% / 66,558 tok**; cascade
  **86.7% / 4,312 tok** — **15.4× cheaper**. And the cascade **routes better**: page 86.7% vs 73.3%,
  book 90.0% vs 83.3%, shelf 96.7% vs 93.3%. Its entire deficit was that it **GAVE UP** —
  found_rate 90% vs 100%.
- **And two of the three give-ups were standing on the exact target page.** The sieve found it, the
  triage basketed it, and the answerer said "insufficient" because it was handed one page where the
  walk would have handed it three. **A librarian may not declare the library empty while the closest
  pages sit unread on his desk.** Added the last resort: before any NOT_FOUND, open the top
  candidates in full and look once more. Only then is the not-found honest (P6).
- **A caution about the numbers themselves.** The walk moved **96.7% → 93.3%** and **49k → 66k
  tokens** between two runs of the *same* 30 questions. Its run-to-run spread (±3.4 pts) is about the
  size of the lead it is defending. A 9–13-call machine has 9–13 chances to wander, and pays
  quadratically for each. The cascade's spread is ~1%.

## 2026-07-13 (evening) — Ingest becomes a rule; the AI-News corpus lands (D-037, D-038)
- The user pushed back on my proposed fix for the AI-news frontmatter (`summary:` vs `description:`):
  *"if every new document type needs a code change, that is not a product."* He was right, and he
  pointed at Ekimetrics' `adaptive-chunking` — run a verify metric, let the corpus pick the cut.
- Separated two things that looked like one: the frontmatter problem is **schema mapping** (solved by
  the ingest contract — generate what the source didn't give, in the call already being made, for
  free), and the real chunking question is **leaf granularity**, which we had never measured at all.
- Read the parse layer as he asked. It was worse than either of us thought, and none of it was a
  "document type" problem: `split_document` picked ONE heading level for a whole document and never
  recursed (a 9,992-char `3 Methodology` page with **12 unused sub-headings inside it**), and our
  **largest page in the library was a bibliography** — 13,136 chars, indexed, embedded, retrievable
  as evidence. Both are a missing base case.
- Rewrote `split.py` as one recursive rule (structure → recurse → size only as a last resort → merge
  strays). Two guards earned from real files: back matter is kept but never indexed *and never cut*
  (the size-splitter renames pieces `… (3/6)`, which the apparatus filter stops recognising — that is
  how a bibliography walks back into the catalog); and **furniture is not structure** — a document's
  own title is not one of its chapters, and a heading that dominates its level is a PDF running
  header, not a chapter.
- Built `libkb probe-granularity`: their loop, not their metric. Fairness is the trap (a coarser cut
  scores higher for free), so the ground truth is fixed OUTSIDE the cut — the source file.
- **The probe's verdict on AI-news: `default` is byte-identical to `as-authored`. The rule cut
  nothing.** That is the result a generic rule should produce on a corpus whose author already chose
  the leaves — and it is the honest answer to "is this actually generic".
- **A fourth metric bug, caught before it was reported.** My `near-dup` column said 65% and looked
  like the user's feared flood; the LIVE library — 93.3% answer accuracy, no duplication problem —
  scores 95.7% on the same threshold. D-028 had already established that absolute cosine is not a
  signal for this embedder. Replaced with a margin. **Check the metric against a known-good corpus
  BEFORE reading anything into it.**
- Imported AI-news as its own domain (116 pages, 3 shelves). Whole-library LOI R@1 "improved"
  39.3% → 56.1%; decomposed, **Retail never moved** — the average rose because news is an easy
  population. The predicted textbook⇄news collision is real: `AI` loses **11.7%** of its top-1s to
  another domain, 9× Retail's rate. The near-duplicate flood did not arrive, for a reason that is a
  warning: this corpus is many documents about one entity *each*, not many about *one*.
- 156 tests green, ruff clean. Nothing committed — the 138 new AI-news files and the deletion of the
  mis-parsed PDF book are both the user's call.

## 2026-07-15 — Session 8: a 2,000-page corpus, a second provider, and the first external numbers
The user asked for a corpus big enough to trust (231 pages / 30 questions was too small — the
flagship A/B's spread was the size of its own lead). So: imported **MultiHop-RAG** (609 news articles
→ 2,079 pages, its own library at `benchmarks/multihop/`), wired **Alibaba Qwen** (DashScope) as a
second provider to run evals cheaply, and ran the first evaluations on external, human-labelled
ground truth.

**The corpus did not give prettier numbers. It exposed eight real defects that 231 pages never could
— and that was the whole value.** Five of the eight are the same disease: a failure that does not
announce itself (21% of the corpus lost from the sieve while the import printed SUCCESS; Qwen
refusing content with `choices: null`; a truncated response "repaired" into an invented answer; a
socket hung for 30 minutes at 0% CPU). The principle now written into the code: **a broken call must
fail CLOSED, never OPEN, and `compose_answer` must not trust the model's `sufficient`.**

Findings that changed a belief:
- **FiQA — the first fully external number in the project** (human questions, human qrels), and
  **verified bit-for-bit by `pytrec_eval`, the official TREC scorer** — the first metric check this
  session that confirmed instead of refuting. nDCG@10 0.621, R@10 0.701. Real, and only mediocre:
  30% of real questions miss the top-10.
- **text-index ≥ question-index on every external metric, at zero generation cost.** The question
  flywheel cost ~3.1M tokens to lose. But do NOT retire it yet — our own colloquial VI held-out set
  says the opposite (R@1 83.3% vs 60.0%), and neither corpus settles the other (the vocabulary
  bridge, still open).
- **The cascade uses ONE knob for TWO things** — evidence amount and answer-eagerness. Basket 10
  wins accuracy but costs honesty. The fix is a separate confidence gate, and only the n=301 P6 run
  made it visible.
- **P6 holds at scale: 92.7% honest refusals** once broken calls fail closed. The rule the project
  calls non-negotiable, measured for the first time.

Also shipped: Qwen provider (route by model name, tool-calling Gemini-only, catalog locked to one
embedder, UI model picker + `/model`), `bench` / `bench-multihop` / `eval-multihop` / `probe-index`
harnesses, and `docs/SCORECARD.md` — a living measured-truth document, pinned in CLAUDE.md.

Cost ≈ $3.5. Left for next session (evidence in hand, not yet acted on): make `index_kind`
configurable (default text), split the basket/confidence knobs, and — the real blocker for a 10k-page
corpus — **concurrency** (ingest+eval are fully sequential; 2,079 pages took 40 min).
Still the user's call: commit the 138 AI-News files? delete+re-ingest the mis-parsed PDF book?

## 2026-07-16..19 — Sessions 9–10 (detail lives in STATE + DECISIONS, not re-narrated here)
The diary skipped two sessions; their full record is in `.agent/STATE.md` (SESSION 9/10 blocks) and
DECISIONS **D-045…D-061**. In one breath: **session 9** answered the scale question (retrieval is
scale-invariant if you read WIDE — R@50/R@100 are near-flat 2k→10k while R@1/R@10 collapse), shipped
retrieval-depth tiers (basket 10→20 was the real win, +7–9 on the multi-source kinds at held honesty),
and REFUTED a cross-encoder reranker (a strong embedder leaves it nothing to add). **Session 10** built
the multi-agent architecture (D-061): narration piggybacked on existing calls, typed agent roles +
registry, an MCP/A2A seam, a calculator route, and front-door routing — all default-safe, committed at
`0da0915`.

## 2026-07-20..23 — Session 11: product features, a public release, and the cost bug the release exposed
Three arcs.

**Product (D-062, committed `bb53628`).** Four capabilities, each bent to the same rule the retrieval
redesign set — keep the answer call single-shot, never let history or aggregation re-inflate it into an
O(T²) walk. **Multi-turn** (a transcript store + a lite rewrite that turns "tell me more about it" into
a standalone query BEFORE retrieval, so history touches only the cheap call). A **semantic answer
cache** (a grounded, confident answer returns for a paraphrase with zero LLM calls; never caches a
NOT_FOUND; threshold set precision-first at 0.92 because a cross-topic neighbour already sits at 0.875).
A **synthesis route** for aggregative questions — shipped but **honestly flagged UNMEASURED**, because
it has no held-out set yet. And **query decomposition**, built to attack a real measured cause and then
**REFUTED by measurement** (it discards the joint signal a wide single-query basket keeps), so it is
unregistered by default with its engine kept to reproduce the finding. The through-line, and the thing
worth remembering: each was measured to decide keep-or-discard — two kept, one kept-but-unmeasured, one
shelved — none applied because it was fashionable.

**Published.** The repo went public at `github.com/LeDat98/toshokan_kb` under PolyForm Noncommercial
1.0.0 (source-available; MIT later) with a measured-numbers README. The safety work was the point: a
multi-layer audit confirmed the private-client, retail, ai-news, benchmark and eval data and the
proposal deck are gitignored and absent from the remote.

**A cost-accounting feature — built, then removed at the user's request.** A Gemini-dashboard scare
led into the billing console and a real finding: the project measured accuracy with care and had been
*estimating* cost. A cost-measurement feature was built to fix that — and building it caught a second
bug: the new default-ON answer cache was serving evals their own prior answers, inflating scores on
re-run. But the cost code kept accreting real billing figures, and the user's standing instruction is
that billing stays out of the repo — so the **whole feature was reverted and deleted**, the incident
recorded only in the gitignored `.agent/private/COST_LEDGER.md`. That revert also removed the
eval-integrity fix, so that bug is live again — flagged for a standalone re-apply if wanted. (The
stale session-8 "Cost ≈ $3.5" line above is left untouched, still the user's call.)

**Housekeeping.** `library/domains/<client>/` was moved out of the repo to a sibling folder outside
the project (data intact), and the `.gitignore` entry that named the client removed — the repo's
tracked tree no longer carries the client name. (The name still exists in older git history on the
remote; erasing that needs a history rewrite, the user's call.)

The unit suite ran clean at 284 earlier the session; product features are committed (`bb53628` …
`e4c0194`), the cost work is gone, nothing new is uncommitted beyond the pre-existing product tree.

## 2026-07-28 — Ollama as the fourth provider (session 12)
- User's goal: a **cheaper generation tier on open weights**, local or Ollama Cloud. Built it as a
  fourth provider behind the existing single gateway (D-063) — `llm/client.py` is still the only
  module that knows a provider exists, and routing is still by model name.
- Three choices worth remembering:
  1. **The prefix is explicit (`ollama/…`)** where the other providers route on a bare vendor
     string. Ollama serves `qwen3.5`, `gemma4` and `gemini-3-flash-preview` under its own roof, so a
     bare-name rule would hand them to DashScope or to Google. Found by reading Ollama's own model
     list before writing the router, not by debugging a mis-billed call.
  2. **Native `/api/chat`, not the OpenAI-compatible shim** — for `format: <json schema>` (enforced
     by constrained decoding: the structural fix for D-040's silent 21% data loss) and `think`
     (cloud models reason by default and we pay GPU-time for it). Bonus: httpx is already a
     dependency, so this provider adds **nothing to install**, unlike openai/boto3.
  3. **The embedder deliberately does NOT move.** Ollama Cloud has no embedding model at all, and
     any Ollama embedder is a different coordinate system — switching it invalidates every catalog
     row and every SCORECARD retrieval number. Implemented (`_embed_ollama` + a configurable
     query-side instruction prefix, which is how open embedders express gemini's task-type
     asymmetry) so the head-to-head is one `reindex --fresh` into a separate db, never a half switch.
- Side-fix the fourth provider forced: `GET /api/models` called every non-Gemini model "dashscope"
  and gated its availability on the DashScope key — a Bedrock model already showed as unavailable
  when only AWS was configured. Now `LLM.provider_of()`, one place.
- The cost picture is NOT per-token: Ollama Cloud bills GPU-time inside a flat plan (Free $0 /
  Pro $20 / Max $100-paused) and publishes no cap numbers, so break-even can only be measured, not
  computed. Against our measured $6.75/500 queries on `gemini-3.5-flash`, Pro pays for itself around
  ~1,500 queries/month. **The limit that bites first is concurrency, not price:** eval/ingest default
  to 8-wide and the Free plan allows 1 concurrent model.
- The risk of a cheap model here is **honesty, not accuracy**, and we already measured it once: qwen
  labelled 26/28 improvised nulls "high" confidence (D-046) and lost 2.7 points of honesty where
  gemini held 99.3% (D-052). So the gating number for any open model is the **null-set** run.
- `docs/OLLAMA.md` written (signup, env, model shortlist, cost, the honesty caveat, the embedder
  experiment). 14 new tests, all LLM-free; nothing measured yet — no quality claim is made.

## 2026-07-29 — Session 13: the SELECTION layer (D-064) — built, and deliberately unmeasured
- **The question.** The step this project is named for is the one that loses: the LLM triage keeps
  **69% AllGold** where simply taking the embedder's **top-10 keeps 75%** (probe 2c, MultiHop n=150).
  A reranker is not the fix — measured and refuted (D-048).
- **The reframe** (from the literature pass, notes in `.agent/private/RESEARCH_agentic_selection.md`):
  "AI selection loses" is a verdict on the **weakest possible configuration**, and ours hits three of
  its axes at once — *pointwise*, *binary*, *titles-only*. Fix an axis, not the ranker.
- **Shipped, all default-OFF, all zero new LLM calls:**
  - `triage_card=rich` (Tier 0) — `cascade.build_card`: several query-relevant passages instead of
    one, passage AND the matched catalog row together (the lean card made them mutually exclusive
    for no reason), and section titles whose *body* overlaps the query marked `▸`. New model-free
    helpers `query_passages` / `relevant_sections`.
  - `triage_mode=set` (Tier 2) — `cascade._triage_set` + `prompts/select_set.md`: the same one call,
    asked for a covering SET; each pick states what it ADDS; `missing` names the hole. Section
    naming kept (D-053's `read` selector lost partly by taking whole pages).
  - `libkb probe-selection` (`evals/selection.py`) — the deciding experiment. Arms over ONE shared
    candidate pool; headline metric **retention**; preflight prices the run on 3 real pools and
    stops without `--yes`. Dataset-agnostic (a dataset is a loader).
- **Discipline kept:** `query_snippet` left BIT-IDENTICAL to the version D-050's +1.7 was measured
  on — the improvement lives only in the new `query_passages`, so the baseline arm really is the
  shipped system. Tier 1 (setwise) skipped on cost grounds and said so.
- SCORECARD reconciled with D-048: §2.2/§5/§8 still called the reranker "the highest-value
  experiment, still not run" and FiQA "none yet". Both had been settled for a session and a half.
- **NOTHING HERE IS A CLAIM.** No arm has been run. 25 new LLM-free tests pass; that is all.
- **Test-suite hang, diagnosed at last (it is NOT a code regression).** Two causes, both
  environmental: (1) killed pytest runs leave **orphan processes holding locks**, and a stale one
  silently stalls every later run — `Get-Process python*` and kill before believing a hang; (2) the
  venv is built on the **Microsoft Store Python** (`WindowsApps\PythonSoftwareFoundation...`), whose
  app-container filesystem makes the seed/store writes pathologically slow. Proved by stashing every
  change: at HEAD, `test_orchestrator.py` and `test_store.py` hang identically. Small file sets pass
  fast (`test_selection` 25/25, `test_cascade` 9, `test_agent_roles` 6, `test_config` 4).

## 2026-07-29 (cont.) — BM25 re-tried on the corpus that should have favoured it (D-065)
- The user challenged D-032: *one run does not mean it does not work — it may have been applied
  wrongly, and big tools still use lexical search.* Both halves were worth taking seriously.
- **The challenge was right about the evidence.** D-032's two query sets were adversarial to BM25 by
  construction: LLM-generated questions written FROM the pages being searched (metric bug 6.4), and
  a CROSS-LINGUAL paraphrase set — Vietnamese questions, English pages, almost no shared tokens.
- **It was wrong about the conclusion, and so was I.** Re-run on FiQA (57,638 docs, 648 human
  questions, human qrels, cached vectors, 0 generation calls): fusion costs **-0.18 nDCG@10**. My
  own config hypothesis — that ORing an unfiltered question was the real bug — moved it **+0.001**.
  Gating fusion to rare query terms moved it **-0.004**.
- **Then the question fusion cannot answer**, measured separately because the two come apart: of
  1,706 gold documents BM25 finds **10 (0.6%)** the embedder misses at k=100, in 10 of 648 queries.
  That is the CEILING on what a perfect trigger could add — so the agent-tool/escalation design (the
  `grep` analogy) is closed here too, not just fusion.
- On Claude Code: it does not do BM25 hybrid retrieval at all — it runs ripgrep as a TOOL. The
  transferable lesson was "exact search as an escalation", and the 0.6% is what killed it *for this
  kind of corpus*. Code is identifier-dense and has no embedding index; prose knowledge bases are
  not that regime. Recorded as scope, not as a universal.
- **Harness discipline:** the run reproduces two numbers it did not choose — dense nDCG@10 = 0.621
  (= SCORECARD §2.2, three decimals) and our BM25 = 0.235 vs BEIR's published 0.236. After seven
  metric bugs, a harness that cannot reproduce a known result may not be used to refute one.
  `beir.score_rankings` was split out so every arm is scored by literally the same code.
- Two incidental facts: `hybrid_lookup` was only reachable from the WALK's shortlist tool, so the
  cascade never touched it; and a `text` row stores an EMPTY display text, so `questions_fts` would
  have indexed empty strings. The queued "fix the FTS source" change was therefore **dropped** — it
  would only have made a dead signal reachable.
- Writing the tests corrected an assumption before the run did: in a toy corpus, stopword filtering
  alone does NOT rescue the buried rare-term document — only the gate does. The test says so.

## 2026-07-29 (cont.) — the scope rule, and the first build under it (D-066 / D-067)
- **User set the frame and it was a correction worth taking:** every method from here is a TOOL the
  agent uses on the 50–100 candidates the sieve already returned — not a change to the sieve. The
  agent currently guesses from titles; the tools let it trace. Recorded as D-066 + a memory, because
  it is the rule that says which experiments are even on-topic.
- That immediately reclassified my own BM25 work: D-065 measured BM25 across all 57,638 FiQA
  documents = sieve-level. Valid for "should BM25 retrieve" (no). Says nothing about BM25 as a tool
  inside the pool — and its 0.6% complement figure cannot be borrowed, because that figure is about
  documents never retrieved, whereas in-pool they are retrieved by definition.
- Built: `pooltools.py` (`coverage_map`, `find_in_candidates` — both 0 LLM), `triage_mode=trace`
  (set-selection handed the coverage map, same call count), `triage_mode=agent` (a ReAct loop with
  `ask_page`, budgets in CODE, closing out with a forced `select` and falling back to shipped triage
  if it still selects nothing).
- **Removed the Gemini-only tool-calling refusal.** It was justified by D-027/D-017 — but those are
  arguments about the WALK, where 9–13 turns compound a weak model's mistakes. The pool loop is
  bounded by construction. Refusing by provider made the 6×-cheaper tier untestable, so the refusal
  became a measurement. **Live on qwen-plus, 4/4**: tool call with parseable args + id, result
  round-trips into the answer, real pool-agent schemas (incl. nested arrays) accepted.
- Design notes worth keeping: `coverage_map` thresholds at HALF a part's content words per part
  rather than summing across parts — summing is exactly how BM25 lets a crowd of common words bury
  the one document that answers (D-065). And the pool is a FENCE: a model naming a page outside it
  is told so, never silently given a best guess.
- 28 new LLM-free tests. Nothing measured yet — `probe-selection` now has 9 arms and none has run.

## 2026-07-29 (cont.) — the selection experiment ran, and it inverted the premise (D-068)
- Stage A: 5 arms x 150 MultiHop queries, gemini-3.5-flash, one shared candidate pool. First read:
  `embedder` 89.0% retention at basket 20, no LLM arm above it — probe 2c reproduced, thesis dead.
- **Then the control that should have come first.** The LLM arms take 3.4-4.4 pages; the embedder
  arm takes all 20. Retention rewards taking more. Free to check (0 LLM): embedder retention is
  53.6 / 59.7 / 63.7 / 77.7 / 89.0% at basket 3 / 4 / 5 / 10 / 20.
- **At an equal budget it inverts.** `rich` retains 88.1% on 4.1 pages vs the embedder's 59.7% on 4
  — **+28.4 points** — and lands within 0.9 points of what the embedder needs FIVE TIMES the pages
  to reach. The agent is not worse at picking; it is ~5x more page-efficient, and it had been scored
  against an opponent with 5x the budget. Probe 2c's 69-vs-75 carried the same confound, and the
  artifact / D-064 / the research notes were all written on top of it.
- Recorded as metric bug 6.8: **retention reads like a quality metric and behaves like a budget
  metric. Equalise what each arm may take before comparing selectors.** Eight metric bugs now; seven
  of eight checks refuted us.
- `rich` (Tier 0) is the best selector measured (+1.5 over shipped `headers` on fewer pages, +2.4 on
  comparison). `trace` — the coverage map — is REFUTED as a mode: worst LLM arm at 79.7% and the
  fewest pages taken. Handing the model a map of which candidate covers which part appears to
  convince it that it is done. Same shape as the refuted coverage PROMPT (D-051): the tool computes
  correctly, and telling the agent the answer makes it less thorough.
- **The real defect is under-filling, not mis-picking** — allowed 20, takes 3-4, and retention
  tracks pages-taken almost perfectly across arms. That is now the highest-value untried experiment
  and it is one prompt change plus one arm.
