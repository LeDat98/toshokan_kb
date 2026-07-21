# SCORECARD — what this system actually does, measured

> **2026-07-19 — the multi-agent architecture (D-061) shipped but is NOT re-measured here.** Narration,
> agent roles, the MCP/A2A seam, the calculator, and front-door routing are plumbing + default-off knobs
> (see `docs/AGENT_ARCHITECTURE.md`). The cascade's measured behaviour below is unchanged: the roles are
> behaviour-preserving wrappers and routing is default-off. **No new accuracy/cost numbers are claimed
> for them.** When the router is turned on and measured (its lite-call tax, its social-vs-cascade
> precision), the numbers land here with their `n`.

**Last updated: 2026-07-15 (measured numbers); 2026-07-19 (architecture note above).** Rewrite this file after every major change. Its only job is to let a
future version be compared honestly against this one, so **every number here carries its `n`, its
regime, and the command that produced it.** A number without those is not evidence, it is decoration.

Three rules for maintaining it:

1. **Never quote a number without its regime.** LOO ("a paraphrase of a question we anticipated") and
   LOI ("an intent we never anticipated") differ by 30 points on the same system. Quoting the first
   as "accuracy" is lying with true numbers.
2. **§5 (What we have NOT measured) is the most important section.** A scorecard that only lists
   wins is a marketing page. When a gap gets closed, move it up; when a new gap appears, add it.
3. **Record the metric bugs too (§6).** Six times in this project the broken thing turned out to be
   the measurement, not the system. Whoever reads this next needs to know which numbers were
   retracted and why, or they will re-derive them and be misled the same way.

---

## 1. The headline

The system is a **cascade**: an embedding sieve proposes ~20 candidate pages for free, an LLM triages
them on section headers only, and a basket of pages is opened ONCE to compose a cited answer. It
replaced an agentic tree-walk in D-036.

| | walk (old) | **cascade (shipped)** |
|---|---|---|
| **answer accuracy** | 93.3% | **93.3%** — identical |
| reached the exact target page | 73.3% | **90.0%** |
| reached the right shelf | 93.3% | **100%** |
| **input tokens / query** | **66,558** | **4,711** |
| LLM calls / query | 9–13 | **2–3** |

*n=30 held-out colloquial paraphrases · `gemini-3.5-flash` · 231-page library · D-036*
`LIBKB_ROUTING_MODE=shelf libkb eval --cases evals/holdout.json --mode cascade --save`

**Same accuracy, better routing at every level, 14× cheaper.** The tree is still how the library is
catalogued, cited and browsed by humans — it is simply not how the machine searches.

⚠️ **n=30.** The walk's run-to-run spread on the same 30 questions is ±3.4 points and ±17k tokens —
about the size of the lead it was defending. The cascade's spread is ~1 point. *"The cascade is far
more predictable"* is a better-supported claim than *"the accuracy is identical."*

### 1.1 The live library now runs on a TEXT index (D-045), and held out at 96.7%

The whole library was reindexed from the question flywheel to **text** — `LIBKB_INDEX_KIND=text`,
**250 pages, 250 rows, 0 generation tokens** (embeddings only). Held-out cascade, same 30 questions,
`gemini-3.5-flash`:

| | text-index (live now) |
|---|---|
| **answer accuracy** | **96.7%** (29/30) · Gate PASS |
| reached the exact target page | 73.3% |
| reached the right domain | 100% · found 100% |
| input tokens / query | **3,960** |

`LIBKB_RETRIEVAL_MODE=cascade libkb eval --cases evals/holdout.json --mode cascade --save`

- **This is NOT a clean text-vs-questions A/B.** The corpus changed underneath the comparison
  (AI-News added since the 93.3% questions run, the PDF book re-ingested with fresh IDs). What it IS:
  the honest held-out number for the library **as it actually ships today**. A clean A/B would mean
  reindexing back to questions on this same corpus — not done, because we have adopted text.
