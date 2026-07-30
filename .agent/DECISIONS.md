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

## D-022 · 2026-07-12 · Card catalog = SQLite + brute-force cosine; embeddings shortlist, not backbone
The catalog (`libkb/catalog/`) stores generated questions (vi+en) as L2-normalized float32 blobs;
`Catalog.search` is a numpy dot product over the whole matrix (cached in memory, rebuilt on write).
Deliberately the simple path up to the ~100k-question ceiling (D-002); past it, replace the search
body with sqlite-vec behind the SAME `search()` signature — callers don't change. Layering:
`db.py` (connection/schema, WAL, `check_same_thread=False` so API worker threads can read),
`store.py` (Catalog CRUD + vector search, pure — no LLM), `search.py` (query-side `lookup`: embed +
threshold; the only catalog file that touches `llm.embed`). Embeddings NEVER answer directly — they
only (a) shortcut to a page or (b) hint the navigator, so an embedding miss can't fabricate an answer.
The flywheel writes 8 rows/page (questions_per_page=4 intents × vi+en); `RETRIEVAL_DOCUMENT` at index,
`RETRIEVAL_QUERY` at lookup (Gemini asymmetric retrieval).

## D-071 · 2026-07-31 · Score-only set sizing is CLOSED — and the same run shows the LLM selector is worth +20
Two training-free selectors from the literature, built as `probe-selection` arms because TP is 2.75
and **varies** with the question kind while every selector we have commits to a near-constant 3.0–3.2
— a constant cannot be a superset of a moving target, and that failure is arithmetic, not judgement.
Both cost **zero LLM calls**, so the whole result is free. Full numbers: SCORECARD §2.7.

- **Adaptive-k** (arXiv 2506.08479) — cut at the sharpest drop in the sorted scores, take `B` more.
- **Conformal filtering** (arXiv 2511.17908), adapted — the nonconformity score is the margin each
  query needed to keep **all** of its gold, so the certified quantity is `superset` itself rather
  than per-document recall. Cross-fitted over 5 folds: no query is scored under a threshold it helped
  calibrate. (The leakage guard is a test, not a comment — this project has paid for two metric bugs
  of that family already.)

**The conformal certificate is exact**, which is the run's own correctness check: predicted absolute
superset is (1−α) × 0.927 (the pool ceiling), and measured lands within 0.8 points at α = 0.03, 0.1,
0.2, 0.3 and 0.4. Same class of external check as BM25 0.235 vs BEIR 0.236 (D-065).

**Both are NULL as selectors.** Adaptive-k sits ON the embedder curve (0 to +2 at matched `taken`).
Conformal is +3…+5 wide and *negative* tight. Neither chooses better; both choose **more**.

**What it settles.** At the target `taken ≈ 4` the best score-only selector reaches ~25–32% superset,
and reaching 90% from scores alone costs ≈22 documents / ~40,000 ctx tokens — **7× the budget**. *The
28 missing points are not in the sieve's scores.* Any further score-only set sizing is closed.

**The finding that pays for the run, though, is the other direction.** With the free curve mapped, an
LLM arm can finally be scored against *doing nothing at the same basket size* — a subtraction nobody
had computed: `set` **+23**, `rich` **+20**, `agent` **+16** points of superset. Selection is not the
weak component of this system. **Rule added: never quote an LLM arm without the free number at its
own `taken` beside it.** `probe-selection` now runs that matched control automatically, bisecting the
basket until the embedder commits to the same number of DOCUMENTS — a basket is counted in pages and
`taken` is not, and matching the two directly is the same category error rule 2 exists to prevent.

**Consequence for the open direction:** the completeness check must READ. It must also be a SEPARATE
judge over the assembled set (every in-prompt variant has failed: D-051, D-068, D-069), score the SET
rather than its passages (SURE-RAG, arXiv 2605.03534: +18 F1 over GPT-4o-as-judge on exactly this),
and it is not optional — insufficient context makes a model improvise rather than abstain (*Sufficient
Context*, ICLR 2025, arXiv 2411.06037: 10.2% → 66.1%), and our honesty is at 100%.

## D-070 · 2026-07-29 · The scoring contract is fixed: approximate the TRUE-PAGE SET. Everything else is diagnostic.
**Set by the user, and it closes the framing question for good.** `docs/SELECTION_TARGET.md` is the
page; this decision records why it outranks the older docs.

**The mission.** The sieve hands the agent 50–100 candidates. **Only TP ≈ 2.75 documents actually
hold the answer** (measured on MultiHop: range 2–4, never 1; comparison 2.25 · temporal 2.49 ·
inference 3.46). The agent's job is to return a set as close to TP as it can — **containing all of
it**, carrying little else.

**Score `superset` (selection ⊇ TP). Nothing else is an objective.**
- **Overhead of 1–2 documents is an ACCEPTABLE TRADE.** Taking fewer pages is not the failure;
  taking fewer than TP is. A tight precise set that misses one true page is worse than a loose one
  that contains them all.
- **Never compare selectors at different `taken`.** That measures budget, not skill (metric bug 6.8).
- **The basket is NOT free.** `ctx_tokens` — what the answerer must then read — is the bill the whole
  selection layer exists to cut, and leaving it out is what made "better selection changes nothing"
  look true. Same coverage for half the tokens IS the win.
- **`retention` is diagnostic only.** It gives partial credit and rewards taking more.