- **The single miss is the ANSWERER, not the sieve.** On *"why is it a bad idea to only look at the
  failing items?"* the sieve reached the **exact target page** (level=page) — then the answerer
  agreed with the leading question, which the reference page contradicts (it *advocates*
  exception-based reporting). Sycophancy to a loaded premise, not a retrieval failure. Notably this
  same question was a NOT_FOUND under the question index — **text-index improved the retrieval here**
  and exposed a separate answerer weakness underneath.
- **Two eval-infra fixes shipped alongside** (both were latent traps a re-ingest sprung): the scorer
  now counts a stale `target_page_id` a miss instead of crashing the whole paid run (`runner.py`,
  fail-soft like ingest); and `evals/holdout.json` had its 3 PDF-book targets remapped to the
  re-ingested pages (they were frozen at the old ULIDs). Regression test added.

---

## 2. The sieve — where the real ceiling is

The embedder is a **bad oracle and a good sieve**, and the whole architecture rests on that being
true. Measured two ways, on two corpora.

### 2.1 On our own library (231 pages · generated questions · LOI regime)

`libkb probe-recall` — **free, no LLM calls**

| level | R@1 | R@10 |
|---|---|---|
| page | **56.1%** | 92.5% |
| book | 73.1% | 99.9% |
| shelf | 83.6% | 100% |

Per domain (this decomposition matters — the aggregate lies):

| domain | rows | LOI R@1 | LOI R@10 |
|---|---|---|---|
| AI (textbook) | 240 | 50.0% | 91.7% |
| AI News | 1,266 | **68.6%** | 94.5% |
| Retail | 680 | **34.9%** | 89.0% |

**The 56.1% aggregate went UP from 39.3% when we added AI-News, and that means nothing** — news is an
easy population (one named entity per page). Retail did not move at all. *Never quote the aggregate.*

### 2.2 On FiQA (57,638 docs · 648 questions REAL PEOPLE wrote · HUMAN qrels) — the first fully external number

`libkb bench benchmarks/fiqa` · text-index · **0 generation tokens** · **VERIFIED bit-for-bit by
`pytrec_eval`, the official TREC scorer** (the first metric check this session that confirmed).

| metric | @1 | @10 | @100 |
|---|---|---|---|
| nDCG | 0.603 | **0.621** | 0.682 |
| Recall | 0.316 | **0.701** | 0.920 |

- **This is not a good number, it is an honest one.** R@10 = 0.70 means **3 of every 10 real
  questions have their answer outside the top-10** — a hard failure for a cascade that opens ~10.
  R@1 = 0.32: two of three times the single best doc is not ranked first.
- **The R@10→R@100 gap (0.70→0.92) is the recurring finding of the whole session:** the sieve FINDS
  the evidence; the window is too narrow. Same shape as MultiHop's AllGold@20 0.935 vs @3 0.296. The
  two fixes it points to — a wider window and a reranker — are backlog #2 and #5.
- Above BM25's published 0.236, but BM25 is a weak 2009 baseline; clearing it is not an achievement.
- Pure text-index reached this with the question flywheel NOT participating — more evidence (§2.3)
  that the flywheel is not carrying the sieve.

### 2.3 On MultiHop-RAG (2,079 pages · 2,255 EXTERNAL ground-truth queries)

`libkb bench-multihop` — **embeddings only, no generation**. This is the first retrieval number in the
project our own LLM did not author.

| index | Hit@3 | Coverage@10 | AllGold@3 | AllGold@20 | generation cost to build |
|---|---|---|---|---|---|
| questions (shipped) | 86.7% | 81.7% | 25.7% | 69.5% | **~3,100,000 tokens** |
| **text** | **90.3%** | **87.5%** | **29.6%** | **93.5%** | **0** |
| sections | 90.4% | 87.6% | 30.0% | 93.8% | 0 |
| both (RRF) | 89.4% | 85.8% | 28.9% | 80.6% | 3,100,000 |

- `Hit@k` = ≥1 gold article in the top k · `Coverage@k` = fraction of gold assembled ·
  `AllGold@k` = **every** gold article (evidence spans 2–3 articles).
- **Text-index beats the question flywheel on every metric AND costs zero generation.** Fusing them
  by RRF is *worse* than text alone — mixing a weak index into a strong one drags it down.
- **The sieve is not the bottleneck.** At k=20 it has assembled ALL the evidence for **93.5%** of
  questions. At k=3 — the cascade's basket — only 29.6% survives.

### 2.4 The scale curve — does accuracy survive 2k → 10k → 57k? (D-048, model-free, free)

The founding worry, finally measured. FiQA needle-in-a-haystack per query (rank a query's gold docs
mixed into N random distractors, grow N). **Reuses the cached vectors — $0.**

| corpus N | R@1 | R@10 | **R@50** | **R@100** |
|---|---|---|---|---|
| 2,000 | 0.488 | 0.952 | **0.988** | **0.997** |
| 5,000 | 0.450 | 0.911 | **0.976** | **0.987** |
| 10,000 | 0.409 | 0.862 | **0.961** | **0.976** |
| 20,000 | 0.372 | 0.799 | 0.939 | 0.959 |
| 57,638 | 0.316 | 0.701 | 0.863 | 0.920 |

- **The scale problem is entirely in the NARROW window.** R@1/R@10 collapse with corpus size; **R@50
  is nearly flat 2k→10k (−2.7 pts)** and R@100 flatter still. Read a wide enough window and retrieval
  IS scale-invariant in the target range. The bottleneck then moves from RETRIEVAL to SELECTION.
- **The reranker that should have converted the wide window to top-1 was REFUTED** (D-048): qwen3-rerank
  on FiQA top-50 HURT R@1 by 5–9 pts at every scale (120 queries, no bug) — a strong embedder leaves
  a reranker nothing to add. The de-facto reranker is therefore the LLM **triage**; the lever is
  widening its window (`fetch=50`, `basket=10`), not adding a cross-encoder.

---

## 3. The answer — accuracy, and the thing that matters more

`libkb eval-multihop` · n=200 stratified · `qwen-plus` · MultiHop-RAG

| | basket = 3 (shipped) | basket = 10 |
|---|---|---|
| **ANSWER** (176 answerable) | 73.9% | **77.8%** |
| ↳ comparison (needs 2 docs) | 60.6% | **69.7%** |
| ↳ temporal (needs 2 docs) | 65.2% | **69.6%** |
| ↳ inference (often 1 doc) | **93.8%** | 92.2% |
| **coward** (wrongly gave up) | 13.6% | **8.0%** |
| input tokens / query | **6,572** | 10,568 (+61%) |

A bigger basket earns exactly where multiple documents are genuinely required. It costs 61% more
tokens — which, on `qwen-plus`, is **$0.0026 → $0.0042 per query**.

### 3.1 P6 — the honest NOT_FOUND. The one rule this project calls non-negotiable.

> no evidence ⇒ an honest NOT_FOUND, never an improvisation

MultiHop-RAG carries **301 questions the corpus genuinely cannot answer**. Every eval this project
had ever run contained only *answerable* questions — which quietly rewards guessing. This is the
first one that punishes it.

**Result, at n=301, with the fail-closed fix (§7.5) in place:**

| basket | honest refusals | improvised (P6 violations) |
|---|---|---|
| **3 (shipped)** | **92.7%** (279/301) | 22 |
| 10 | 90.0% (271/301) | 30 |

**P6 holds.** The one rule the project calls non-negotiable, measured at scale for the first time.
The first run *looked* like a 79.4% catastrophe — but **56 of those 62 "improvisations" were the
fail-open BUG (§7.5), not hallucination**: `generate_json` turned a truncated response into a
one-character answer (`"J"`, `"F"`) carrying an invented `"sufficient": true`. Once a broken call
fails CLOSED, the true improvisation rate is ~7%, and the genuine coherent hallucinations are a
handful.