**What this immediately reclassified.** Under the old reading, `rich` "did not beat the embedder".
Under this one: **`rich` covers TP more often than embedder@20 (64.7% vs 61.3%) while taking 7.0
documents instead of 11.1 and costing 10.5k context tokens instead of 18.1k** — better coverage for
42% fewer tokens. And `set`/`agent`, previously read as simply worse, have exactly the right SHAPE
(TP+1, 70% precision against the embedder's 23%) and one specific defect: they miss a true page on
~6 queries in 10.

**So the diagnosis, and the only open direction.** The tight selectors do not fail at judging. They
fail at **knowing they are not finished** — `set` already emits `missing`, the agent already has
`coverage_map`, and neither uses it to check itself before committing. The fix must be a MECHANISM,
not an instruction: `triage_fill` told the model plainly to fill its basket and moved it 4.5 → 4.7
(D-069). **Target: superset ≥ 90% at `taken` ≈ 4, ≲6,000 ctx tokens.**

Enforced in three places so it cannot drift again: `CLAUDE.md`'s session protocol reads
`SELECTION_TARGET.md` first, `STATE.md` opens with it, and `probe-selection` now prints the
set-vs-TP table (superset · taken · over · precision · ctx tok) instead of leading with retention.

## D-069 · 2026-07-29 · The three ReAct fixes, the fill lever, and the answer-level A/B — all measured, none adopted
Four changes, all measured on the same protocol, and the useful part is which ones failed and how.

**1 · The three ReAct fixes WORKED on the mechanism and did not become a score.** Batching tool
calls in one turn, carrying `turns_left` in every tool result, and `pool_max_steps` 6→8:

| | before | after |
|---|---|---|
| `select` fired voluntarily | 53/150 (35%) | **49/50 (98%)** |
| ran out of steps | 147/150 | **0** |
| fell back to shipped triage | yes | **0** |
| retention | 84.2% | 89.7% |

And it still loses to one `rich` call (92.8%) at ~7× the calls. **Two side-effects that matter more
than the score:** `ask_page` — the only tool that costs money — went from 6 calls in 150 queries to
**46 in 50**; and the agent became **less** discriminating, not more (`coverage_map` was 79% of
comparison vs 27% of inference questions; after batching it is ~85% / ~87%, near-uniform).
**Telling it to fire everything in one turn removed the incentive to choose.** The adaptive routing
was the best thing the loop had, and the fix for its pacing cost it. Not adopted; the fixes stay in
the code because the loop is unusable without them, but the loop stays default-OFF.

**2 · `triage_fill` is a NULL RESULT.** Told plainly that the basket is a ceiling it should
approach, the selector went 4.5 → **4.7** pages (retention +0.2, AllGold −2.0). Under-filling is
real and **is not reachable by instruction** — the same shape as the refuted coverage prompt
(D-051). If it is worth closing it needs a CODE mechanism (top the basket up from the ranked pool),
not more words. Knob kept default-OFF so the refutation is reproducible.

**3 · The answer-level A/B: retention did NOT carry through. `rich` is NOT promoted.**
`eval-multihop --limit 100`, identical cases: ANSWER **70.5% → 71.6%**, honesty 100% both, coward
14.8% both, +22% tokens. **+1.1 points is one flipped comparison case** — below this project's own
noise floor (§5.8). So: `rich` wins decisively on *retention* (§2.6c: matches a 20-page embedder on
4.5 pages) and that advantage does not reach the answer. Either the basket at 20 is already large
enough that better selection within it changes little, or **the ceiling is the ANSWERER**. Temporal
sits at 47.8% with the gold in the basket, which points at the second — and that is now the open
question, not selection.

**4 · And the eval-integrity bug that destroyed the first attempt at (3).** Both arms came back
bit-identical on every metric, with the `rich` arm reporting FEWER input tokens. Cause: the semantic
answer cache (D-062) matches anything within 0.92 cosine, so arm B answered nothing and replayed arm
A — confirmed by **zero** `cascade_done` lines against 75 in the clean re-run. **It inflated the
score by +6.8 points** (77.3% vs 70.5% clean). `evals/multihop_answer.run()` now forces
`enable_answer_cache=False` itself, with a regression test; it is deliberately not configurable,
because a knob the caller must remember is one that will be forgotten. Metric bug 6.9 — and it was
caught only because two identical arms are implausible enough to look at twice.

**Where this leaves the selection work.** `rich` is the best SELECTOR measured and the honest claim
for it is efficiency, not accuracy: **it reaches a 20-page embedder's coverage on 4.5 pages.** That
is worth having when the basket must be small (cost, latency, a small corpus) and is worth nothing
at basket 20 on this corpus. Default stays `lean` until a regime exists where the basket is the
binding constraint.

## D-068 · 2026-07-29 · MEASURED: at an equal page budget the agent beats the sieve by ~28 points. The founding comparison was confounded.
**The premise this entire research thread was built on is wrong, and the correction is the finding.**

Probe 2c said: *triage keeps 69% AllGold, the embedder's top-10 keeps 75%* — the selector loses to
the sieve. The artifact, D-064, the research notes and every tier in them were written to close that
gap. `probe-selection` (150 MultiHop queries, window 50, gemini-3.5-flash, one shared pool per
query) reproduced it at basket 20: `embedder` **89.0%** retention, no LLM arm above it.

**The control nobody had run.** The LLM selectors take **3.4–4.4** pages. The embedder arm takes all
**20**. Retention rewards taking more, so the comparison was measuring basket size. The embedder's
own curve costs nothing to produce (0 LLM calls): retention **53.6 / 59.7 / 63.7 / 77.7 / 89.0%** at
basket 3 / 4 / 5 / 10 / 20.

**At an equal budget it inverts:**

| arm | pages | retention | AllGold |
|---|---|---|---|
| embedder | 4.0 | 59.7% | 21.3% |
| **rich** | **4.1** | **88.1%** | **58.7%** |
| headers (shipped) | 4.4 | 86.6% | 57.3% |
| set | 3.6 | 82.6% | 50.0% |
| trace | 3.4 | 79.7% | 42.7% |

`rich` retains **+28.4 points** over the embedder on the same number of pages, and lands within
**0.9 points** of what the embedder needs **five times** as many pages to reach. **The agent is not
worse at picking. It is ~5× more page-efficient, and it was being scored against an opponent
allowed five times the budget.**

**Decisions this settles:**
1. **`triage_card=rich` (Tier 0) is the best selector measured** — +1.5 retention over shipped
   `headers` on *fewer* pages, +2.4 on `comparison`. One call, no extra call, +56% input tokens.
   It is the arm to promote once an answer-level A/B confirms retention carries through.
2. **`trace` — the coverage map — is REFUTED as delivered.** Worst LLM arm (79.7%) and the fewest
   pages (3.4). Handing the model a map of which candidate covers which part appears to *convince
   it that it is done*: it fills the named parts and stops. Same shape as the refuted coverage
   PROMPT (D-051) — the tool computes correctly, and telling the agent the answer makes it less
   thorough. The tool stays (`pooltools` is used by the agent loop); the `trace` MODE does not
   become a default.
3. **`set` likewise underperforms `headers`** (82.6 vs 86.6) on fewer pages — same mechanism.
4. **The real defect is UNDER-FILLING, not mis-picking.** Every selector may take 20 and takes 3–4.
   Retention tracks pages-taken almost perfectly across arms. **That is the highest-value untried
   experiment in the project** and it is one prompt change plus one arm: make the selector fill its
   basket and see whether ~5× efficiency converts into an outright win over embedder@20.

5. **The ReAct loop routes tools adaptively — and still loses to one call.** Same 150 queries:
   retention **84.2%** at 4.4 pages and **7.7 calls/query**, against `rich`'s 88.1% at 4.1 pages and
   ONE call. But the telemetry says the routing works: `coverage_map` on ~79% of comparison and ~75%
   of temporal questions versus ~27% of inference — **the agent worked out unprompted that a
   multi-part question needs a coverage map and a single-fact one does not** — and it spent the paid
   tool (`ask_page`) six times in 150 queries. **The defect is that it never commits:** `select`
   fired voluntarily on 53 of 150; **147 hit the step ceiling** and were closed out. It issues
   `find_in_candidates` one pattern per turn (~4.2/query) and the budget dies before it decides.
   Untried fixes: batch the tool calls (the loop already counts a multi-tool turn as one step), or
   show it a visible commit deadline. **Not adopted, and not refuted either** — *right instincts, no
   closing move* is a different verdict from *worse at selecting*, and it is the one the data
   supports. It also vindicates the scope rule (D-066): the tools are worth having; what is unproven
   is this loop's pacing.

**Method note, and it is the reusable part.** Two independent measurements — probe 2c and the first
pass of this one — carried the same confound, and it survived because "retention" reads like a
quality metric while behaving like a budget metric. The control that exposed it was FREE. *Before
comparing two selectors, equalise what they are allowed to take.* Recorded as metric bug 6.8.

## D-067 · 2026-07-29 · Pool tools, a ReAct loop with budgets in code, and tool calling opened to DashScope
The first build under D-066's scope rule. Three things, all default-OFF, none of them a retriever.

**1 · Pool tools (`agent/pooltools.py`) — 0 LLM calls.** They answer, over the 50–100 candidates the
sieve already proposed, questions the agent otherwise guesses at from a section title:
- `coverage_map` — split the question into parts, show which candidate covers which, computed from
  the page text. Reports the parts NO candidate covers, and offers a greedy minimal covering set.
  This is the direct attack on the measured multi-hop floor (comparison 74%, temporal 58%): one
  blurred query vector ranks no part sharply, and a pointwise selector cannot notice it has covered
  the same half twice. A part counts as covered at **half** its content words — not *any*, which
  would make every page cover every part through one shared word (that is BM25's summing failure,
  D-065, and this thresholds per part instead).
- `find_in_candidates` — literal/regex search across candidate bodies, returning the SECTION each
  hit sits in. **This is not D-065 re-opened.** D-065 measured BM25 fused into the SIEVE across all
  57,638 documents and it lost; there is no ranking here to corrupt, and its 0.6%-complement figure
  is about documents never retrieved at all. Different question, still open.

**2 · `triage_mode` gains two shapes.**
- `"trace"` — `set` selection with the coverage map handed to it. **Same call count as `set`.** The
  block is not another model's opinion; it is arithmetic over the page bodies.
- `"agent"` — a ReAct loop (`agent/poolagent.py`) where the librarian is given the tools and decides
  what to check: `find_in_candidates` / `coverage_map` / `read_section` (free) and `ask_page` (one
  lite call, "does THIS page answer it? quote the line"), ending at `select`.

**Why the loop is not the walk** (refuted as the default, D-036, 9–13 calls and O(T²)): the walk
searched a TREE, so a wrong turn at depth 1 was unrecoverable. Here the candidate set is fixed
before the loop starts and every tool reads only from it — the pool is a fence, and a model naming a
page outside it is told so rather than quietly given a best guess. The worst a bad tool call costs
is one step.

**Budgets are enforced in CODE, never in the prompt** (D-008). Three independent ceilings —
`pool_max_steps` (6), `pool_max_lite_calls` (3), `pool_max_reads` (6) — and running out does NOT
fail the turn: the loop is closed out with one forced `select`, because a librarian out of time
still hands over what he found. If even that selects nothing, `_triage_agent` falls back to the
shipped triage: an agent that spent its budget learning nothing must not also cost the reader the
answer (that is D-035 with extra steps).

**3 · Tool calling opened to DashScope.** It used to raise, on the grounds that a cheap model fails
at navigation (D-027) and that Gemini's thought-signature echo (D-017) has no counterpart. Both
facts hold — but they are arguments about the WALK. Refusing by provider made the 6×-cheaper tier
untestable on the pool tools, so the refusal became a measurement. `_dashscope_messages` /
`_dashscope_tool_calls` do the OpenAI-shaped plumbing; `ToolCall.call_id` and `ToolResponse.call_id`
are additive (Gemini leaves them None). **VERIFIED LIVE on qwen-plus** (`tests/llm/
test_tool_calling.py`, 4/4): it emits a call with parseable arguments and an id, the result
round-trips and is used in the answer, and it accepts the real pool-agent schemas including
`select`'s nested array-of-objects. Bedrock and Ollama still raise.

Measurable as `probe-selection` arms `trace`, `trace+rich`, `agent`. **No arm has been run** — none
of this is a claim yet. 28 new LLM-free tests; the two hardest assert the fence and the budgets.

## D-066 · 2026-07-29 · Every retrieval method from here is an AGENT TOOL over the bounded candidate pool — not a change to the sieve
**The scope rule, set by the user, and it settles which experiments are even on-topic.**

The sieve is not the bottleneck and has not been for two sessions: FiQA R@100 = **0.920**, MultiHop
AllGold@20 = **93.5%**. The evidence is almost always already in the top 50–100. What loses it is
**selection** — the triage keeps 69% of the gold where taking the embedder's own top-10 keeps 75%.

So from now on a method must be shaped as a **tool or skill the agent uses on the 50–100 candidates
the cascade already proposed**. Its job: stop the agent from having to *guess from titles* which
page holds the answer, and let it **trace** to the likely ones. Keyword/exact search is one such
tool, not the point; the point is the shape.

**The test before building or measuring anything: does this run over the WHOLE CORPUS, or over the
candidate pool?** Whole corpus ⇒ wrong frame, wrong question, wasted run.

**Applied to what already exists:**
- `triage_card=rich` (D-064) — on-frame: it is exactly "give the agent more than titles".
- `triage_mode=set` (D-064) — on-frame: the agent choosing a covering subset of the pool.
- `probe-selection` (D-064) — on-frame: it holds one candidate pool fixed and varies the selector.
- **D-065 (BM25) — OFF-frame.** It measured BM25 fused with dense across all 57,638 documents, i.e.
  as part of the SIEVE. That answers "should BM25 help retrieve?" (measured: no, decisively) and it
  stays valid for that question. It does **not** answer "does an exact-search TOOL over the 50–100
  candidates help the agent select?" — and its 0.6%-complement figure does not bear on it either,
  because that figure is about documents the embedder never retrieved, whereas here the documents
  are already retrieved by definition. **That question is open and is the on-frame version.**

## D-065 · 2026-07-29 · Hybrid BM25 re-tried on the corpus that should have favoured it — D-032 CONFIRMED, and my own two rescue hypotheses refuted
**The challenge was fair and it was the user's.** D-032 refuted BM25 fusion, but on two query sets
adversarial to BM25 *by construction*: LLM-generated questions written FROM the pages being searched
(metric bug 6.4), and **cross-lingual** Vietnamese paraphrases against English pages — where BM25
matches tokens across languages that share almost none. One run, in a regime where the mechanism
could not fire, should not close a question for good. So it was re-run properly.

**And a second suspect I raised: our own configuration.** `_fts_terms` ORs every word of a question
and filters nothing, and BM25 sums a contribution per matched term — so a document echoing six
common words can outrank the one document carrying the rare word. (`sections.py` has a vi+en
stopword list; the lexical path never used it.) A plausible config bug, worth separating.

**The measurement (`libkb probe-lexical`, `evals/lexical.py`).** FiQA: 57,638 documents, 648
questions real people wrote, human qrels, same language, real lexical overlap, vectors already
cached ⇒ **0 generation calls**. BM25 is deliberately the one SQLite FTS5 would run (k1=1.2, b=0.75,
`unicode61 remove_diacritics 2`, no stemming), so a number here is a claim about production.

| arm | nDCG@10 | R@10 | R@100 |
|---|---|---|---|
| **dense** | **0.621** | **0.701** | **0.920** |
| BM25 | 0.235 | 0.298 | 0.512 |
| hybrid RRF (today's `hybrid_shortlist`) | 0.440 | 0.518 | 0.877 |
| + stopword-filtered query | 0.441 | 0.530 | 0.880 |
| + fused only on rare terms (df ≤ 1%) | 0.436 | 0.549 | 0.885 |

**Two correctness checks are built into the run**, because this project has been misled by its own
metrics seven times: the dense arm reproduced §2.2's **0.621** to three decimals, and our BM25 landed
at **0.235 against BEIR's published 0.236**. A harness that cannot reproduce a known number may not
be used to refute one.

**Findings, in order of what they cost me:**
1. **D-032 replicates.** Fusion costs −0.18 nDCG@10 in the regime chosen to favour BM25.
2. **My config hypothesis is REFUTED.** Stopword filtering: +0.001. Rare-term gating: −0.004.
3. **And the question fusion cannot answer — is there a hidden complement?** Measured separately,
   because "does fusing help" and "does the weak ranker see what the strong one cannot" come apart:
   of **1,706 gold documents, BM25 finds 10 (0.6%) that dense misses at k=100**, in 10 of 648
   queries; of the 16 queries dense misses entirely it rescues 2. **0.6% is therefore the ceiling on
   what a PERFECT trigger could add** — which closes the escalation/agent-tool design too, not just
   fusion.

**Mechanism — the same one as D-048.** A strong first stage leaves a second signal nothing to add,
and RRF weights both rankers equally, so mixing a 0.235 ranker into a 0.621 one lands at 0.44.

**Scope, stated so this is not over-read a second time.** FiQA is conversational prose. A corpus
whose queries carry hard identifiers — an article number, a SKU, an error string, a function name —
is a different population and is what lexical search exists for. The claim is: **on prose knowledge
bases with a strong embedder, lexical adds ~nothing and no wiring fixes that.** Coding agents lean
on `grep` because code is identifier-dense and has no comparable embedding index; that regime is not
ours. Re-open this when a corpus looks like that one — and `probe-lexical` will be here to settle it
in one free run.

`hybrid_shortlist` stays OFF, and it is now off on evidence rather than on one narrow run. Two
incidental facts recorded while looking: `hybrid_lookup` is only reachable from the WALK's shortlist
tool (`agent/tools.py`), so the cascade — the default since D-036 — never touched it; and a `text`
row stores an EMPTY display text, so `questions_fts` would have indexed empty strings anyway. The
FTS-source fix that was queued behind this measurement is therefore **not** being made: it would
only have made a dead signal reachable.

## D-064 · 2026-07-29 · Stop trying to out-RANK the embedder. Enrich the CARD and select a SET — with the probe that decides it
**The finding this answers.** Probe 2c (MultiHop n=150): the LLM triage keeps **69% AllGold**; just
taking the embedder's own **top-10 keeps 75%**. The selector — the "active seeker" the whole project
is named for — **loses to the sieve it was meant to improve.** The obvious fix was a reranker, and
that was already measured and REFUTED (D-048: qwen3-rerank on FiQA top-50 HURT R@1 by 5–9 pts,
because a strong first stage leaves a reranker nothing to add).

**The reframe (from a literature pass, notes in `.agent/private/`).** "AI selection loses" is not a
verdict on AI selection. It is a verdict on the **single weakest configuration**, and our triage
hits three of its axes at once: *pointwise* (each candidate judged alone), *binary* (take/leave,
never "what does this ADD"), and *titles-only* (~59 tokens of section headings). Every comparative
selection study ranks exactly that configuration last. So the lever is not a better RANKER — that
door is closed by D-048 — but the two axes a reranker never touched. Both are different
**objectives**, not better scorers, which is why D-048's mechanism does not reach them.

**Shipped, both default-OFF (the measured-safe state), both zero new LLM calls:**
1. **`triage_card=rich` (Tier 0)** — the card carries `triage_passages` query-relevant passages
   instead of one, shows the passage *and* the matched catalog row (the lean card made them
   mutually exclusive for no reason — "what is this page FOR" and "what does it say about YOUR
   question" are different facts), and MARKS the section titles whose *body* overlaps the query.
   All model-free, computed from the body already fetched. This is Anthropic's Contextual Retrieval
   move (context before embedding, −35% retrieval failures) done at query time for $0.
2. **`triage_mode=set` (Tier 2)** — one call over the SAME cards, asking *"which pages TOGETHER
   cover this question?"* instead of *"is this page relevant?"* one at a time. Every pick must state
   what it contributes that the others do not, and `missing` names what no candidate covers (the
   widen round currently has to infer that). Section naming is KEPT — the refuted `read` selector
   (D-053) picked whole pages and short-circuited the last-resort net the accuracy rides on.

**And the thing that makes them claims rather than hopes: `libkb probe-selection`.** Every arm
(`embedder` · `headers` · `rich` · `set` · `set+rich` · `read`) runs over ONE shared candidate pool,
embedded once — so a difference between arms is the selector and nothing else. The headline metric
is **retention**: *of the gold the sieve ALREADY put in the pool, how much did the selector keep?*
`embedder` is the do-nothing baseline; an arm below it made things worse by choosing. Retrieval
only — no answer, no judge — so an arm costs one call per query and is not confounded by the
answerer. A query whose gold never entered the pool is a SIEVE failure and is excluded from
retention (it shows up in `ceiling` instead). The run **prices itself on 3 real candidate pools and
stops** unless `--yes`.

`query_snippet` is left BIT-IDENTICAL to the version D-050's +1.7 was measured on (its heading-
skipping improvement lives only in the new `query_passages`) — a shipped baseline that quietly
improves is a baseline you can no longer compare against.

**Not adopted, deliberately:** *setwise* tournament selection (Zhuang, SIGIR 2024) — it costs k
comparison calls where set-selection costs one, and SetR-style set selection beats listwise
rerankers on exactly our metric. **No arm re-runs a cross-encoder** (D-048 stands).

## D-063 · 2026-07-28 · Ollama is the fourth provider — open weights, one code path for local and cloud, generation only
The user wants a cheaper answer/generation tier on open-weight models. Added Ollama alongside Gemini,
DashScope and Bedrock, under the SAME rule as the others (D-016): `llm/client.py` stays the single
gateway, routing is by MODEL NAME, and nothing else in `libkb` learns a provider exists.

- **The prefix is EXPLICIT: `ollama/…`.** The other providers route on a bare vendor string
  (`qwen`, `anthropic.`), and that rule breaks here — Ollama serves `qwen3.5`, `gemma4` and even
  `gemini-3-flash-preview` under its own roof, so a bare name would be captured by
  `dashscope_prefixes` or fall through to Gemini. `LIBKB_MODEL=ollama/gpt-oss:120b-cloud` is then the
  entire configuration, and `Settings._split_ollama_models` re-adds a missing prefix on menu entries
  so a mis-typed one cannot silently be billed to Gemini.
- **LOCAL and CLOUD are one code path**, because Ollama Cloud speaks the same `/api/*` protocol as
  the local daemon and differs only by host + bearer token: `LIBKB_OLLAMA_HOST` +`OLLAMA_API_KEY`.
  "Where does it run" is deployment, not architecture, and it should not be a branch in this file.
- **The NATIVE API, not the OpenAI-compatible shim, and not for purity — for two properties:**
  (a) `format: <json schema>` is enforced by constrained decoding, which is the structural fix for
  the D-040 class of defect (DashScope does *not* enforce a schema; a malformed reply crashed the
  parser and 439/2,079 pages silently left the corpus). (b) `think` lets us turn a reasoning model's
  reasoning OFF — most Ollama cloud models reason by default, and on a triage or question-generation
  call every reasoning token is GPU-time we are billed for and did not want. Bonus: no new dependency
  (httpx is already required), unlike `openai` for DashScope and `boto3` for Bedrock.
- **Tool calling is refused, as for every non-Gemini provider** — even though Ollama models DO
  advertise tools. The walk echoes Gemini thought-signatures (D-017) with no counterpart here, and
  navigation is the one job a cheap model MEASURABLY fails (D-027). The cascade is tool-free, so
  every Ollama model runs the default retrieval path; only `retrieval_mode=walk` is closed to them.
- **Fails CLOSED, twice over.** An empty `message.content` RAISES instead of returning `""` — the two
  ways to get one are both silent (a thinking model that spent its whole budget reasoning, and a
  refusal Ollama reports as a normal 200), and an empty string would be composed into an answer.
  And an embed batch that returns fewer vectors than inputs raises rather than mis-align the catalog.
- **The embedder does NOT move, and that is the deliberate half of this decision.** Ollama Cloud
  hosts no embedding model at all (its embedders are local-only), and any Ollama embedder is a
  different coordinate system from `gemini-embedding-001` — so switching `LIBKB_EMBED_MODEL`
  invalidates every catalog row and every retrieval number in the SCORECARD. Generation moves first:
  cheap, reversible, and A/B-able against the numbers we already have. The embed path is IMPLEMENTED
  (`_embed_ollama`, with `ollama_embed_query_prefix` standing in for gemini's task-type asymmetry,
  which open embedders express as a query-side instruction prefix) so the head-to-head is one
  `reindex --fresh` into a separate db — never a halfway switch.
- **A side-fix the fourth provider forced:** `GET /api/models` labelled every non-Gemini model
  `dashscope` and gated its availability on the DashScope key — so a Bedrock model already showed as
  unavailable when only AWS was configured. Replaced by `LLM.provider_of()`, one place, and an
  Ollama entry is available if the host is local (no key needed) or a cloud key is set.
- Still UNMEASURED, and must not be claimed until it is: open-weight answer quality on this library.
  The Qwen-vs-Gemini A/B was never run either (SCORECARD §5.2); this adds a third arm to that gap.

## D-062 · 2026-07-20 · Multi-turn + a semantic answer cache + a cross-document synthesis route (and decompose, refuted)
The product session. Four capabilities, each shaped by the same constraint the retrieval redesign set:
**keep the answer call single-shot — never let history or aggregation re-inflate it into an O(T²) walk.**

- **Multi-turn without O(T²)** (`conversation/store.py` + `agent/contextualize.py`). A transcript store
  (conversations + messages, same gitignored db) persists every turn; a *lite* call rewrites a
  follow-up ("tell me more about it") into a STANDALONE query BEFORE retrieval. History touches only
  the cheap rewrite — the expensive cascade call never sees it. No-op and free when there is no history
  (CLI/eval unchanged). `enable_context_rewrite` default-on. Sidebar: title = first user question,
  editable, deletable, pin ≤5 (D-013 English UI).
- **Semantic answer cache** (`cache/store.py` + `cache/lookup.py`), default-ON. A grounded, confident
  answer is stored keyed by its query embedding; a later paraphrase within cosine threshold returns it
  with **0 LLM calls**. Honesty is not traded for speed: **never cache a NOT_FOUND**, never cache
  without citations, never below `answer_cache_min_confidence`. Threshold is **precision-first (0.92,
  calibrated live)** — a cross-topic near-neighbour ("chunking in RAG") already sits at 0.875, so the
  bar must sit above the confusers, not merely above chance. A hit is transparent (UI shows "from
  cache" + citations); entries are curatable and page-invalidatable; a global toggle lets a user demand
  the model answer everything. Viewable/editable in the Observatory.
- **Synthesis route** (`agent/synthesizer.py`) for AGGREGATIVE questions ("what are the trends across
  all X?") that no single page answers, so no index fixes. A registry route (D-061): aggregative-detect
  (lite) → wide scan → parallel *lite* MAP per page → strong REDUCE over compact findings, cited; empty
  harvest = honest NOT_FOUND. Defers to the cascade on a single-fact question. **UNMEASURED on purpose**
  — it needs an aggregative held-out set before it earns a number.
- **Query decomposition — BUILT, MEASURED, REFUTED** (SCORECARD §3.2). Split a compound question into
  sub-questions → sharp parallel retrieval per part → one combine call. Attacked a real measured cause
  (AllGold@20=93.5% but @3=29.6%), yet lost on qwen-plus (comparison 74.1%→63.0%, temporal
  83.3%→66.7%) — and NOT from starvation: at `per_q=6` it read MORE pages than baseline and still lost,
  give-ups turning into wrong answers. The split-recombine discards the joint signal a wide single-query
  basket keeps. **Unregistered by default** (`enable_decompose_route`); engine + prompts + tests stay so
  the measurement reproduces. Added `force_route` (measurement knob). Joins the measured-refuted list
  alongside NMS / BM25 / cross-encoder rerank / auto / the confidence gate.

The through-line: every one of these was measured to decide keep-or-discard, not applied because it is
fashionable. Two shipped (cache, multi-turn), one shipped-but-unmeasured (synthesis, honestly flagged),
one refuted and shelved (decompose). Also this arc: the repo was published **public** at
`github.com/LeDat98/toshokan_kb` under **PolyForm Noncommercial 1.0.0** (source-available; MIT intended
later) with a measured-numbers README — the private-client, retail, ai-news, benchmark and eval data
all gitignored and verified absent from the remote (D-020).

## D-061 · 2026-07-19 · Agent architecture: home-grown runtime, open protocols (MCP/A2A/AG-UI) to spec, no framework dependency
Plan of record: `docs/AGENT_ARCHITECTURE.md`. The silent cascade becomes a **narrated, cost-aware,
self-reflective multi-agent orchestration**, and a foundation for skills / tool-calls / MCP that can be
extended later **without a rewrite**. The load-bearing choices (principles P11–P16 in the doc):

- **Home-grown runtime, standard wire-protocols.** We do NOT adopt a heavyweight agent engine
  (LangGraph, CrewAI) — it fights the project's minimalism and model-independence. We DO conform to the
  three open protocols as message contracts: **MCP** (agent↔tools/data), **A2A** (agent↔agent),
  **AG-UI** (agent↔frontend). A protocol is a JSON shape over SSE, not a runtime; conforming needs no
  framework import. This buys genericity + interop without lock-in, and without reinventing the specs.
- **`client.py` stays the single model gateway (D-016 stands).** Multi-provider (Gemini, Qwen via
  DashScope, Haiku via Bedrock) is ALREADY proven there, so the loop runs on structured JSON and every
  provider keeps working. No agent SDK becomes the model layer.
- **Agentic only when it earns it (Adaptive-RAG / FLARE).** Simple queries stay on the cheap single-pass
  cascade; only complex/uncertain queries escalate into the reflective loop and load full context. The
  escalation ladder (headers → sections → full page → widen) is the cascade's EXISTING branches, made
  explicit and narrated — we wrap, not rewrite.
- **Narration is real and near-free.** First-person "thoughts" piggyback on LLM calls we already make
  (triage/answer), so ~0 extra cost; a dedicated Narrator agent is opt-in. Narration must describe what
  actually happened (real paths/counts/branch), never decorative progress.
- **Honesty not traded for UX.** Answers are NOT backend-token-streamed — the anti-fabrication gate
  (D-057) must see the whole answer first; the UI reveals the finished, verified answer client-side.
- **No agent framework in the dependency tree.** Pydantic AI / OpenAI Agents SDK may be run as a
  throwaway reference spike only; UI design stays 100% ours (protocols touch only the backend event
  stream, never how the UI looks).

Phased, each behind a flag with a falsifiable check: **A** — narrated self-reflective loop on the
cascade + AG-UI-shaped events + inline thinking-timeline UI (check: simple-query cost/latency do NOT
regress; honesty holds); **B** — typed agent roles + registry + A2A-shaped descriptors, generic
Orchestrator (check: a throwaway 5th agent registers without editing the orchestrator); **C** — MCP
client seam (tools→`ToolSpec`) + tool-agent + A2A descriptor (check: a sample MCP server runs
end-to-end with zero change to the cheap path). Techniques referenced: Self-RAG, FLARE, Adaptive-RAG /
Cost-Aware Query Routing, ReAct.

## D-054 · 2026-07-16 · Pinpointed + fixed the ~0.5% concurrency NoneType: a shared sqlite connection race
The rare NoneType D-049 left open (`answer_query_crashed`, caught by the fail-closed net) finally
logged its traceback under the D-053 A/B: `catalog.count()` → `SELECT COUNT(*) … .fetchone()[0]`, with
`fetchone()` returning **None** — impossible for `COUNT(*)`, which always yields a row. Root cause: the
eval/ingest ThreadPool shares ONE `sqlite3.Connection` (`connect` sets `check_same_thread=False`).
sqlite3 permits cross-thread use but does NOT serialise concurrent `execute()` on one connection; two
threads interleaving cursor state made a query see a torn/empty result (~0.5% of concurrent queries).
Fix: a reentrant `threading.RLock` on `Catalog` guards every connection touch (`count`, `_load`,
`add_page`, `remove_page`, `clear`, the meta reads, the FTS reads). Reentrant because `search()` →
`_load()` nest. The vector matrix is cached in memory, so the hot search path takes the lock only on a
cold or after-write reload, not per query — negligible contention. This is the write-lock backlog #1
named for INGEST, arrived at from the read side. Verified: 0 crashes across the D-053 runs (the smoke
n=8 had hit one). tests/test_concurrency.py still green.

## D-053 · 2026-07-16 · Cheap-reader selector (LLM reads bodies to pick the basket) REFUTED
The user's idea: header-triage chooses from vague metadata (and the D-051 diagnostic showed it drops
24 pts of gold, keeping only 69% AllGold and under-filling the basket to ~4 pages) — so replace it with
a CHEAP subagent that READS the top-N candidate bodies and picks the basket, hopefully selecting better
AND cheaper (few bodies on the lite tier; the strong answerer then opens only the picks). Built as
`triage_mode="read"` (`_triage_read`, `prompts/select_read.md`, lite tier, `triage_read_n=10` bodies
truncated to `triage_read_chars`). Per-model token accounting added to the client to price it.

**MEASURED (n=80, basket=20, gemini-3.5-flash vs -3.1-flash-lite selector), and REFUTED:**

    metric        headers   read      Δ
    ANSWER         80.3%    73.2%    −7.0     ← worse, and every kind fell
      inference   100.0%    88.5%   −11.5     ← the EASIEST (single-doc) kind hit hardest
      temporal     55.6%    50.0%    −5.6
      comparison   77.8%    74.1%    −3.7
    coward          7.0%    12.7%    +5.6     ← hands the answerer worse evidence → gives up more
    strong tok/q   13,077   10,954  −2,123
    lite   tok/q      231    5,295  +5,065
    $/1000 q       $3.94    $3.68   −$0.26    (~7% cheaper under a 4× lite/strong price ratio)

**~7% cost for −7 accuracy is a bad trade.** Two reasons it lost, and the second is the real lesson:
1. A LITE model reading bodies selects WORSE than a STRONG model reading headers — it confidently
   prunes wrong, handing the answerer less/worse evidence (strong tokens FELL 2.1k; coward rose).
2. **The system's accuracy rides on the LAST-RESORT net, not on triage's pick quality.** Header-triage
   is stingy (69% AllGold) but CHEAP, and when its ~4-page basket is insufficient the cascade opens the
   top-20 candidates IN FULL (93% gold, D-052) and recovers. The cheap-reader picks whole pages
   confidently and short-circuits that net — so "reads carefully but breaks the safety net" loses to
   "chooses badly but lets last-resort catch it." A STRONG reader would select better but is no longer
   cheap (the whole point). Kept default-off (`triage_mode`) for revival with a different design.

The concurrency fix (D-054) is the keeper from this experiment; per-model token accounting stays too.

## D-052 · 2026-07-16 · Cash in the diagnostic: the basket is 10 → 20, and honesty did not move
D-051's diagnostic said the multi-source ceiling is the basket, not triage (AllGold@10 = 75%, @20 =
93%). D-052 tests whether opening a bigger basket actually cashes that in or just DROWNS the answerer
("lost in the middle" — more evidence can lower accuracy AND honesty, so it had to be measured).

**Basket sweep on the text catalog (gemini-3.5-flash, snippet on, coverage off), 2 seeds × n=200:**

    basket   ANSWER (s0/s1)   temporal   comparison   coward        honesty(null-only n=301)
    10        72.2 / 75.0      50 / 49    69 / 72      15.3 / 14.2   —
    15        72.2 / —         49         72           17.0          — (a dead spot: no gain)
    20        77.3 / 79.0      58 / 58    72 / 75      11.9 / 10.2   99.3% (299/301)

- **ANSWER +4.5, both seeds** — a bigger, more robust win than the card snippet (D-050, +1.7).
- **temporal +7–9** (both seeds landed 58%): the multi-source kind the whole thread was chasing
  finally moved. comparison +3. Even single-hop inference rose (91→97 / 97→98).
- **coward FELL 3–4 points** — the opposite of drowning: the extra evidence let the answerer commit
  where before it wrongly gave up.
- **Honesty HELD at 99.3%** null-only (n=301), vs the ~91% D-043 saw for basket 3→10 on *qwen*. The
  honesty cost was a qwen artefact (that model is overconfident, D-046); on gemini it does not appear.
- Cost: ~+22% tokens on answerable (~11.5k → 14k). basket=15 is a genuine dead spot — 20 is the jump.

**Shipped: `cascade_max_pages` default 10 → 20.** It is a CEILING, not a floor — `_open_basket` opens
only the pages triage actually put in the basket, so the extra cost is spent ONLY where the evidence
exists (multi-hop queries with many good candidates); a single-hop corpus barely notices. `minimum`
users and cost-sensitive deployments set `LIBKB_CASCADE_MAX_PAGES=10` back.

Two open threads this leaves: (1) actual answer (77–79%) still sits below the AllGold@20 = 93% ceiling
— basket>20 was NOT swept (15→20 was non-monotonic, so do not extrapolate; measure it); (2) temporal
at 58% is still its own floor — its residual is selection-vs-synthesis, unmeasured (needs a probe of
the ACTUAL triage basket's article coverage, D-051). Those are the next two levers, in that order.

## D-051 · 2026-07-16 · Coverage-aware triage prompt REFUTED; the multi-hop ceiling is BASKET SIZE, not selection
The plan after D-050 was that a smarter *selection policy* would crack multi-hop: tell triage a
comparison/temporal question needs a page for EACH part, not ten variations of its most obvious half
(`prompts/triage_coverage.md`, injected via `{{coverage}}`, gated by `triage_coverage`). **Measured on
the text catalog, snippet ON in both arms, 2 seeds × n=200 — REFUTED:**

    seed   ANSWER Δ   temporal Δ   comparison Δ   inference Δ
    0       −1.7        0.0 (flat)   −1.5           −3.1
    1       −0.6       −2.2         +1.5           −1.6

It did not lift the multi-hop kinds and cost a little overall. Kept default-OFF (mechanism preserved,
like the confidence gate D-046).

**WHY — the diagnostic that reframes the whole "SELECTION quality" thread** (`scratchpad/diag_multihop.py`,
model-free, on the live text catalog; AllGold@k = the top-k DISTINCT gold articles ALL present, n=1439
comparison+temporal):

    kind          AllGold@10   @20     @50
    comparison      75.2%      92.9%   97.2%
    temporal        75.6%      92.6%   99.0%

- **Retrieval is not the wall:** @50 = 97.9% — the sieve almost always fetches every gold article.
- **The BASKET is the wall:** the answerer opens `cascade_max_pages=10` pages. Even a PERFECT triage
  that picked the 10 best distinct articles caps multi-source recall at **~75%** (AllGold@10). Opening
  20 would lift the ceiling to **~93%**.
- **comparison (~73% answer) already sits AT its basket-10 ceiling (75%)** → no selection policy can
  help it; only a bigger basket can. That is why the coverage prompt was inert on comparison.
- **temporal (~50% answer) is 25 pts BELOW its 75% ceiling** → temporal alone still has selection-or-
  synthesis headroom; which one is unmeasured (needs the actual triage basket's article coverage, not
  the sieve's — the next probe).

**Consequence for the roadmap:** "improve SELECTION" was the wrong frame for comparison — its lever is
`cascade_max_pages` (basket size), a token-priced retrieval-depth dial (D-049 raised the fetch window
but NOT the basket), and it must be MEASURED against "lost in the middle", not assumed. temporal keeps a
genuine selection/synthesis gap to localise first. The card-richness lever (D-050) is spent; the next
real-points lever is the basket, then temporal's residual.

## D-050 · 2026-07-16 · Restore the sieve's "why THIS page" to the triage card on a TEXT index (small win)
Adopting text-indexing (D-039) silently thinned the triage card. A QUESTION row stored the matched
question as `Hit.text`, and triage showed it (`Answers questions like: "…"`, D-035) — the single most
discriminative line on the card. A TEXT row stores an EMPTY display text (the 8k-char body must never
ride into a 59-token/page triage prompt), so that line never fires and triage was left choosing from a
bare spine label + section titles. The sieve's *reason* for ranking a page was discarded exactly where
the librarian picks.

`library/sections.py::query_snippet` recovers it, **model-free and deterministic**: score each sentence
of the body by how many DISTINCT query content-words (stopwords stripped, vi+en) it carries, show the
best as `Relevant passage: "…"`. Returns "" when nothing overlaps — an honest blank beats a misleading
first sentence. Fires only when `Hit.text` is empty (i.e. only on a text index; the question path is
untouched). `triage_snippet_chars` (default 200 ≈ 50 tok/candidate) gates it; **0 = off**, which is the
clean A/B switch.

**MEASURED on a TEXT-indexed MultiHop catalog (2,077 pages, gemini-3.5-flash, 2 seeds × n=200):**

    metric      OFF (chars=0)   ON (chars=200)    Δ
    ANSWER        72.7%           74.4%          +1.7   (256→262 / 352, both seeds positive)
    coward        16.5%           15.1%          −1.4   (fewer wrong give-ups, both seeds down)
    HONESTY(48)   47/48           47/48          ±0.0   (honesty-neutral, the non-negotiable held)
    tokens/q     ~10.6k          ~11.3k          +7%

A **small but consistent** win: both seeds moved ANSWER up and coward down, honesty was flat to the
case, and it costs nothing at ingest (no generation). The per-KIND deltas swung wildly and OPPOSITELY
between seeds (seed0 inference +9/temporal −9; seed1 the reverse) — at 4–6 cases/kind that is NOISE and
it cancels in the pool. **Shipped default-on** (off-switch retained). What it did NOT do is move the
multi-hop ceiling: comparison ~71%, temporal ~50% are still the floor and are untouched by a richer
card. That localises the real bottleneck to the triage *selection policy* for questions that need 2+
sources (coverage), not the information on each candidate — the next lever, not this one.

## D-049 · 2026-07-16 · Retrieval DEPTH is one dial, three tiers; the new defaults are basket=10, fetch=50
D-048 said scale-invariance comes from a wide window and a dedicated reranker does not help. This
turns that into a shipped default. `cascade_depth` ∈ {minimum, default, deep} sets how many
candidates the sieve fetches and triage sees:

    minimum  20    the pre-D-048 behaviour; leanest
    default  50    R@50 is near scale-flat to 10k; the new default
    deep    100    for huge corpora where R@100's extra flatness pays (57k: 0.920 vs R@50 0.863)

**MEASURED clean on MultiHop (bug-fixed, concurrent), qwen-plus:**

    config                    ANSWER   HONESTY(301)   tokens/q
    basket 3  · fetch 20      73.9%      92.7%          6,572     ← the old default
    basket 10 · fetch 20      82.6%      90.7%         10,945
    basket 10 · fetch 50      84.0%      91.0%         15,784     ← the new default

The whole move (basket 3→10, fetch 20→50) is **+10.1 answer for −1.7 honesty** and 2.4× tokens.
basket 3→10 is the big win (+8.7); fetch 20→50 adds +1.4 here at FLAT honesty — small now, but the
scale curve says its value GROWS with corpus size (the R@50−R@10 gap widens 0.04→0.16 over 2k→57k),
so it is scale INSURANCE, priced at ~$0.006/query on qwen. `basket` (pages opened) drives cost;
window width only adds ~4k triage-header tokens (the 50 candidates are never loaded into context).

Three implementation notes:
1. `cascade_fetch_n` and `cascade_k` are DERIVED from the tier (a `model_validator` fills them when
   left at 0), and equal by design — the whole window is triaged in one call, which makes the
   round-based "widen if insufficient" loop redundant at width (insufficiency is now handled by
   re-open-in-full and last-resort, D-035). Both stay settable for fine control and for the tests
   that still exercise the multi-round path with a small `cascade_k`.
2. The confidence gate (D-046) stays default-off: it was refuted on qwen (overconfident), and P6
   honesty holds at 91% without it. Honesty is bought by evidence, not by the model's self-report.
3. Two robustness fixes the wide window exposed: `{"basket": null}` (Qwen's "nothing relevant") no
   longer slices None; and `answer_query_safe` now fails CLOSED on ANY exception (not just LLMError)
   with the full traceback logged — a bare TypeError would otherwise 500 a real request instead of
   becoming an honest NOT_FOUND. A rare (~0.5%) concurrency-only NoneType survives, is caught by
   that net, and will surface its traceback via `answer_query_crashed` the next time it fires.

## D-048 · 2026-07-16 · Scale-invariance lives in the WIDE window; a cross-encoder reranker was REFUTED
The user reframed the whole target: not "95%" but "95% that HOLDS as the corpus grows 2k → 10k."
Two measurements settled the method, and one of them killed the obvious idea.

**① The FiQA scale curve (model-free, 648 human queries, cached vectors — free).** Needle-in-a-haystack
per query: rank a query's gold docs mixed into N random distractors, grow N, watch recall.

    corpus N      R@1     R@10     R@50    R@100
       2,000     0.488    0.952    0.988    0.997
       5,000     0.450    0.911    0.976    0.987
      10,000     0.409    0.862    0.961    0.976
      57,638     0.316    0.701    0.863    0.920

**The scale problem is entirely in the NARROW window.** R@1/R@10 collapse with corpus size; R@50 is
nearly flat 2k→10k (0.988→0.961, −2.7) and R@100 flatter still (0.997→0.976). So retrieval IS
scale-invariant if you read a wide enough window — the evidence stays in the top-50/100 as the corpus
grows. The bottleneck then shifts from RETRIEVAL to SELECTION: picking the right pages out of the
wide window (which in this system is the LLM TRIAGE step).

**② A cross-encoder reranker was the textbook fix — and MEASURED, it HURTS.** qwen3-rerank (top of
the MTEB-R leaderboards; reached via the standard `dashscope-intl` host — the user's MaaS host does
not serve rerank, but the same key works on intl) on FiQA top-50, 120 queries, verified no bug (API
returns 50 sane scores):

    N        stage         R@1      R@5     R@10
    2,000    bi-encoder    0.530    0.904    0.979
    2,000    + rerank      0.478    0.839    0.929   (−5.2 / −6.5 / −5.0)
    57,638   bi-encoder    0.378    0.684    0.766
    57,638   + rerank      0.288    0.568    0.695   (−9.0 / −11.6 / −7.1)

**Why:** the reranker only helps when the first stage is WEAK (the BM25 assumption behind the
textbook advice). Our first stage is `gemini-embedding-001`, already strong — so a reranker that is
merely comparable REPLACES a good order with a not-better one and loses. Reranking is not free lunch
with a strong embedder. Joins NMS, BM25-fusion, the page digest and `routing_mode=auto` on the list
of plausible ideas this project adopted the discipline to REFUTE by measurement (~$0.05 here, vs the
$2.5 full run the smoke-first habit avoided). Do not re-add a reranker without a first stage weak
enough to need one.

**The chosen path (no new dependency, model-light):** widen the retrieval window and let the existing
cascade compress it — `cascade_fetch_n` and the triage window up to ~50 (scale-stable), `basket` at
~10, and the LLM TRIAGE is the de-facto reranker (since a dedicated one does not beat the embedder).
A `fetch=100` "deep search" mode is worth keeping for very large corpora, where R@100's extra
flatness pays (57k: 0.920 vs R@50 0.863). Cost is bounded and asymmetric: a wider window costs only
~+4k tokens on the ONE triage call (headers, not content — the 50 candidates are NEVER loaded into
context); the real cost is the BASKET (pages actually opened), which is the +61% D-043 already
measured. Being validated now: does triage still pick well from a 50-wide menu (the SELECTION
question), measured on MultiHop at fetch=50/basket=10.

## D-047 · 2026-07-15 · Concurrency for eval (backlog #1): a thread pool, because the work is I/O-bound
Ingest and eval spend ~all their wall-clock WAITING on a provider (embed/generate), and CPython
releases the GIL during that wait — so a **thread pool** parallelises them with no processes and no
serialization: one shared LLM client, one shared read-only catalog. MEASURED trigger: the confidence
tuning run (301 null + 150 answerable) was taking **~3 HOURS** sequentially on qwen-plus; a 10k-page
ingest would be ~5 hours. `libkb/concurrency.py::parallel_map` runs up to `eval_concurrency` (default
8) in flight, PRESERVES input order in the result (so a saved eval file still lines up with its
cases) while letting them finish out of order, and reports progress per completion. `workers <= 1`
is the exact old sequential loop — the safe fallback if a provider starts throttling.

Three correctness points that a naive `ThreadPoolExecutor(map)` would get wrong:
1. **Token attribution.** The eval used to price each case by the delta of the global token counter
   before/after — meaningless once calls interleave. So under a pool the per-case figure is left at
   0 and the whole RUN is priced from one counter delta (`Report.input_total`); the counter itself
   is now bumped under a `threading.Lock` (an `int +=` is a read-modify-write and would lose updates).
2. **SQLite under >1 writer.** WAL gives one writer + many readers; a second writer got SQLITE_BUSY
   *instantly*. Added `PRAGMA busy_timeout=30000` so a concurrent write WAITS for the lock instead of
   crashing — needed the moment ingest (or trajectory logging) writes from a pool.
3. **The vector matrix is built ONCE** before the pool starts (`catalog.vectors()`), so N threads do
   not race to lazily load a 290MB matrix N times.

VERIFIED live: 8-wide eval-multihop on qwen-plus — no 429, no thread crash, correct honesty/answer
numbers, order-preserving save. Applied to `eval-multihop` (the slow one) this session. STILL
SEQUENTIAL and noted as the remaining half of backlog #1: `runner.run_eval` (the `libkb eval` path)
and INGEST (`reindex`/`import` write catalog rows from the pool, so they need a write-lock around
`add_page`/`remove_page` on the shared connection — busy_timeout alone is not enough for one
`sqlite3.Connection` shared across threads).

## D-046 · 2026-07-15 · The basket is now TWO knobs: evidence size, and a separate confidence gate
D-043 named it and this splits it. `cascade_max_pages` (the basket) governs how much evidence the
answerer opens; a NEW knob `cascade_min_confidence` (ordinal low<medium<high) governs how sure the
answerer must be before the library speaks. `compose_answer` already asked the model for a
`confidence` — it was reported and never used. Now: a `sufficient` answer whose confidence falls
below the caller's floor becomes an honest NOT_FOUND (fail-closed, P6). The two are independent, so
the basket can be widened for multi-hop accuracy (D-043: +3.9 at basket 10) without the improvisation
rate rising with it (the honesty the wider basket cost — 30 vs 22 on 301 unanswerable — is what the
gate is there to buy back).

**Shipped default `low` = gate OFF (today's behaviour unchanged).** The mechanism is the deliverable;
the VALUES — how wide a basket, how high a floor — are a MEASURED decision, deliberately not guessed
(this project has been burned six times guessing). 169 tests green; a regression test pins that a
`low`-confidence sufficient answer is served at floor `low` and refused at floor `medium`.

**The tuning is NOT yet run, and it has a real confound to design around:** eval-multihop runs on
`qwen-plus` for cost, and DashScope does NOT enforce `response_schema` (D-040) — so Qwen may omit the
`confidence` field, which `compose_answer` then reads as `medium`. On Qwen the gate is therefore only
partly observable (it can reject `low`-vs-`medium`-floor, but only when Qwen bothers to emit `low`).
A clean confidence signal needs Gemini (schema-enforced) — but gemini-3.5-flash on ~500 eval queries
is ~$7, over budget. So the tuning grid (basket ∈ {3,10} × floor ∈ {low,medium,high}, on the
MultiHop null set for honesty AND the answerable set for accuracy) is a spend+model decision left to
the user, not run blind.

## D-045 · 2026-07-15 · `index_kind` is a config knob, default `text` — the flywheel is no longer the default
The sieve now indexes the **page body** by default (`LIBKB_INDEX_KIND=text`), not generated
questions. This closes D-039: on every EXTERNAL benchmark text ≥ questions (bench-multihop
AllGold@20 **0.935** vs 0.695; FiQA nDCG@10 0.621) **at zero generation cost**, and a real corpus
(a 22,633-article legal code ≈ 34M generated tokens through the flywheel) is only reachable at all
without per-page generation. `index_kind` ∈ {`text`, `questions`, `both`}.

Three implementation facts worth keeping:
1. **A text row is embedded from the full body but STORED with an empty display `text`.** `Hit.text`
   rides into the triage card at a ~59-token/page budget (D-035); an 8,000-char body there would
   blow the whole point of triage. Triage falls back to spine label + section titles — the signal it
   was designed on. The embedding still carries the body.
2. **Furniture no longer depends on generation.** The flywheel used to fill `one_line`/`keywords` in
   the same call as the questions (the ingest contract, D-037). A text index generates neither — but
   the splitter already sets a deterministic first-sentence `one_line`, so the spine label survives.
   Keywords are simply absent under text; an acceptable, honest loss.
3. **The catalog is LOCKED to one representation**, mirroring the embedder lock (D-028-era). Mixing
   `questions` rows and `text` rows in one catalog re-creates metric bug 6.6 (question→question
   cosines dominate question→text ones at max-pool), silently. A mismatched write RAISES; changing
   kind = `reindex --fresh --index-kind <k>`. **Consequence, deliberate:** with the default now
   `text` and the LIVE catalog still on `questions`, a new ingest's index attempt is refused by the
   lock and surfaces in `report.index_failures` — the honest signal that the library must be
   reindexed to adopt text, not a silent half-migration.

**ADOPTED on the live library** (user's call, same session): `reindex --fresh --index-kind text` →
**250 pages, 250 rows, kind=text, 0 generation tokens**. Held-out cascade held at **96.7% (29/30),
Gate PASS, 3,960 tok/query** (SCORECARD §1.1) — not a clean A/B (the corpus changed since the 93.3%
questions run), but the honest number for what ships now, and the single miss is an ANSWERER
sycophancy issue, not the sieve (which reached the exact page). This wiped the warm question rows and
with them the free LOI probe query set (`all_questions()` / `probe-recall` use catalog rows AS
queries — meaningless once the rows are page bodies); `probe-index` still builds all representations
itself for comparison. The vocabulary bridge (SCORECARD §5.1, colloquial-VI where `questions` wins
R@1) is why the flywheel code is KEPT, not deleted; switching back = `reindex --fresh --index-kind
questions`.

Two eval-infra defects a re-ingest sprang, fixed alongside: `runner.py::_deepest_reached` now counts
a stale `target_page_id` a miss instead of crashing the whole paid run (fail-soft, like ingest); and
`evals/holdout.json`'s 3 PDF-book targets were remapped to the re-ingested pages (they were frozen at
the old ULIDs). A frozen held-out set is silently invalidated by a re-ingest of any book it targets.

## D-044 · 2026-07-15 · FiQA: the first EXTERNAL number, verified by pytrec_eval, and it is only mediocre
`libkb bench benchmarks/fiqa` — 57,638 docs, 648 questions real people wrote, human qrels. Pure
text-index, **0 generation tokens**. nDCG@10 **0.621** · R@1 **0.316** · R@10 **0.701** · R@100 **0.920**.

**Cross-checked bit-for-bit against `pytrec_eval` (the official TREC scorer): identical.** After six
metric bugs this session, this is the first check that CONFIRMED. The number is real. It is also not
good: **30% of real questions have their answer outside the top-10** — a hard failure for a cascade
that opens ~10 pages. The R@10→R@100 gap (0.70→0.92) is the session's recurring shape: the sieve
finds the evidence, the window is too narrow. Above BM25 (0.236), but BM25 is a weak baseline and
clearing it means nothing. **Discipline recorded: when a metric surprises you, verify against a
reference implementation before quoting — that is what caught the other six.**

## D-043 · 2026-07-15 · A broken call must fail CLOSED, and the basket is TWO knobs wearing one hat
Two findings from the P6 test at n=301, both load-bearing.

**(1) The fail-open bug, and the principle that replaces it.** `generate_json` used to take a
malformed/truncated response and ask the model to *"fix this output"*. A truncated `{"answer": "J` is
not a formatting error — it is a call that did not happen, and asking a model to "repair" the fragment
asks it to hallucinate the rest. MEASURED: 40 of 301 unanswerable questions came back as a
one-character answer (`"J"`, `"F"`, `"X"`) carrying an invented `"sufficient": true`. That is the
exact failure P6 forbids, manufactured by the infrastructure. Fixed two ways, both now principles:
  - `generate_json` **re-asks the original question** (another go at answering, not at rationalising a
    fragment), validates the required keys, and **raises** if it still won't comply. `answer_query_safe`
    turns the raise into an honest NOT_FOUND. **A broken call fails CLOSED, never OPEN.**
  - `compose_answer` **does not take the model's `sufficient` on trust** — an "answer" under 2 chars is
    not an answer, whatever the flag says. (2 chars, not more: MultiHop's comparison answers are
    "Yes"/"No".) This guard lives at the function that decides whether the library speaks, and it must
    fail towards silence.
  Effect: the P6 "violation" rate fell from a fake 20.6% to a real ~7%. **The system was never as bad
  as the number said; its infrastructure was inventing answers on its behalf.**

**(2) `cascade_max_pages` is overloaded, and the fix is a separate confidence gate.** At n=301,
fail-closed: basket=3 refuses honestly 92.7% (22 improvised), basket=10 refuses 90.0% (30 improvised).
Yet basket=10 also answers MORE (n=200 accuracy 73.9%→77.8%, comparison +9.1, temporal +4.4). The one
knob controls both *how much evidence the answerer sees* and *how eager it is to speak at all*: more
evidence → more things look relevant → more willingness, right AND wrong. These must be split — raise
the basket (the sieve HAS the evidence: R@100 0.92, AllGold@20 0.935) and add an INDEPENDENT confidence
gate in `compose_answer`. **This is only visible at n=301; at n=24 the 2-case gap was noise.** It is
now the top design item. Do NOT ship a basket bump without the gate.

Also this session: two more silent-failure defects fixed — `embed()` had no retry and leaked raw
httpx errors past `answer_query_safe` (killed a paid 301-run); the DashScope client had no timeout
(a hung socket froze a run 30 min at 0% CPU). Both are the same disease as D-040/D-041: a failure
that does not announce itself. Timeouts, retries, and loud failure are now in `client.py`.

## D-042 · 2026-07-14 · P6 HOLDS at scale (91.7% honest refusals) — and D-039's headline claim was WRONG
The first cascade eval on external ground truth. 200 stratified MultiHop cases, `qwen-plus`, basket=3
(the shipped config), answers saved.

    ANSWER    73.9%   of the 176 answerable questions
    HONESTY   91.7%   of the 24 UNANSWERABLE ones correctly refused   ← P6, measured at last
    coward    13.6%   answerable questions it wrongly gave up on
    by type   comparison 60.6% · inference 93.8% · temporal 65.2%
    cost      6,572 input tokens/query

**The honest-NOT_FOUND rule holds.** 22 of 24 questions the library genuinely cannot answer got an
honest refusal instead of an improvisation. Every eval this project has ever run contained only
*answerable* questions — which quietly rewards a system for guessing. This is the first one that
punished it, and the system passed. The price is 13.6% cowardice, and both numbers must always be
quoted together: a librarian who refuses everything scores 100% honesty and is worthless.

**And D-039's headline was wrong.** I wrote — in the decision, and in `evals/multihop.py`'s docstring
— that *"AllGold@3 is not a diagnostic; it is the ceiling on the answer."* The data says no:

    type          AllGold@3      ANSWER
    inference        14.0%   →    93.8%     ← 80 points ABOVE the "ceiling"
    comparison       40.8%   →    60.6%
    temporal         35.2%   →    65.2%

`evidence_list` in MultiHop-RAG lists **every** fact that supports an answer, not the **minimum set
needed** to reach it. "Who in crypto is on trial for fraud?" → *Sam Bankman-Fried*: one article that
names him is enough; the other two are corroboration. So AllGold is a **strictness ceiling on
evidence assembly**, not a ceiling on answers — a metric I built, believed, and had to be refuted by
a run I nearly did not commission. (A second explanation cannot be excluded and should not be:
**the model may simply know who SBF is.** Prior-knowledge leakage inflates `inference` and we have no
way to subtract it here.)

The real weakness is where multiple documents are genuinely required: **comparison (60.6%) and
temporal (65.2%)**. Those are what a bigger basket has to earn.

## D-041 · 2026-07-14 · Qwen REFUSES some content, silently. That is a data-integrity property, not a bug.
DashScope returns `choices: null` when its content filter trips — no error, no status code, no
message. MEASURED on MultiHop-RAG: `qwen-flash` refuses to summarise a news article about **the Epoch
Times** (a paper critical of the Chinese government); `gemini-3.1-flash-lite` handles the same page
without comment. Unguarded, the refusal surfaced as `TypeError: 'NoneType' object is not
subscriptable`, which `index_page_safe` logged and swallowed — so **the page silently left the
corpus**.

`client.py` now raises a named `LLMError` on an empty `choices`. But the fix does not make the
problem go away, and nobody should pretend it does:

> **If you index a corpus with a Chinese-provider model, part of your corpus will disappear, and you
> will not be told which part.** For a statutory corpus that may be irrelevant; for news, human
> rights, or anything geopolitically live, it is a hole you cannot accept.

The rule that follows: Qwen is fine for the BULK tier on neutral material (it is 30× cheaper than
gemini-3.5-flash on output), but **the refusals must be loud and the fallback must exist**. Six pages
here; a policy question at scale.

## D-040 · 2026-07-14 · A schema is a REQUEST, not a guarantee — and "best-effort" hid a 21% data loss
Gemini enforces `response_schema` server-side. DashScope only honours `json_object` and leaves the
shape to the model, so `qwen-flash` periodically returned `"questions": ["…", "…"]` where the schema
asked for `[{"vi": …, "en": …}]`. Valid JSON, wrong shape → `item.get(lang)` raised AttributeError →
`index_page_safe` logged it and moved on.

Result: **439 of 2,079 pages (21%) were written to the library and never entered the catalog.** The
sieve could not see a fifth of the corpus. And the import printed:

    Imported into 'News': 6 shelves · 58 books · 2079 pages · catalog now 18050 questions

**Silent data loss looks exactly like success.** Three fixes, and the third is the one that matters:
1. `_read_item` bends instead of breaking — a bare string, a dict with odd keys, junk: salvage what
   is there. Any provider can misbehave; the parser must not be the thing that breaks.
2. `generate_json`'s repair retry only catches `JSONDecodeError`, never a schema mismatch — which is
   why it never fired. Noted; a real validator is still owed.
3. **`index_page_safe` returns a bool and the caller must look.** `ImportReport` counts
   `indexed_pages` and lists `index_failures`; the CLI prints them with `!!`. A page in the library
   but not in the catalog is invisible to the sieve — it may as well not have been imported, and an
   import is not allowed to call that a success ever again.

I had written this exact risk into `client.py` when wiring DashScope ("Qwen honours `json_object` but
does NOT enforce a schema server-side") and then **did not test it**. Writing the warning is not the
same as checking it.

## D-039 · 2026-07-14 · MultiHop-RAG is in (2,079 pages, 2,255 ground-truth queries) — and the cascade CANNOT do multi-hop
The user asked for a corpus big enough to trust. The weak point was never the 231 pages; it was the
**30 eval questions** (±3.4 points of run-to-run spread, about the size of every lead we have claimed).
MultiHop-RAG gives **2,255 answerable queries with ground truth, evidence spanning 2–3 DIFFERENT
articles**, plus **301 `null_query` rows with zero evidence** — a direct test of P6 (no evidence ⇒
honest NOT_FOUND) that we have never run at any scale.

Because evidence spans documents, "did a gold article make top-k" is the wrong question:

    Hit@k       ≥1 gold article in the top k       — the loosest thing anyone reports
    Coverage@k  the FRACTION of gold assembled
    AllGold@k   EVERY gold article in the top k    — what a correct multi-hop answer REQUIRES

**The cascade opens a basket of 3 (`cascade_max_pages`), so AllGold@3 is not a diagnostic — it is the
ceiling on the answer.** Evidence the sieve does not deliver cannot be recovered by any prompt, any
triage, any re-read.

Preliminary (on a catalog that was still missing 21% of pages — D-040 — so these are pessimistic):

    AllGold@3   questions 17.6%   text 19.6%   sections 19.9%   both(RRF) 19.4%
    by type     comparison 29.2%   temporal 24.0%   inference 6.5%

Even at the loosest reading, **four out of five multi-hop questions do not have their evidence in the
basket**, and inference queries (which need three articles) fail 93% of the time. This is the first
MEASUREMENT of something I had only asserted to the user: *a synthesis question needs a different
machine.* `agent/synthesizer.py` is no longer a roadmap item; it is the gap between what the cascade
retrieves and what an answer requires.

Also settled, and not the way I expected: **text-index ≥ question-index on every metric here**, but
the margin is 2–3 points, not the 24 points `probe-index`'s LOI regime claimed. That regime was
rigged — its queries were generated FROM the pages being searched, so embedding the page body and
matching the question back is near-tautological. Held-out (n=30) said the opposite. **Neither was
trustworthy; this is.** And economically it is decisive anyway: question-indexing this corpus cost
~3.1M generated tokens; text-indexing costs **zero**.

## D-038 · 2026-07-13 · The AI-News corpus is in. The average went UP and that means nothing.
Imported `ai_knowledge` (116 pages, 9 books) as its own domain `AI News` — deliberately NOT under the
existing `AI` domain, whose shelves (LLM, RAG, CV) are a TEXTBOOK on the same subjects. Library is now
231 pages / 3 domains / 9 shelves. `--shelves auto` grouped the 9 source folders into 3 shelves.

The whole-library LOI page R@1 jumped **39.3% → 56.1%**, and that number must not be quoted. Broken
down (free, `evals/` per-domain probe):

    domain      rows   LOI R@1   LOI R@10   top-1 stolen by ANOTHER domain
    AI           240     50.0%      91.7%             11.7%
    AI News    1,266     68.6%      94.5%              1.3%
    Retail       680     34.9%      89.0%              0.4%

**Retail did not improve — it never moved.** The average rose because we added an EASY population: a
news item is about one named entity (a model, an acquisition), and embeddings separate named entities
well. An average over a mixed population is not a measurement of the sieve. This is the same class of
error as D-035 and the near-dup threshold below: the metric flattered us and we nearly reported it.

Two findings that ARE real:
1. **The predicted collision happened, and we now know its price.** `AI` (textbook) loses **11.7%** of
   its top-1s to another domain — 9× Retail's rate. That is `AI ▸ LLM` being outbid by
   `AI News ▸ Models & Research ▸ LLM Models`. Filing news beside a textbook on the same subject costs
   the textbook about a ninth of its precision. Worth it or not, it is no longer a guess.
2. **The near-duplicate flood did NOT arrive.** R@10 held at 89–94% in every domain. The reason is
   structural and it is a warning, not a reprieve: this corpus is *many documents, one entity each* —
   not *many documents, one entity*. The flood needs five articles about Claude Sonnet 5. It is coming;
   it is simply not here yet, and nothing we did earned that.

Also: `survey_folder` silently ignores `.md` files at the ROOT of an imported folder (only child
directories become books). Here it dropped `README.md` and `_TEMPLATE.md` — the right outcome by luck,
not by design. A loose folder of pages would vanish without a word.

## D-037 · 2026-07-13 · Leaf granularity is MEASURED per corpus, not chosen per file format
The user's objection, and it was correct: "if every new document type needs a code change, that is not
a product." The trigger was real — the AI-news corpus writes its summary under `summary:`, retail under
`description:`, a raw PDF nowhere — and the tempting fix (an alias list) is a pile of exceptions with a
nice name. Three changes, all of them rules rather than cases:

**1. The ingest CONTRACT (`ingest/questions.py`).** Every leaf ends with the same furniture — title,
one_line, keywords, questions — whatever it came from. A source that supplies some saves us a job; a
source that supplies none costs nothing, because the missing fields are generated *in the call that was
already generating the questions* (lite tier, 0 extra tokens). Frontmatter is a SHORTCUT, never a
dependency. Cost of supporting a new source format: **zero lines**.

**2. The recursive splitter (`ingest/split.py`).** The old rule picked ONE heading level for a whole
document and never looked again. MEASURED on the live library, that produced `3 Methodology` at 9,992
chars **with 12 unused sub-headings inside it**, and `References` at 13,136 chars — our largest page,
indexed, embedded, retrievable as "evidence", and not knowledge at all. Neither is a PDF problem or a
chunker-selection problem; both are a missing base case. The rule now:

    cut at the shallowest repeated heading level
      → a piece still over budget: cut IT at its own shallowest repeated level (recurse)
        → structure exhausted and still over budget: only NOW cut by size
    → a piece too small to stand alone: merge it forward

with two guards earned from real files, not imagined:
  - **Back matter** (References/Bibliography/Acknowledgements) is kept on the shelf but `indexable:
    false` — never in the sieve. And it is never CUT: the size-splitter renames pieces `… (3/6)`, which
    the apparatus filter no longer recognises, and the bibliography walks back into the catalog.
  - **Furniture** is not structure. A document's own title is not one of its chapters (a bilingual paper
    reprints its title, so `#` "repeats", and all 37 pages got a 70-char prefix). A heading that
    DOMINATES its level is a running header from a PDF converter, not a chapter — the tell is share, so:
    ≥4 occurrences AND ≥40% of its level. That keeps a textbook's per-chapter "Exercises" and kills the
    running header.
  A file in an imported folder is treated as ALREADY a page (`bound_page`) and is only cut if oversized;
  a document is cut into pages by its structure (`split_into_pages`). Different inputs, not exceptions.

**3. `libkb probe-granularity` — the loop from Ekimetrics' `adaptive-chunking`, and NOT its metric.**
Their five intrinsic scores (size compliance, intra-chunk cohesion, block integrity…) measure whether a
chunk LOOKS well-formed. Ours measures whether the librarian FINDS it. Fairness is the trap: a coarser
cut has fewer leaves and scores higher for free, so the ground truth is fixed OUTSIDE the cut — the
SOURCE FILE, a unit no strategy may redefine. Same queries, same truth, different indexes. Two axes are
reported because leaf size pulls them apart: recall (the sieve) and read-tokens (the answerer).

RESULT on AI-news (118 files, 674 lite calls, leaves cached across strategies):

    strategy      leaves   med   p95     R@1     R@3    R@10     read
    as-authored      118   640   938  100.0%  100.0%  100.0%    1,977
    tight (500t)     565   116   272   93.7%   97.0%   99.1%      444
    medium (1000t)   133   614   871   99.8%  100.0%  100.0%    1,807
    default (2000t)  118   640   938  100.0%  100.0%  100.0%    1,977

**`default` is byte-identical to `as-authored`: the recursive rule looked at 118 authored files and cut
nothing.** That is what a generic rule must do — act on the broken PDF, stay silent where the author was
already right. `tight` is a genuine trade (4.5× cheaper reading, −6.3 R@1) and we are NOT taking it: this
is a LOO regime, the 100%s are inflated, and a held-out check must come first.

**A fourth metric bug, caught before it was reported.** The probe's first `near-dup` column ("share of
leaves whose nearest neighbour in another document is above cosine 0.90") returned 65% and looked like
the user's feared flood. Checked against the LIVE library — which routes at 93.3% and has no duplication
problem — **95.7% of its pages clear that same bar** (nearest-other-page cosine: min 0.878, median
0.942). D-028 said this in 2026-07-12: absolute cosine is not a signal for this embedder; the MARGIN is.
Replaced with `margin = score@1 − score@10`, which needs no threshold because it is a difference between
two numbers from the same run. A flood is not "things are similar" — things are always similar. A flood
is the sieve unable to separate the winner from the restatements behind it.

## D-036 · 2026-07-13 · A/B CONFIRMED: the cascade is the default. Same accuracy, better routing, 14× cheaper
The fair A/B the user demanded: same 30 held-out questions, the same corrected judge (D-035), both
arms re-run, every answer saved.

| | walk | **cascade** |
|---|---|---|
| **answer_acc** (the gate) | 93.3% | **93.3%** — identical |
| page (exact target reached) | 73.3% | **90.0%** |
| book | 83.3% | **93.3%** |
| shelf | 93.3% | **100.0%** |
| found_rate | 100% | **100%** |
| avg hops / backtracks | 4.8 / 1.2 | **1.9 / 0.1** |
| **input tokens / query** | **66,558** | **4,711** |
| LLM calls | 9–13 | **2–3** |
| Gate | PASS | **PASS** |

**Identical accuracy. Strictly better routing at every level. 14× cheaper.** `retrieval_mode`
defaults to `cascade`; `walk` stays as the control arm.

**The last bug, and it was the whole deficit.** The cascade's first fair run scored 86.7% purely
because it **GAVE UP** three times (found_rate 90% vs the walk's 100%) — and **two of those three
were standing on the exact target page**. The sieve had found it, the triage had basketed it, and
`compose_answer` said "insufficient" because it was handed *one* page where the walk would have
handed it three. Fixed with a rule that should never have needed stating: **a librarian may not
declare the library empty while the closest pages sit unread on his desk.** Before any NOT_FOUND, the
top candidates are opened IN FULL and read once more. Only then is the not-found honest (P6). That
one change: **86.7% → 93.3%**, found_rate → 100%, at +400 tokens on the mean.

**Read the run-to-run spread before quoting any of this.** The walk moved **96.7% → 93.3%** and
**49,120 → 66,558 tokens** between two runs of the *same* 30 questions. Its spread (±3.4 points) is
about the size of the lead it was supposed to be defending. A 9–13-call machine has 9–13 chances to
wander and pays quadratically for each. The cascade's spread is ~1 point and ~400 tokens. **The
cascade is not only cheaper and better-routed — it is far more predictable**, and at n=30 that is
arguably the more trustworthy claim than the accuracy tie.

**What we are NOT claiming.** n=30. The tie is a tie, not a win, on accuracy. The corpus is 115
pages and 2 domains. The sieve's ceiling (LOI R@1 = **39.3%**) is now the binding constraint on
everything downstream — a **cross-encoder reranker** between propose and triage is the highest-value
experiment left, and it is cheap. Nothing here says the *tree* was a mistake: it remains how the
library is curated, cited and browsed. What was a mistake is making the **LLM walk it**.

## D-035 · 2026-07-13 · The cascade's first eval was decided by THREE bugs, and two were in the METRIC
The cascade's first run scored **answer_acc 83.3%** against the walk's 96.7%, at **2,010 tokens vs
49,120**. The prediction in RETRIEVAL_REDESIGN §6 ("answer_acc ≥ 96.7%") was **falsified**. Before
accepting that, I asked the one diagnostic question that mattered: **did the sieve fail, or the
oracle?**

**In all FOUR losses, the sieve had ranked the target page #1.** The embedder did its job perfectly
every time. So the architecture was not what lost — three concrete bugs were.

**Bug 1 (mine, in the cascade): the librarian threw away the right page for being opened at the
wrong chapter.** He picks sections from a list of *titles*, and a title easily hides the paragraph
that answers. When the answerer then said "insufficient", my code went looking for *other pages* —
discarding the one the sieve had ranked #1. Fixed: **before widening, re-open what we already hold,
in full.** One call, no search.

**Bug 2 (mine, in the triage prompt): I taught the librarian to give up.** The prompt dwelt on how
honourable a NOT_FOUND is, and the card he judged on was thin (path + a 120-char spine + section
titles). He returned an **empty basket on a page the sieve had ranked #1 with cosine 0.845**. Fixed:
the bar is *"could this help?"*, not *"am I certain?"* — plus the card now carries **the catalog
question that MATCHED**, which says what the page is *for* in a reader's own words. That signal was
sitting in `Hit.text`, unused.

**Bug 3 — and this is the one that matters — THE JUDGE PENALISED A BETTER ANSWER.** Its rejections
read: *"provides information … not present in the reference"*, *"introduces external concepts …"*.
But the cascade deliberately hands the answerer several pages **from across the library** — that is
its whole advantage (its very first live smoke cited two *different shelves*). The judge saw only
the single target page as reference, found extra material, and marked it wrong. Verified on case 13:
the answer gave the reference's own point (inference cost, not training loss) **plus** a correct
second point from another page — and was graded **incorrect for being richer**.
Fixed: *"the reference is a floor, not a fence. Extra material is NOT an error — mark it wrong only
if it CONTRADICTS the reference."* Re-judging the four losses: **2 of 4 flip → 90.0%, not 83.3%.**

**The meta-lesson, and it is the expensive one.** This is the **third** time this session that the
*measurement*, not the system, was the thing that was broken (`page_acc` ignoring ancestors, D-029
§4; `page_acc` structurally biased against shelf routing, D-030; the judge penalising a richer
answer, here). Each time, finding out cost a **full re-run of the arm — walks included**.
So: **`libkb eval --save` now persists every answer, and `libkb rejudge` re-grades a saved run for
almost nothing.** The answers are the expensive artifact; grading them is not. This should have
existed from the first eval.

**Two remaining losses, and neither is architectural.** Both are pages of one **mis-parsed PDF book**
whose every title still carries markdown emphasis (`**2 Related Work**`) — a PDF→markdown converter
emitting bold headings, which then rode into the title, the TOC, the citation and the triage card.
Fixed at ingest (`clean_title`, shared by `ingest/split.py` and `library/sections.py`), though the
pages already on disk keep their titles until re-ingested. And **case 7 is a broken eval case**: the
paraphrase *"how is this new setup better than the old ones that only looked at words?"* lost its
referent — "this setup" is unanchored, and the cascade's generic-RAG answer is arguably the better
response to the question **as actually asked**.

## D-034 · 2026-07-13 · The LLM was the SIEVE. It should be the ORACLE. (docs/RETRIEVAL_REDESIGN.md)
Triggered by the user: *"the whole knowledge base is ~200k tokens and one answer burns 50k — a
quarter of the corpus. This librarian is not professional; he is wasteful."* That is correct, and no
patch fixes it. Four measurements and one theorem say the **agentic tree-walk is the wrong shape of
machine**.

**1. Four fifths of the bill is rent.** MEASURED across the 30 held-out walks: a walk sees **8,601
tokens of distinct information** and we pay **45,268** — **5.3×**. Every LLM turn resends the whole
conversation, so cost is **O(T²)** in turns. This is why the spine cap won (−62%: it shrank a thing
multiplied by T) and the page digest lost (+17%: it attacked a symptom, and the librarian
compensated). **You cannot patch your way out of a quadratic.**

**2. Greedy tree descent is PROVABLY not optimal — even with a perfect scorer.** Zhuo et al.,
*Learning Optimal Tree Models Under Beam Search* (ICML 2020): greedy/beam descent is **not
Bayes-optimal even when every node scorer is trained optimally**, because a wrong turn at depth 1 is
unrecoverable. That is D-029's finding as a general theorem. We patched one level of the disease by
deleting the book hop; the theorem says the disease is **the descent itself**.

**3. I claimed the hierarchy prunes for free. It does not — I was wrong.** To score a container by
`max` over its pages you must first score *every page inside it*. The pruning narrows what the LLM
sees; it saves no retrieval work at all. And the sound version (a centroid+radius **cone bound**, Ram
& Gray, KDD 2012) prunes logarithmically in N but **degrades exponentially in dimension** — at 768-d
it collapses to brute force. That is why ANN abandoned trees for HNSW. **The tree earns its keep for
citation, curation and human browsing. Not for search.**
(Trap avoided by luck: the *element-wise* max of a container's leaf vectors, dotted with the query,
is **not** an upper bound on the best leaf — verified, it fails **80.8%** of the time. Our code takes
the max of the dot products, which is exact. Anyone "optimising" this later will reach for the other.)

**4. PageIndex — the system we set out to beat — does not walk either.** Read from their source:
their OSS retrieval is **2 LLM calls** (dump the whole tree's titles+summaries into ONE prompt → get
a node list → fetch and answer). **No embeddings, no hop-by-hop agent.** The MCTS is marketing, not
code. There is **no sufficiency loop or rollback** in the code at all. And **98.7% is soft**: their
own LLM judge scores **136/150 = 90.7%**; the 98.7% appears only after humans re-labelled 12 of the
14 misses. **Our 96.7% answer_acc already beats their honest number.** We were never losing on
quality — only on architecture, and on an agentic walk they never had.

**The replacement: a cascade.**
```
① PROPOSE  0 LLM calls  embed the question, rank every page (the sieve)
② TRIAGE   1 LLM call   the librarian sees PATHS + SECTION HEADERS (59 tok/page, not 1,571)
                        and fills a BASKET. He never sees a page body here.
③ ANSWER   1 LLM call   the basket opens ONCE: the chosen SECTIONS → cited answer + sufficiency
④ EXPAND   only if insufficient — pop the next candidates (free, already ranked), answer again
```
**Live smoke, real Vietnamese question: 2 LLM calls, 2,462 input tokens** (walk: 49,120 / 9–13
calls) — **20× cheaper** — with a correct answer citing pages from **two different shelves**, which
the walk could only have reached by backtracking.

**The basket is the structural point, and it came from the user.** Text in the *navigator's
conversation* is re-billed every turn (T times); text in the *answerer's call* is billed **once**. So
the full page must never enter the conversation. Not read-then-shrink (that was the page digest, and
it cost +17%). **Don't read.** MEASURED: page 1,571 tok · its section headers **59** · its two
biggest sections **516** → a section is **13.5× cheaper**, and 78% of pages are already sectioned by
their own headings. It also defuses the mis-parsed **12,842-token** page sitting in the library.

**No diversification — and this is the fourth theoretically-sound idea killed by measurement.** I
proposed NMS/facet-coverage for the user's (correct) worry that near-duplicate documents would flood
the candidate list. Measured on the 30 held-out questions: **NMS costs 10 points of recall** (96.7% →
86.7%, and it never recovers even at K=50) because it suppresses the right page **for being similar
to a good one** — and that similarity was corroboration, not redundancy. Diversity pays only for
multi-facet queries. The real answer to the objection is (a) dedupe at INGEST, and (b) keep K small:
**the recall curve is flat from K=3 (96.7%)**, so a 5-candidate shortlist cannot be flooded.

**Design constants, measured not guessed:** `cascade_k=5` (recall flat from 3), `fetch_n=20`,
`max_pages=3`, `max_rounds=2`, `max_page_tokens=4000`. `retrieval_mode` defaults to **walk** until
the A/B on the same 30 held-out questions says otherwise. **Prediction to falsify: answer_acc ≥ 96.7%
at ≤ 15k tokens and ≤ 3 LLM calls.**

## D-033 · 2026-07-12 · PART II eval: accuracy HELD, cost ROSE 17% — the page digest is OFF by default
The consolidated verification the user asked for: same 30 held-out questions, same shelf routing,
`--mode walk`, with every PART II change on.

| | shelf baseline (D-031) | + PART II | |
|---|---|---|---|
| **answer_acc** (the gate) | 96.7% | **96.7%** | unchanged — **Gate PASS** |
| page_acc (diagnostic) | 80.0% | 76.7% | −1 case |
| avg hops | 4.3 | 4.5 | ↑ |
| avg backtracks | 0.9 | 1.0 | ↑ |
| **input tokens/query** | 49,120 | **57,667** | **+17% — a regression** |

**The page digest — whose ONLY purpose was to cut cost — made queries more expensive.** The
mechanism is not in doubt; it is visible turn by turn in the log. The compression does exactly what
it was designed to do: with it on, a walk's per-turn input **plateaus** (…8,009 → 8,525 → 8,531 →
8,426 → 8,919…) instead of climbing (…4,999 → 7,018 → 8,644 → 10,941 → **13,660**). But the
librarian, robbed of the full text, **compensates**: he read **6 pages instead of 5** (hitting
`max_pages_per_nav`) and took **13 turns instead of 11**. The saving is eaten by the behaviour it
induces. §6 named this risk in its own falsifier — "what it could cost is the navigator's own *have
I got enough?* judgement" — and that is exactly what it cost.

So `page_digest_after_turns` defaults to **-1 (off)**: the measured-safe state. The code, the tests
and the knob all stay.

**A real bug found by reading the eval log, now fixed:** `read_page` had no re-read guard. A page
read twice was appended to the evidence twice (so `compose_answer` saw one source as two) *and*
charged twice against the page budget. Harmless before; a live trap with the digest on, because
digesting a page is precisely what makes the librarian want it back. Now a re-read hands the full
text back **for free** — no budget slot, no duplicated evidence. That attacks the compensation
mechanism directly, and it is the one change that could plausibly make the digest pay. It has not
been measured, so the digest stays off until it is.

**On the other PART II changes:** answer_acc held at 96.7% with cross-references and `reframe` live,
so nothing in the bundle broke anything. But the bundle was evaluated as a bundle: **we cannot
attribute the +17% between the digest, the cross-refs (which add readable pages to a menu) and the
larger prompt** without isolating runs. The digest is the prime suspect on mechanism, not on
attribution — that is why it is disabled rather than deleted, and why this note says so plainly.

## D-032 · 2026-07-12 · PART II shipped — and TWO of its recommendations were refuted by measurement
Source: `docs/ROUTING_REDESIGN.md` PART II (§6–§10), written by the user after the A/B. Everything
below was reproduced first, then built. Two of its headline recommendations did not survive contact
with a measurement, and the ones that did are stronger for it.

**`routing_mode="auto"` — DROPPED, on the doc's own test.** §9 said: check how many of the 30 A/B
cases even landed on a well-separated shelf; if "one or two", `auto` is still a live question. The
answer is **9 of 30** (`AI ▸ LLM` 100% separable, `Merchandising` 92.7%) — and shelf mode lost
**0 of those 9**. On `Merchandising`, the shelf where the book hop should be worth most, flattening
*improved* things (answer 6→7, page 4→6). There is no cow to build a fence around.

**§8.1 cross-references — SHIPPED, and it reproduced exactly (56/115 = 49%, top delta +0.078).**
Getting there required finding the pooling the doc used, and it turned out to be §7.2 applied
consistently: **a page is ONE topic ⇒ mean of its question vectors; a book is a UNION of topics ⇒
max over its rows.** Max on both sides inflates the hit rate to 58% and the deltas with it. The
deliverable is a cross-reference, not a move (`libkb probe-misshelved` → `libkb build-crosslinks`):
the page stays where it is, and the *other* place a reader would look for it gets a `see_also`
pointing at it. Rendered on the shelf menu, resolvable by `read_page`, and the citation still reports
the page's true home. A cross-link the librarian cannot follow is decoration.
**A privacy bug caught in the dry run:** the first pass would have written a link from a *tracked* AI
book to a *private, gitignored* Retail page (D-020) — leaking a private page title into git. Fixed by
refusing cross-domain links, which is also the right call on the merits: on the live library both
cross-domain pulls were test-ingest artifacts, not real facets. Blind spot recorded: a single-page
book cannot be judged by leave-one-out at all, so its pages are invisible to the probe.

**§6 page digest — SHIPPED, but the doc's diagnosis of the cost was WRONG.** Once a page's turn is
`page_digest_after_turns` old, its full text in the navigator's conversation is replaced by a gist.
Safe by construction, and pinned by tests: `compose_answer` rebuilds evidence from `NavState.pages`,
which never enters that conversation, so the ANSWER cannot lose anything.
But §6 called page text "the largest untouched lever" after reading the 49k bill as "2.5k menu + 46k
pages". **That arithmetic forgot that a menu is resent every turn too.** MEASURED on a real walk of
the widest shelf: menu 2,707 × 5 turns = **13,535 (49% of the bill)**; page text ≈ 30%. And the
digest is worth **−8%** (−24% if the most recent page is not kept in full), while **§0a's spine cap
was worth −62%**. The big lever was already pulled; this is a real but modest one.

**§7 shortlist — SHIPPED, and it exposed a serious bug of my own making.** A shelf too wide to lay
out no longer re-imposes the book gate: the catalog shortlists ~8 pages, with an escape hatch. The
catalog earns that job on measurement (`libkb probe-recall`, which reproduced §7.1 *exactly*): on an
intent nobody anticipated, top-1 is 39.3% but the right page is in the **top-10 90.7%** of the time.
A bad oracle; a good sieve. §7.4's rule — *a shortlist the librarian cannot escape is `open_book` all
over again* — turned out to be violated by my own §2 code: in shelf mode `open_book` was an alias for
`open_shelf`, so on a too-wide shelf the escape hatch **looped straight back into the shortlist**.
The text promised an exit that did not exist. Now `open_book` really opens the book *iff* the shelf
is over budget. The test that caught it is the one written to enforce §7.4.

**§7.3 hybrid BM25 — MEASURED AND REFUTED. Off by default.** The doc's reasoning is textbook-correct
(embeddings miss rare terms; BM25 nails them) and the mechanism is real — `tests/test_hybrid.py`
shows lexical rescuing "GMROI" from an embedder blind to it. But fused into retrieval it **loses, on
both query distributions we have, at every fusion weight, monotonically**:
| | dense | + BM25 (w=1) |
|---|---|---|
| generated questions, LOI page R@10 | **90.7%** | 78.6% |
| held-out colloquial paraphrases, R@1 | **83.3%** | 43.3% |
A reader's paraphrase reuses almost none of the library's exact words, so BM25 latches onto the
common ones and drags noise up. The index and `hybrid_shortlist` are kept for the day real traffic
shows queries where rare terms actually appear. **This is the third doc claim in a row that was
right in theory and wrong in measurement** — the discipline is the point, not the doc's fallibility.
(Incidental bug found while measuring: the FTS5 index was silently empty. `count(*)` on an
external-content FTS table is delegated to the content table, so it reports every row as indexed
even when nothing is — the backfill guard passed and every MATCH returned []. Now recorded
explicitly in `catalog_meta`, not inferred.)

**§8.2 entry vocabulary — BUILT, deliberately UNMEASURED.** `gen_questions` now also emits a term
ring (synonyms, abbreviations, named entities, vi+en) in the *same* generation call, stored with
`kind='term'`. The `kind` column exists precisely so its effect can be measured separately instead
of being quietly mixed into the questions — after two refutations, a new retrieval signal does not
get shipped on theory. It takes effect at the next `reindex`.

**§8.3 `reframe` — SHIPPED.** Bates (1989): a real search is berrypicking, the query rewritten at
every stop with the vocabulary just learned. The walk used to freeze the reader's words at t=0.
Costs no hop (rewording is not travel), budgeted at 2 in code (D-008). The pair it logs — reader's
words → library's words — is exactly the entry-vocabulary training data §8.2 is guessing at, except
earned from behaviour.

**§8.4 trajectory logger — SHIPPED. This is the answer to the founding worry.** Every query is now
logged with its route, outcome and landing page (`libkb harvest` feeds the answered ones back into
the catalog at one embed each). The user's original doubt — *can ingest-time generated questions ever
be enough?* — has a measured answer: **no**, and they were never meant to be. They are the cold
start. Real query distributions are Zipf-shaped: the infinite tail is uncoverable, the head is small,
and the head can only be learned from traffic. Harvesting is deliberately conservative: only ANSWERED
walks that landed on exactly ONE page, because a question answered from three pages is not a label.

## D-031 · 2026-07-12 · A/B RESULT: shelf routing wins on every axis — route B is CONFIRMED, gate armed
The validation D-029 was shipped without and D-030 unblocked. Two arms, **same 30 held-out
paraphrased questions** (`evals/holdout.json`, generated by `make-holdout` on `model_lite`),
`--mode walk` (no catalog, no shortcut — pure description routing), strong model both sides.

| | A: `routing_mode=book` | B: `routing_mode=shelf` | Δ |
|---|---|---|---|
| **answer_acc** (the gate) | 90.0% | **96.7%** | **+6.7** |
| page_acc (diagnostic) | 66.7% | **80.0%** | +13.3 |
| book_acc | 83.3% | 83.3% | 0 |
| found_rate | 100% | 100% | — |
| **avg hops** | 5.2 | **4.3** | −0.9 |
| **avg backtracks** | 2.1 | **0.9** | **−57%** |
| mean input tokens | 53,941 | 49,120 | −9% |

**Paired, per case — this is the part that matters at n=30:** on `answer_acc`, shelf **rescues 2,
loses 0**; on `page_acc`, shelf **rescues 4, loses 0**. Thrashing walks (≥5 backtracks): **5 → 3**.
There is **not a single regression** in either metric. Route B dominates; it does not trade.

**The falsifiable prediction held.** §3.1 demanded `answer_acc` UP **and** `hops`/`backtracks` DOWN
— "if accuracy rises but hops do not fall, route B is paying for accuracy with tokens and should be
reconsidered". Accuracy rose, hops fell, backtracks more than halved, and tokens fell too. Shipped
as the default; `routing_mode=book` stays available.

**Honesty about the strength of this evidence.** The accuracy delta is **2 flipped cases**. McNemar
exact gives p≈0.5 (answer) and p≈0.125 (page): **at n=30 the accuracy delta alone is NOT
statistically significant.** What carries the conclusion is the *convergence* of three independent
measurements on the same mechanism: (a) the free centroid proxy over 904 questions (+8.2%, 91
rescues / 17 losses), (b) the backtrack collapse — the direct fingerprint of "wrong book ⇒ the right
page leaves the search space ⇒ the agent can only thrash", and (c) 6 rescues / **0** losses here.
Any one alone would be thin. Together they agree on sign, magnitude and cause.

**§2.4's cost model was wrong in MAGNITUDE (right in sign).** It predicted −63%; the measurement says
**−9%**. Because it modelled only the *menu*. After the D-030 cap, the union TOC is ~2.5k tokens of a
**~50k** bill. **The real cost driver is the PAGES the librarian reads** — 2.1–2.3 pages per walk,
each one full markdown, each one resent on every subsequent turn. That is now the largest remaining
lever in the system, and neither the redesign doc nor I had noticed it. (It also means the cost
argument never favoured either arm much; the case for route B rests on accuracy and thrash, not
price.)

**The real baseline is much lower than 86%.** On the held-out set, book-mode `page_acc` is **66.7%**
vs the 86% we had been quoting from the leaked set. Stripping the generator's jargon out of the
questions costs ~20 points of routing accuracy. **66.7% is the honest number**; 86% was measuring
memory. Note `answer_acc` (90%) barely moved — the system was *serving readers* better than
`page_acc` ever admitted.

**Gate armed** (`evals/gates.py`): `min_answer_acc = 0.90` = the shelf baseline − 1.6 se (se ≈ 0.033
at n=30, p≈0.97). A regression to book-gated routing lands exactly on the line. `min_page_acc` stays
**None on purpose** — gating it would punish the system for answering correctly from a sibling page.

## D-030 · 2026-07-12 · A menu line is a SPINE LABEL; the eval's primary metric is the ANSWER
Four changes that all had to land **before** the D-029 A/B could mean anything. Source:
`docs/ROUTING_REDESIGN.md` §0a / §2.5 / §3.0, written by the user after reviewing the D-029 code.

**1. `one_line` was 8x its budget, and it silently taxed every query.** MEASURED over all 125 TOC
entries in the live library: median **1013** chars, max **1436**. `library/models.py` has had a
`one_line_of()` helper all along; `ingest/survey.py` was not using it — it copied each source file's
whole frontmatter `description:` (an abstract) into `TOCEntry.one_line` (a spine label). Isolated to
the retail import; the hand-written seed is fine (max 160). Consequences, all live before any
redesign: (a) **cost** — a menu is resent on *every* later turn, so its price is paid once per
remaining hop; (b) **accuracy** — when every option is a 1000-char paragraph, everything sounds
relevant, which is the documented cause of LLM mis-selection among similar categories (Lu et al.,
ACL 2024); (c) it made the union-TOC design look expensive when it is not.
MEASURED effect of the cap on the real union-TOC menus: **28,032 → 6,319 tokens (−77%)**; worst
shelf (KPIs) **14,221 → 2,584 (−82%)**, closely matching the doc's independent estimate (13,999 →
2,364). Capped at **render** time (`agent/tools.py`, all three renderers — the stored value is never
trusted, so existing libraries are fixed with no migration) **and** at ingest (`survey.py`,
`split.py`), and in the description prompts (`views.py`) and the API's TOC (`routes.py`).
Knob: `max_one_line_chars=120`.

**2. The scale guard counted the wrong unit.** `max_shelf_toc_entries=60` counts ROWS. The KPIs
shelf has 50 pages → passed the guard → emitted a **14,221-token** menu. Rows and tokens are two
*independent* ceilings and both are real: rows bound the **option count** (an LLM cannot rank 200
titles no matter how short each is), tokens bound the **cost** (quadratic in turns). A shelf over
either now falls back to book-by-book. Added `max_shelf_menu_tokens=6000`. NOTE: with the cap in
place no live shelf trips either guard (worst = 2,584 tokens) — which is exactly the point. Had we
shipped the token guard *without* the cap, the KPIs shelf would have fallen back to book mode and
route B would never have been tested on the very shelf it exists to fix.

**3. `page_acc` is a DIAGNOSTIC, not the metric — and it is biased against route B.** It asks "did
the walk reach the exact page that generated the question". Route A commits to a book and then picks
among ~8 pages. Route B sees ~42 at once, so it has far more opportunity to land on a **sibling page
that answers the question perfectly** — scored a MISS. The property that makes route B good was
being counted as a defect. (Observed live in the D-029 smoke: a question about inventory *days* was
answered correctly and completely from the *Inventory Turnover* page → scored `miss`.) So the
primary metric is now `answer_acc`: an LLM judge (`evals/judge.py`, prompt `judge_answer.md`) over
the **final answer**, with the target page as the reference, explicitly told to judge the answer and
not its provenance. Runs on `model_lite` (D-027) — one cheap call per case. The eval now also runs
every mode through `answer_query`, so the thing being graded is the answer a reader would actually
have received. `mean_input_tokens` is reported too (judge calls excluded — they are scaffolding, not
product), which turns §2.4's cost model into a measurement.

**4. The gates are DISARMED until the A/B produces a real baseline.** Every threshold we had was
calibrated in `routing_mode=book`, on the leaked case set, against `page_acc`. All three premises are
now false. Arming a stale gate is worse than having none: it fails honest work and waves through real
regressions. `EvalGates` fields are `None` (with `.armed`); the CLI prints "not armed" and explains.
Re-arm `min_answer_acc` from the A/B result minus ~1.6 se (≈0.09 at n=30).

Also built (not yet run — it costs tokens): `libkb make-holdout`, which restates each eval question
the way a reader who has NOT read the page would ask it (vague, plainer, sometimes the wrong term)
and **saves it to disk**, because both arms of an A/B must be scored on byte-identical questions.
The default eval set is leaked — its questions *are* the catalog rows the system indexes.

## D-029 · 2026-07-12 · The book is a unit of STORAGE, not of ROUTING (docs/ROUTING_REDESIGN.md)
Source: a review/analysis pass by the user (`docs/ROUTING_REDESIGN.md`). I re-derived every number
independently with a fresh implementation (`evals/separability.py`) and **reproduced them exactly**.

**Evidence.** Decomposing the measured n=50 walk baseline into conditional per-hop accuracy:
domain 100% → shelf 96% → **book 89.6%** → page **100%**. Page-selection *inside* a book is already
perfect; the ENTIRE 14-point loss is the shelf→book hop. Then, from the catalog vectors (free, no LLM):
- **Sibling books are not separable by their own content**: leave-one-out book centroids pick the true
  book only **82.3%** of the time (904 decisions). The LLM+descriptions already scores 89.6% — it is
  BEATING the intrinsic ceiling of the tree. So **rewriting descriptions cannot fix this hop.**
  `Root Cause Analysis` ⇄ `KPI Interpretation` confuse each other in BOTH directions (19x / 14x) —
  the signature of one book that got split in two. Separability decays with sibling count
  (2 books → 100%, 5 books → 74.4%).
- **Deleting the book hop is worth +8.2 points**: route A (shelf→book→page) 68.3% vs route B
  (shelf→page over the union TOC) **76.4%**; B rescues 91 cases A lost and loses only 17. Page-on-shelf
  decisions are also MORE confident (median margin 0.0236 vs 0.0189).

**Mechanism (this is the real argument).** `open_book` is an **irreversible commitment**: choose the
wrong book and the right page leaves the search space entirely — it is in no TOC the agent can see.
The only recovery is to read useless pages and `go_back`, which is exactly the "misroutes correlate
with 12-hop thrashing walks" pattern already logged. Route B never makes that commitment. And it is the
librarianship answer: a reference librarian does not pick a book then open it — they scan the spines and
TOCs of the whole shelf at once. **Against PageIndex**: their 98.7% is *within one document* — they have
NO book-selection hop. We were not losing because we have more levels; we lost because we invented a
lossy commitment they don't have. The way to compete is **fewer committed decisions**, not a higher p
at every level.

**Principle (extends P1–P10).** *The book is a unit of storage, authorship and citation. It is not a
unit of routing. Routing commits only at levels that are measurably separable — measure with
`libkb probe-separability` BEFORE making any level a decision point.*

**Change.** `agent/tools.py` only — disk layout, `_meta.json`, `toc.json`, ingest and citations are
untouched. New `open_shelf()` renders the union of every book's TOC on the current shelf, grouped by
book (book = context, not choice); `read_page` resolves shelf-wide; `open_book` survives as a forgiving
alias; `Settings.routing_mode: "book"|"shelf"` (default **shelf**) keeps both arms runnable;
`max_shelf_toc_entries=60` falls back to book-by-book on a too-wide shelf (the scale guard — route B
trades a 4-way book choice for a 42-way page choice, which wins today but will not at 200 pages/shelf).
Prompt `route_shelf.md` states explicitly that the agent does not choose a book.

**Prerequisite bugs fixed first (they corrupted the eval that judges this):** (1) `score_case` did not
credit the ancestors of touched nodes, so a shortcut landing on the wrong page of the RIGHT book scored
`miss` — every level below `page` was understated; (2) hop-budget exhaustion returned NOT_FOUND and
**discarded pages already read** — a product bug: the librarian read the answer and then threw it away;
(3) `store._scan()` cleared the index in place while worker threads read it; (4) `_resolve_child` matched
substrings both ways, first-in-dict wins → now exact/prefix/difflib best-score with a floor. Gates raised
from 0.55/0.80 (below the 0.86 baseline, protecting nothing) to 0.78/0.80.

**NOT yet validated end-to-end.** The +8.2% is a content-centroid proxy, not an LLM walk: trust the SIGN
and the MECHANISM, not the absolute numbers. Live smoke passed (a previously-misrouted vi question now
answers in 3 hops / 0 backtracks). The A/B (`LIBKB_ROUTING_MODE=book` vs `=shelf`, same seed) is the
proof and is still owed. Caveat found during the smoke: the eval's ground truth is the page a question
was GENERATED from, but another page can answer it correctly — the metric understates real quality.

## D-028 · 2026-07-12 · MEASURED: the absolute-cosine shortcut gate was HARMFUL — gate on MARGIN instead
The user asked the right question: does generating questions at ingest actually help, when the question
space is unbounded and a catalog can only match near-paraphrases? Answered with a **free** held-out
probe (`libkb probe-catalog` / `evals/catalog_probe.py` — zero LLM calls, pure cosine over the vectors
already stored), on the live 920-question / 115-page catalog:
- **LOO** (drop the query's own row; page keeps its other questions ⇒ "user paraphrases"): top-1 lands
  on the right page **70.9%**.
- **LOI** (also drop the translation twin ⇒ "a question we never thought of"): **39.3%**.
- And the killer: top-1 cosine **crowds at median 0.904 / 0.882**, so the shipped absolute gate (0.82)
  fired on **99.9% / 92.6%** of queries at only **70.9% / 40.1%** precision → estimated end-to-end
  **71% / 43%**, i.e. **WORSE than the 86% of having no catalog at all. The shortcut as shipped was
  actively harmful.** Absolute cosine is simply not a confidence signal for this embedding.
**Fix:** gate on the **MARGIN** between the best page and the runner-up PAGE (`catalog_margin`, default
**0.05**). Measured: LOO fires 34% at **95.5%** precision (est. 89.3% > 86%); LOI fires only **12.6%** at
71.6% (est. 84.2% ≈ neutral). The margin gate makes the catalog **know when it doesn't know** — it goes
quiet on unfamiliar questions and lets the librarian walk. `lookup(min_margin=…)` returns only the
winning page (the case the precision was measured on). `ask_librarian` deliberately does NOT apply the
margin: hints are allowed to be uncertain because the walk verifies them anyway.
Also measured: a Vietnamese question finds its page from ENGLISH-only rows **98.3%** of the time.
⚠️ **CORRECTION (same day, review pass):** I over-read this. Those vi/en rows are translations of the
SAME generated question — near-identical in meaning — so 98.3% shows only that the embedder matches
translations. It says NOTHING about a novel, colloquial, wrong-jargon Vietnamese query. My inference
that "storing both languages is redundant, we can halve ingest cost" was **NOT justified**. Keep both
languages until a proper paraphrase/held-out probe says otherwise.
**Standing conclusion on the flywheel:** ingest-time questions are a COLD START (supply-side guesses) and
cannot cover an unbounded question space — the user's instinct was correct. Their durable value is
(a) the **routing eval set** (which is how we got the 86% baseline AND found the book-description bug)
and (b) a vocabulary bridge. The missing half is **DEMAND-side**: log real queries + their resolved
pages and index THOSE (P3 trajectory logger). That is what makes the catalog cover the head of the real
question distribution instead of our guesses. Until then, keep the margin gate conservative.

## D-027 · 2026-07-12 · MEASURED: flash-lite cannot navigate — two tiers by difficulty (supersedes D-026)
Re-ran the identical walk eval (n=50, seed 7, same cases, *with* the improved descriptions helping it)
on `gemini-3.1-flash-lite`: page **54%** · book 62% · shelf 78% — against **86% / 86% / 96%** on
`gemini-3.5-flash`. A 32-point collapse in exact-page routing. Diagnosis from the trace stats: the lite
model **stops deliberating** — avg backtracks fell 2.1 → 0.4 and hops 5.3 → 3.4, while found-rate ROSE
90% → 96%. It grabs a plausible page fast and declares FOUND instead of reconsidering: confidently
wrong. Navigation is the reasoning-hard task and needs the strong tier.
So D-026's global switch is REVERTED and replaced by the two-tier split D-003 always anticipated
("per-node assignment by MEASURED difficulty"): `model` = gemini-3.5-flash (navigator, answerer,
classify); `model_lite` = gemini-3.1-flash-lite, wired into **question generation**
(`ingest/questions.py`) — genuinely easy (summarise one page into questions), and the single biggest
bulk cost (1 call per page ⇒ 115 calls per full reindex). Embeddings stay on gemini-embedding-001.
Standing cost guidance: the model tier is a MINOR lever. The major one is the P2c shortcut — a known
question costs ~2 calls (a cheap embed + one compose) versus a 5–10 generate walk. `--mode walk` evals
are the worst-case spend by construction (they disable the shortcut), so don't read eval cost as
production cost. Reindex is a one-off; it is already done.

## D-026 · 2026-07-12 · Generation model switched to gemini-3.1-flash-lite for cost (SUPERSEDED by D-027)
User flagged gemini-3.5-flash cost (~$10–15/day during P2c/P3 live runs). Switched `Settings.model`
and `model_lite` defaults to `gemini-3.1-flash-lite` — config is the single model-ID source (D-003),
and `.env` is never touched (hard rule); override per-env with LIBKB_MODEL if needed. Embeddings stay
on gemini-embedding-001 (cheap, and the catalog is already built so re-embed cost is one-off).
Validated the ID live (smoke: `get_settings().model` resolves to it, one generate returns "OK"). Re-ran
the walk eval on the cheap model to quantify any accuracy change — see STATE/JOURNAL for the number.
Cost note: the biggest ongoing saver is NOT the model tier but the P2c shortcut — a known question
answers in ~2 calls (embed + compose) vs a 5–10 call walk, and embeddings are ~10× cheaper than
generation. So warming the catalog (more logged questions → more shortcut hits) cuts per-query cost far
more than the model swap does. Walk-mode eval is the worst case cost-wise (it forbids the shortcut).

## D-025 · 2026-07-12 · Book descriptions are materialized views too (extends D-004), driven by an eval miss
P3's first eval exposed the failure mode: at n=50 walk (leak-free) routing was page/book **86%**,
domain **100%** — every miss stayed in the right domain but 5/7 landed in the wrong BOOK. Root cause:
`views.rebuild_description` only regenerated root/domain/shelf, so imported books kept their generic
placeholder description (`_book_description` = "N topics: <first 3 page titles>…"). Two sibling books
both about inventory read almost identically → the librarian thrashed (some misses hit 12 hops) and
picked wrong. Fix (principled, not a patch): a book IS a non-leaf whose children are its pages, so it
too is a view — `rebuild_description` (and `rebuild_all`/`propagate_up`) now include `"book"`, sourced
from the book's TOC one-liners with sibling-book context. Added `rebuild-views --domain <D>` to rebuild
one subtree so regeneration doesn't clobber the hand-crafted AI seed descriptions. Regenerated Retail:
each book now says what it covers AND points to the sibling for what it doesn't ("for EOQ/safety stock,
see *Inventory Management*"). Caveat: the menu shows only `one_line_of(description)` (first ~160 chars),
so the trailing "see sibling" pointer can be truncated — front-loading the discriminative clause, or
widening the menu line, is a follow-up if the re-eval shows the effect is blunted. The walk re-eval
(same seed 7, same 50 cases) quantifies the lift. Separately: shortcut-mode eval read 100%/0-hops —
correct but LEAKY (cases come from the catalog; D-024), confirming the flywheel nails seen questions.

## D-024 · 2026-07-12 · Routing eval reuses the flywheel questions; scored by deepest level; three modes
The eval set is NOT authored separately — `evals/dataset.build_cases` samples the catalog (each
generated question has a known target page), one question per page, fixed seed for reproducibility.
`runner.score_case` grades by the DEEPEST target-ancestor the walk reached (page ⊃ book ⊃ shelf ⊃
domain ⊃ miss), so accuracy buckets are monotone (`book_acc` = "landed in the right book at least").
Three modes isolate what you measure: `walk` runs with catalog=None (pure description routing — the
honest per-hop signal, and the apples-to-apples number to compare against PageIndex's 98.7%),
`assisted` adds `ask_librarian`, `shortcut` is the full system incl. the fast path. `gates.py` minima
are placeholders to calibrate from the first baseline; later they gate P4 refactors (P8). CLI: `libkb
eval --limit N --mode M --domain D --seed S`. **Caveat (leakage):** because cases come FROM the catalog,
`shortcut`/`assisted` see the exact stored question (optimistic — measures "can it re-find its own
row"); `walk` mode is leak-free and is the metric to trust for routing quality. A future held-out /
paraphrased eval set removes the caveat for the other modes.

## D-023 · 2026-07-12 · Catalog shortcut is answerer-gated; ask_librarian only hints; indexing is best-effort
`answer_query` tries a fast path before walking: a question matching a stored question at cosine ≥
`catalog_shortcut_threshold` (0.82, a placeholder to be TUNED by the P3 eval) answers straight from
those pages — BUT only if `compose_answer` judges the evidence sufficient; otherwise it falls back to
a full walk. So a spurious high-similarity match cannot produce a wrong answer (the answerer is the
safety net). The navigator's `ask_librarian` tool (offered only when a catalog is loaded) returns
suggested PATHS, budgeted by `max_ask_librarian=2` in the tool layer (D-008) — it does NOT teleport;
the librarian still walks there and verifies, so citations + honest NOT_FOUND still hold. Indexing is
best-effort: import/ingest swallow per-page index errors (a flaky embed must not lose an import), only
non-gated (filed) pages are indexed at ingest, and `approve_placement` indexes on approval. The
orchestrator auto-opens the on-disk catalog only if the db file exists (never creates one as a query
side effect) and closes what it opened. Verified live on gemini-3.5-flash: an in-library paraphrase
answered in 0 hops via the shortcut; an off-library query declined the shortcut, called ask_librarian
twice, and concluded NOT_FOUND after 10 hops / 9 backtracks.