**The bigger basket costs honesty (30 vs 22 improvisations).** This is the load-bearing architecture
finding: `cascade_max_pages` controls *how much evidence* AND *how eager to answer* with one knob.
More evidence → more things look relevant → more willingness to speak, right (cowardice 13.6%→8.0%)
AND wrong (§8 item 2 — the fix is a SEPARATE confidence gate, not a bigger or smaller basket).

**Always report honesty and cowardice together.** A librarian who refuses everything scores 100%
honesty and is worthless.

### 3.2 Query DECOMPOSITION — REFUTED (2026-07-20, n=80, basket=10, qwen-plus, text index)

The intuition: a compound question ("compare A before vs after X, and which applies to Y") gives one
BLURRED query vector; split it into standalone sub-questions, retrieve each sharply in parallel, and
combine (the LlamaIndex/AWS-Step-Functions "decompose → retrieve → combine" pattern, home-grown as
the `decompose` route). Attacks the retrieval layer, unlike the refuted `triage_coverage` (D-051).
Paired A/B, forced via `LIBKB_FORCE_ROUTE=decompose`, same 80 cases (seed 11):

| slice | baseline (cascade) | decompose `per_q=3` | decompose `per_q=6` |
|---|---|---|---|
| **comparison** | **74.1%** (20/27) | 63.0% | 63.0% |
| **temporal** | **83.3%** (15/18) | 72.2% | 66.7% |
| coward | 1.4% | 8.5% | 4.2% |
| mean pages read (comp/temp) | 7.1 / 7.4 | 5.5 / 4.3 | 11.0 / 8.9 |
| wrong answers (comp/temp) | 7 / 2 | 7 / 2 | **9 / 4** |

**Refuted, and not by starvation.** `per_q=3` read FEWER pages than the cascade's basket (union of a
few 3-page retrievals, deduped) and lost mostly by ABSTAINING (temporal: all 3 losses were give-ups).
So we fed it more — `per_q=6` reads MORE than baseline (11.0 / 8.9 pages) — and it STILL lost, with the
losses shifting from abstention to **wrong answers** (comparison wrong 7→9, temporal 2→4). Extra
evidence turned give-ups into errors, not corrections. **The mechanism itself is worse:** splitting a
multi-hop question and recombining per-sub-question evidence throws away the joint signal that a single
wide query + a holistic basket preserves (temporal, which needs joint ordering, is hit hardest).

**Corollary that matters more:** the baseline here — cascade, **basket=10, text index** — scores
comparison **74.1%** / temporal **83.3%**, well above §3's basket-3/older numbers (60.6% / 65.2%). The
multi-hop gap is smaller than we thought; a wide-enough single-query basket already assembles the
evidence and answers it better than decomposition does. Joins NMS / BM25 / cross-encoder rerank /
`triage_coverage` on the measured-and-refuted list. **Acted on:** the route is now UNREGISTERED by
default (`LIBKB_ENABLE_DECOMPOSE=true` re-registers it), so the router cannot select it at all; the
engine, prompts and tests remain so this measurement reproduces. It is NOT a win.

---

## 4. Cost — verified prices, 2026-07-14

| model | input $/1M | output $/1M | free quota |
|---|---|---|---|
| `qwen-flash` | $0.05 | $0.40 | 1M tokens / 90 days |
| `qwen-plus` | $0.40 | $1.20 | 1M / 90 days |
| **`gemini-3.5-flash`** (default) | $1.50 | **$9.00** | — |
| `gemini-3.1-flash-lite` | $0.25 | $1.50 | — |
| `gemini-embedding-001` | $0.15 | — | — |

**Our default model is the most expensive thing in the table.** 500 eval queries: `gemini-3.5-flash`
**$6.75** vs `qwen-plus` **$1.50**. A live smoke test on `qwen-plus` reached the right page and cited
correctly in 2 calls. Switching the answer tier is a cost decision, not a quality sacrifice —
**but it has not been A/B'd, so it is not yet a claim** (§5).

**Embedding is ~an order of magnitude cheaper than generation per token.** That single fact is why
text-indexing changes what corpus sizes are reachable at all: a 22,633-article legal code costs ~34M
generated tokens through the question flywheel, and **0** through a text index.

---

## 5. What we have NOT measured — read this before believing anything above

1. **The vocabulary bridge.** On our own 30 held-out *colloquial Vietnamese* questions against
   *English jargon-heavy* pages, the **question index WINS at R@1 (83.3% vs 60.0%)** — the exact
   opposite of MultiHop's verdict. MultiHop's queries are formal, entity-rich English, which is what
   text-embedding is best at. **Neither corpus can settle the other's case.** Do not retire the
   question flywheel on MultiHop's evidence alone; measure a colloquial/cross-lingual set at n≫30.
2. **Qwen vs Gemini on answer quality.** Never A/B'd. The cost case is overwhelming; the quality case
   is one smoke test.
3. **Whether the cascade's 93.3% survives the AI-News import.** The A/B ran on a 115-page library.
   Retail's recall did not move (§2.1), so it *probably* holds — but that is an inference, not a
   measurement, and inferring is how we have been wrong six times.
4. **Cross-encoder reranker.** Named as the highest-value experiment since D-036 and still not run.
   It attacks R@1 directly, which is the weakest number we have.
5. **A real external retrieval benchmark.** FiQA (57,638 docs, 648 human-written questions, human
   qrels, BM25 bar nDCG@10 = 0.236) is downloaded and the harness is built. **~11M embedding tokens,
   0 generation.** `libkb bench benchmarks/fiqa --yes`.
6. **Synthesis / aggregation** ("what are the trends across all X?"). No single page answers these,
   so no index fixes them. `agent/synthesizer.py` does not exist.
7. **Recency.** The catalog has no date column. "What is the newest model?" is a temporal query and
   the sieve is blind to it. Live for the AI-News domain; would be fatal for a legal corpus with
   superseded articles.
8. **Statistical power.** n=30 on the flagship A/B. Most claims in §1 are 1–2 flipped cases.

---

## 6. Metric bugs — six times the broken thing was the measurement

Kept because the next reader will otherwise re-derive them and be misled the same way.

| # | the bug | what it claimed | the truth |
|---|---|---|---|
| 6.1 | `page_acc` counted ancestors | route B looked worse | it was better |
| 6.2 | The judge failed a *richer* answer for citing material the reference page didn't mention | cascade 83.3% | **90.0%** — *"the reference is a floor, not a fence"* |
| 6.3 | **near-duplicate = cosine ≥ 0.90** | 65% of the corpus is duplicated | the LIVE, working library scores **95.7%** on the same bar. Gemini crowds every cosine into 0.87–0.95 (D-028). **The metric measured nothing.** Replaced by a margin (`score@1 − score@10`), which needs no threshold. |
| 6.4 | `probe-index`'s LOI regime | text-index beats questions by **24 points** | the queries were **generated FROM the pages being searched** — a tautology. The real margin is 2–3 points. |
| 6.5 | **`AllGold@3` is the ceiling on the answer** (my claim, in a decision AND a docstring) | inference queries cannot exceed 14% | they score **93.8%**. `evidence_list` lists *every* supporting fact, not the *minimum set needed*. |
| 6.6 | `both` index fused by max-pool | `both` == `questions`, exactly | question↔question cosines are systematically higher than question↔text, so max-pooling let questions win every tie **by construction**. The text side was never consulted. Fixed with RRF (rank fusion needs no shared scale). |
| 6.7 | **FiQA nDCG@10 = 0.621** (this one CONFIRMED) | too high? metric bug? | cross-checked bit-for-bit against **`pytrec_eval`, the official TREC scorer** — identical. **The first metric check this session that confirmed instead of refuting.** The number is real; it is just not good. Verification proves correctness, not quality. |

**Permanent countermeasure:** `libkb eval --save` + `libkb rejudge`, and now `eval-multihop --save`.
**The answers are the expensive artifact; grading them is not.** Save them, and a broken rubric costs
nothing to fix. And when a metric looks surprising, **cross-check against a reference implementation
before quoting it** (6.7) — six of seven checks refuted us; the discipline is what caught them.

---

## 7. Defects the big corpus exposed — none of which appeared at 231 pages

This is the answer to *"why do we need a bigger corpus?"* It was never about prettier numbers.

| # | defect | class |
|---|---|---|
| 7.1 | Page title pasted twice (`split.py` already names its slices; `survey.py` prefixed again) | crash |
| 7.2 | No slug length cap → a 200-char headline breaks Windows' 260-char path limit | crash |
| 7.3 | **DashScope does not enforce JSON schema server-side** → Qwen returns `["…"]` where `[{"vi":…}]` was asked → parser crashes → `index_page_safe` swallows it → **439 of 2,079 pages (21%) silently never entered the catalog.** The import printed a success line. | **silent data loss** |
| 7.4 | **Qwen refuses some content and says nothing** (`choices: null`) — it will not summarise a news article about the Epoch Times; Gemini does so without comment. | **data integrity** |
| 7.5 | **`generate_json` "repaired" a truncated response into an invented answer + `sufficient: true`** — 40/301 one-char answers | **P6 violation** |
| 7.6 | `embed()` had no retry and leaked raw `httpx` errors past `answer_query_safe`, killing a 301-case run after ~200 paid queries | lost money |
| 7.7 | **DashScope client had NO request timeout** → a hung socket froze a run for 30 min at 0% CPU (SDK default is 600s/request, and our retry can't fire until the request returns). Fixed: `timeout=60`, `max_retries=0` (we own the retry). | 30-min hang |
| 7.8 | FiQA has empty documents → Gemini rejects "content contains an empty Part" → the whole batch dies at doc 500 of 57,638. Fixed: blank text → `"(empty)"` placeholder (a blank doc is irrelevant to every query; the placeholder preserves alignment and matches nothing). | run killed |

**The principle now written into the code:**
> **A broken call must fail CLOSED (silence), never OPEN (an invented answer).** And
> `compose_answer` — the function that decides whether the library speaks — must not take the
> model's `sufficient` on trust.

---

## 8. The improvement backlog, ranked by the evidence above

| rank | change | evidence | cost |
|---|---|---|---|
| 1 | **Concurrency in ingest and eval.** 2,079 pages took ~40 min sequentially; a 10k-page legal corpus would take **5 hours**. **DONE (D-047 + D-054):** `eval-multihop` runs 8-wide; and the shared-catalog race is fixed — a reentrant `RLock` on `Catalog` serialises every sqlite connection touch (this was the ~0.5% `count()` NoneType, pinpointed from a logged traceback). INGEST can now be parallelised safely on top of that lock; `runner.run_eval` still sequential. | every run today | catalog thread-safe · runner pending |
| ~~5b~~ | ~~**Cheap-reader selector** — a lite LLM reads bodies to pick the basket~~ **REFUTED (D-053).** MEASURED n=80: ANSWER −7.0 (every kind, inference −11.5), coward +5.6, only ~7% cheaper. A lite model selects worse than strong-header-triage, and picking whole pages short-circuits the last-resort net accuracy actually rides on. Diagnostic bonus: triage keeps only 69% AllGold and under-fills to ~4 pages — the system works *despite* triage, via last-resort. | D-053; probe 2c | refuted |
| ~~2~~ | ~~**Raise `cascade_max_pages` 3 → ~10**~~ **DONE (D-049).** New defaults: **basket=10, fetch=50** (`cascade_depth=default`), tiered minimum/default/deep. MEASURED clean: 73.9%→84.0% answer, honesty 92.7%→91.0%, 2.4× tokens. Confidence gate shipped default-off (refuted on qwen — overconfident). | §3 / §2.4 | shipped |
| ~~3~~ | ~~**Make the index kind configurable; default `text`**~~ **DONE (D-045)** — `LIBKB_INDEX_KIND`, default `text`; catalog locked to one representation (bug-6.6 guard); `reindex --index-kind`. Live library not yet reindexed (destructive — user's call). | §2.2: wins every metric, costs 0 generation | ~~code~~ shipped |
| ~~2b~~ | ~~**Bigger BASKET for multi-source**~~ **DONE (D-052): `cascade_max_pages` 10 → 20.** The coverage PROMPT was refuted (D-051); the diagnostic (`diag_multihop.py`) said the ceiling is basket SIZE (AllGold@10=75%, @20=93%). MEASURED (2 seeds × n=200, gemini): ANSWER **+4.5**, temporal **+7–9**, coward **−3–4**, honesty **HELD 99.3%** (null-only n=301), +22% tokens. A ceiling not a floor (cost only where evidence exists). Bigger, more robust win than the snippet. | §3 by-kind; D-052 | shipped |
| 2c | **Two threads D-052 leaves open.** (1) answer 77–79% still trails the AllGold@20=93% ceiling → sweep basket>20 (do NOT extrapolate — 15 was a dead spot; measure). (2) temporal alone at 58% is its own floor → probe the ACTUAL triage basket's article coverage to split its selection-vs-synthesis gap before spending. | D-052; D-051 | one sweep + one probe |
| ~~3b~~ | ~~**Restore "why THIS page" to the triage card on a text index**~~ **DONE (D-050).** `query_snippet`, model-free. MEASURED (2 seeds × n=200, gemini-3.5-flash): ANSWER +1.7, coward −1.4, honesty flat, +7% tokens. Small consistent win; shipped default-on (`triage_snippet_chars`, 0=off). Did not move the multi-hop ceiling → see 2b. | §3 | shipped |
| 4 | **Settle the vocabulary bridge** (§5.1) before retiring the question flywheel | two corpora say opposite things | one eval |
| 5 | **Cross-encoder rerank** between propose and triage | R@1 is the binding ceiling (Retail **34.9%**) | one batch, no walks |
| 6 | **FiQA** — the first externally-valid sieve number | none yet | ~11M embed tokens |
| 7 | **Re-ingest the mis-parsed PDF book** — its `References` page (13k chars) is STILL in the catalog and retrievable as "evidence" | D-037 | destructive; needs the user |
| 8 | **Date-awareness** in the catalog (recency + supersession) | §5.7 | design |
| 9 | **`agent/synthesizer.py`** — no index answers a cross-document question | §5.6 | design |
| 10 | **Shelf hygiene** — merge `Root Cause Analysis` + `KPI Interpretation` (19×/14× mutual theft) | ROUTING_REDESIGN §5 | free probe exists |

---

## 9. How to reproduce every number here

```bash
# FREE — no LLM calls at all
libkb probe-recall                    # §2.1 the sieve, LOO vs LOI, by level and pooling
libkb probe-separability              # are sibling books separable?
libkb probe-misshelved                # which pages fit another book better?
libkb probe-catalog                   # is the shortcut gate calibrated? (margin, not cosine)

# EMBEDDINGS ONLY — no generation
libkb probe-index                     # §6.4 question vs text vs sections vs both (RRF)
libkb bench-multihop                  # §2.2 — needs the MultiHop library built
libkb bench benchmarks/fiqa --yes     # §5.5 — ~11M embed tokens

# COSTS GENERATION — always prints the bill and stops without --yes
libkb probe-granularity <folder>      # what leaf size does this corpus want?
libkb eval --cases evals/holdout.json --mode cascade --save   # §1
libkb eval-multihop --limit 200 --yes --save …                # §3
libkb eval-multihop --null-only --yes --save …                # §3.1 — the P6 test
libkb rejudge <saved.json>            # re-grade saved answers for almost nothing
```

The MultiHop corpus lives in its own library so it cannot contaminate the real one:

```bash
export LIBKB_LIBRARY_DIR=benchmarks/multihop/library
export LIBKB_DB_PATH=benchmarks/multihop/catalog.db
```
