# SCORECARD — what this system actually does, measured

> **2026-07-19 — the multi-agent architecture (D-061) shipped but is NOT re-measured here.** Narration,
> agent roles, the MCP/A2A seam, the calculator, and front-door routing are plumbing + default-off knobs
> (see `docs/AGENT_ARCHITECTURE.md`). The cascade's measured behaviour below is unchanged: the roles are
> behaviour-preserving wrappers and routing is default-off. **No new accuracy/cost numbers are claimed
> for them.** When the router is turned on and measured (its lite-call tax, its social-vs-cascade
> precision), the numbers land here with their `n`.
>
> **2026-07-20 — product features, likewise not new accuracy numbers.** The semantic answer cache,
> multi-turn rewrite, and synthesis route (D-062) are default-safe and, in the synthesis case,
> **honestly UNMEASURED** (§5.6). Query decomposition was measured and REFUTED (§3.2). The accuracy
> tables below are unchanged.

**Last updated: 2026-07-15 (measured numbers); 2026-07-19 (arch note); 2026-07-20 (product note above).** Rewrite this file after every major change. Its only job is to let a
future version be compared honestly against this one, so **every number here carries its `n`, its
regime, and the command that produced it.** A number without those is not evidence, it is decoration.

Three rules for maintaining it:

1. **Never quote a number without its regime.** LOO ("a paraphrase of a question we anticipated") and
   LOI ("an intent we never anticipated") differ by 30 points on the same system. Quoting the first
   as "accuracy" is lying with true numbers.
2. **§5 (What we have NOT measured) is the most important section.** A scorecard that only lists
   wins is a marketing page. When a gap gets closed, move it up; when a new gap appears, add it.
3. **Record the metric bugs too (§6).** Nine times in this project the broken thing turned out to be
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
  the evidence; the window is too narrow. Same shape as MultiHop's AllGold@20 0.935 vs @3 0.296. Of
  the two fixes it points to, only one survived: the **wider window** shipped (backlog #2). The
  **reranker was measured and REFUTED** (§2.4, D-048) — so what has to close this gap is a better
  SELECTOR over the wide window, not a better ranker of it (backlog #5).
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

### 2.5 Hybrid BM25, re-examined on the corpus that should have favoured it (D-065)

`libkb probe-lexical benchmarks/fiqa` — **0 generation calls**, cached vectors, 648 human questions.

D-032 refuted BM25 fusion in 2026-07 on two query sets that were *adversarial to BM25 by
construction*: LLM-generated questions written **from the pages being searched** (metric bug 6.4),
and **cross-lingual** Vietnamese paraphrases against English pages, where BM25 has no tokens to
match at all. The objection was fair — so it was re-run where BM25 must win if it ever wins: same
language, real lexical overlap, human relevance labels, 57,638 documents.

| arm | nDCG@10 | R@10 | R@100 |
|---|---|---|---|
| **dense** (shipped) | **0.621** | **0.701** | **0.920** |
| BM25 alone | 0.235 | 0.298 | 0.512 |
| hybrid RRF (what `hybrid_shortlist=true` does today) | 0.440 | 0.518 | 0.877 |
| hybrid + stopword-filtered query | 0.441 | 0.530 | 0.880 |
| hybrid, fused only on rare query terms (df ≤ 1%) | 0.436 | 0.549 | 0.885 |

**The harness reproduced two numbers it did not choose** — dense nDCG@10 = 0.621 (§2.2, to three
decimals) and BM25 nDCG@10 = **0.235 vs BEIR's published 0.236**. After seven metric bugs, a harness
that cannot reproduce a known result may not be used to refute one.

- **D-032 replicates, and on far better evidence.** Fusion costs **−0.18 nDCG@10**. Not a small
  regression, and not an artifact of the old test sets.
- **Two rescue hypotheses were tested and both failed.** Stopword-filtering the query moved it
  +0.001; gating fusion to queries carrying a rare term moved it −0.004. The 2026-07 result was not
  a configuration bug — *that hypothesis was raised here and is now refuted.*
- **And the deeper question — does BM25 see gold the embedder is BLIND to?** Fusion asks two rankers
  to vote; complementarity asks whether the weak one finds anything the strong one never retrieves.
  They come apart, so it was measured separately: of **1,706 gold documents, BM25 finds 10 (0.6%)
  that dense misses at k=100**, across 10 of 648 queries. Of the 16 queries dense misses entirely,
  BM25 rescues 2. **There is no hidden complement to recover** — by fusion or by any escalation
  scheme, since 0.6% is the ceiling on what a *perfect* trigger could add.
- **Mechanism, and it is D-048's:** a strong first stage leaves a second signal nothing to add.
  RRF weights both rankers equally, so mixing a 0.235 ranker into a 0.621 one drags it to 0.44.

**Scope — what this does NOT settle.** FiQA is conversational finance prose. A corpus whose queries
carry hard identifiers (an article number, a SKU, an error string, a function name) is a different
population, and it is the one lexical search exists for. This says: **on prose knowledge bases with
a strong embedder, lexical adds ~nothing, and no amount of wiring changes that.** It does not say
lexical is worthless everywhere — it says our corpora have to look different before it is worth
re-opening. (This is also why coding agents lean on `grep`: code is identifier-dense and has no
comparable embedding index. That regime is not ours.)

### 2.6 THE SELECTION EXPERIMENT — and the confound that had the answer backwards (D-068)

`libkb probe-selection --root benchmarks/multihop --limit 150` · gemini-3.5-flash · window 50 ·
MultiHop-RAG (2,077 pages / 609 articles). Every arm sees the **same** candidate pool.

**The premise of this whole research thread was that the agent loses to the sieve** — probe 2c:
*"triage keeps 69% AllGold, the embedder's top-10 keeps 75%."* Every arm below was built to close
that gap. The first run reproduced it: at basket 20 the `embedder` arm retained **89.0%** and no LLM
arm beat it.

**Then the control that should have been run first.** The LLM selectors take **3.4–4.4** pages; the
embedder arm takes **all 20**. Retention rewards taking more, so that comparison measures basket
size, not selection. The embedder's own curve (free — 0 LLM calls):

| embedder basket | 3 | 4 | 5 | 10 | **20** |
|---|---|---|---|---|---|
| retention | 53.6% | 59.7% | 63.7% | 77.7% | **89.0%** |
| AllGold | 16.0% | 21.3% | 24.7% | 42.7% | **61.3%** |

**At an equal page budget the result inverts, and not by a little:**

| arm | pages taken | retention | AllGold | vs embedder at the same size |
|---|---|---|---|---|
| embedder | 4.0 | 59.7% | 21.3% | — |
| **`rich`** (Tier 0) | **4.1** | **88.1%** | **58.7%** | **+28.4 retention · +37.4 AllGold** |
| `headers` (shipped) | 4.4 | 86.6% | 57.3% | +26.9 · +36.0 |
| `set` | 3.6 | 82.6% | 50.0% | +~26 · +~32 |
| `trace` (coverage map) | 3.4 | 79.7% | 42.7% | +~23 · +~24 |

- **The active-selection thesis holds, decisively.** `rich` reaches **88.1%** retention on **4.1**
  pages — within 0.9 points of what the embedder needs **20** pages to reach. The agent is not
  worse than the sieve at picking; it is ~5× more page-efficient.
- **Probe 2c's 69%-vs-75% was confounded the same way** (a ~4-page selector against a 10-page
  embedder), and so was the first pass of this run. The artifact, D-064 and the research notes were
  all written on top of it. Corrected here.
- **The real defect is UNDER-FILLING, not mis-picking.** Every selector is allowed 20 pages and
  takes 3–4. Retention tracks pages-taken almost perfectly across the arms — and that is the lever
  nobody has pulled.
- **`rich` (Tier 0) is the best selector measured**: +1.5 retention over shipped `headers` on
  *fewer* pages, and +2.4 on `comparison` (94.2% vs 91.8%). Costs +56% input tokens, no extra call.
- **`trace` (the coverage map) is REFUTED as delivered** — worst LLM arm (79.7%) and the fewest
  pages taken (3.4). Handing the model a map of which candidate covers which part appears to
  *convince it that it is done*: it fills the parts and stops. The tool works; telling the agent
  the answer makes it less thorough, which is the same shape as the refuted coverage PROMPT (D-051).
- `set` also underperforms `headers` (82.6% vs 86.6%) and takes fewer pages — same mechanism.

### 2.6b The ReAct loop: it DOES route tools adaptively — and it never finishes

`--arms embedder,agent` · same 150 queries · 1,149 LLM calls (**7.7 per query**) · 4.67M input tok.

| arm | pages | calls/query | retention | AllGold | comparison | inference | temporal |
|---|---|---|---|---|---|---|---|
| embedder@4 | 4.0 | 0 | 59.7% | 21.3% | 66.7% | 55.4% | 55.6% |
| **`rich`** | 4.1 | **1** | **88.1%** | **58.7%** | **94.2%** | **85.2%** | **83.3%** |
| `headers` | 4.4 | 1 | 86.6% | 57.3% | 91.8% | 85.0% | 81.2% |
| `agent` (ReAct) | 4.4 | **7.7** | 84.2% | 53.3% | 90.9% | 80.9% | 79.1% |

**The tools ARE chosen by question type, unprompted — this is the part that works:**

| question kind | `coverage_map` | `find_in_candidates` | `read_section` | `ask_page` | `select` |
|---|---|---|---|---|---|
| comparison (n≈66) | **52** | 206 | 77 | 5 | 18 |
| inference (n≈44) | **12** | 259 | 53 | 0 | 26 |
| temporal (n≈40) | **30** | 166 | 35 | 1 | 9 |

`coverage_map` on ~79% of comparison and ~75% of temporal questions but only ~27% of inference —
**the agent worked out on its own that a multi-part question needs a coverage map and a single-fact
one does not.** Adaptive tool routing is real, and it is correct. It also spent `ask_page` — the
only tool that costs money — six times in 150 queries, preferring the free tools as instructed.

**And it still loses to a single call, because it never commits.** `select` fired voluntarily on
**53 of 150** queries; **147 hit the step ceiling** and were closed out by the forced `select`. It
spends every step exploring — `find_in_candidates` alone averages ~4.2 calls per query, issued one
pattern per turn — and the budget dies before it decides.

So the verdict is **not** "worse at selecting". It is *right instincts, no closing move* — and the
three fixes are all untried and none is fundamental:
1. **Batch the tool calls.** The loop already counts a multi-tool turn as ONE step; the model emits
   them one at a time. Four patterns in one turn would cost one step instead of four.
2. Raise `pool_max_steps` — buying the same behaviour at more cost, so the least interesting.
3. Show the model a commit deadline ("N steps left"), still enforced in code as it already is.

### 2.6c The three ReAct fixes, and the fill lever (D-069) — n=50, same protocol

`--limit 50 --arms embedder,headers,rich,rich+fill,agent`. **n=50 is a different sample from §2.6,
so read the arms against each other, not against the numbers above.**

| arm | pages | LLM calls/query | retention | AllGold |
|---|---|---|---|---|
| embedder@5 (equal budget) | 5.0 | 0 | 62.7% | 18.0% |
| embedder@20 | 20.0 | 0 | **93.2%** | **72.0%** |
| `headers` (shipped) | 4.5 | 1 | 88.8% | 62.0% |
| **`rich`** | **4.5** | **1** | **92.8%** | **72.0%** |
| `rich+fill` | 4.7 | 1 | 93.0% | 70.0% |
| `agent` (fixed) | 5.6 | ~7 | 89.7% | 66.0% |

**`rich` matches embedder@20 on AllGold exactly (72.0%) using 4.5 pages instead of 20**, and lands
0.4 retention points behind it. Against the embedder at its OWN page budget it is **+30 retention /
+54 AllGold**. One call. This is the result the project should build on.

**The three ReAct fixes worked on the mechanism and did not convert into a score.**
- *Voluntary commits: 35% → 98%.* `select` fired on its own for 49 of 50 queries (was 53 of 150);
  the step ceiling was hit **zero** times (was 147/150) and the fallback to shipped triage fired
  **zero** times. Batching the tool calls, carrying `turns_left` in every tool result, and 6→8 steps
  did exactly what they were meant to.
- *And it still loses to one `rich` call* — 89.7% vs 92.8%, at ~7× the calls and 6× the tokens.
- *A cost the fixes introduced:* `ask_page` (the paid tool) went from 6 calls in 150 queries to
  **46 in 50**. Told to batch and given a deadline, the agent stopped being frugal.
- *And it became LESS discriminating, not more.* `coverage_map` was fired on 79% of comparison
  vs 27% of inference questions; now it is ~85% / ~87% — near-uniform. **Instructing it to batch
  everything into one turn removed the incentive to choose.** Adaptive routing was real and the fix
  for pacing cost it.

**`triage_fill` is a null result.** Told plainly that the basket is a ceiling it should approach,
the selector went from 4.5 pages to **4.7**, retention +0.2, AllGold −2.0. Under-filling is real and
is not reachable by instruction — the same shape as the refuted coverage prompt (D-051). If it is
worth closing, it needs a code mechanism (top up the basket from the ranked pool), not more words.

### 2.6d The answer-level A/B: retention did NOT carry through. `rich` stays default-OFF.

`libkb eval-multihop --limit 100 --seed 11` · gemini-3.5-flash · identical cases · **answer cache
forced off** (see below — the first attempt at this A/B was destroyed by it).

| | `lean` (shipped) | `rich` |
|---|---|---|
| **ANSWER** (88 answerable) | 70.5% | **71.6%** |
| HONESTY (12 nulls) | 100% | 100% |
| coward | 14.8% | 14.8% |
| comparison | 22/33 | **23/33** |
| inference | 29/32 | 29/32 |
| temporal | 11/23 | 11/23 |
| input tokens/query | 14,785 | **18,062 (+22%)** |

**+1.1 points is ONE flipped comparison case.** Honesty flat, coward flat, everything else
identical. By this project's own standard (§5.8 — *"most claims in §1 are 1–2 flipped cases"*) that
is not evidence, and it costs +22% tokens. **`triage_card=rich` is NOT promoted to default.**

The honest reading: `rich` clearly wins on **retention** (§2.6/§2.6c — it matches a 20-page embedder
using 4.5 pages), and that advantage did not reach the answer. Two candidate explanations, and this
run cannot separate them: the basket is already large enough at 20 that better *selection within it*
changes little, or the ceiling is the **answerer**, not the selection. The second is the more
interesting hypothesis and it is now the open one — temporal sits at 47.8% with the gold in the
basket.

**⚠️ The first attempt at this A/B was invalid, and the cause is worth more than the result.**
Both arms came back **bit-identical on every metric** (77.3% / 100% / 6.8% / 22-30-12-16), and the
`rich` arm reported *fewer* input tokens than `lean`. Cause: the semantic answer cache (D-062)
serves any question within 0.92 cosine of one already answered — so arm B answered **nothing** and
replayed arm A. Confirmed: the contaminated `rich` run logged **zero** `cascade_done` lines against
75 in the clean re-run. **The contamination inflated the score by +6.8 points** (77.3% → 70.5%).
Fixed in code — `evals/multihop_answer.run()` now forces `enable_answer_cache=False` and no longer
trusts the caller to remember — with a regression test. Recorded as metric bug 6.9.
*Older `eval-multihop` numbers in §3 predate the cache (D-062, 2026-07-20) and are unaffected.*

### 2.7 The score-only frontier: what selecting WITHOUT reading is worth (D-071)

`libkb probe-selection --arms embedder,adaptive,conformal` · MultiHop n=150 · window 50 · **0 LLM
calls, 0 generation tokens** — free, so it needs no `--yes`. The sweep below is the same command
varying `--basket` / `--buffer` / `--alpha`.

Two published training-free selectors, built as arms because the size of the true-page set is not
constant — TP is 2.75 documents and moves with the kind (comparison 2.25 · temporal 2.49 · inference
3.46) while every selector measured so far commits to a near-constant 3.0–3.2:

- **Adaptive-k** (arXiv 2506.08479) — cut the ranked list at its sharpest score drop, take `B` more.
- **Conformal filtering** (arXiv 2511.17908) — calibrate one threshold so the kept set contains
  **every** true page on at least (1−α) of queries. Adapted here: the nonconformity score is the
  margin each query needed to keep **all** of its gold, so what is certified is `superset` itself,
  not per-document recall. Cross-fitted over 5 folds — no query is scored under a threshold it
  helped calibrate.

**The conformal guarantee is exact, and that is the harness's correctness check.** The certificate
is conditional on the pool containing TP (the 92.7% ceiling), so predicted absolute superset is
(1−α)×0.927. Observed, at every level:

| α | predicted | measured |
|---|---|---|
| 0.40 | 55.6% | **56.0%** |
| 0.30 | 64.9% | **64.7%** |
| 0.20 | 74.2% | **74.0%** |
| 0.10 | 83.4% | **83.3%** |
| 0.03 | 89.9% | **90.7%** |

Every point within 0.8. (The same class of external check as BM25 0.235 vs BEIR's 0.236, §2.5.)

**The frontier — superset against documents committed, all free:**

| taken ≈ | embedder (fixed k) | adaptive-k | conformal | ctx tok |
|---|---|---|---|---|
| 3.2 | 21.3% | — | — | 4,374 |
| 3.8 | 24.7% | 25.3% (B=0) | — | ~7,100 |
| 5.4 | 38.0% | 40.0% (B=2) | — | ~9,200 |
| 6.4 | 42.7% | 42.7% (B=3, at 6.0) | 37.3% (α=.6) | ~9,800 |
| 11.1 | 61.3% | — | 64.7% (α=.3) | ~18–20k |
| 15.8 | 78.0% | — | 83.3% (α=.1) | ~27–29k |
| 22–24 | 92.7% (k=50, the ceiling) | — | 90.7% (α=.03) | 40–43k |

**Verdict — both are NULL as selectors, and the reason is the finding.**
Adaptive-k sits **on** the embedder curve (0 to +2 points at matched `taken`). Conformal is worth
**+3 to +5** but only in the wide regime, and *below* the curve when tight. Neither is a mechanism
for choosing better; both are mechanisms for choosing **more**.

**What it settles, and this is worth the run on its own:** at the target `taken ≈ 4`, the best
score-only selector reaches **~25–32% superset**. Reaching the 90% goal from scores alone costs
**≈22 documents and ~40,000 ctx tokens** — nearly **7×** the ≲6,000 budget. *The 28 points still
missing from the pool cannot be bought from the sieve's scores at any price we would pay.*

**And the same frontier says the LLM selector is already far above it — which nothing had measured
before.** Reading `set` / `rich` / `agent` (§2.6, same pool, same n) against the free curve at the
**same** `taken`:

| selector | superset | taken | free curve at that `taken` | the LLM's contribution |
|---|---|---|---|---|
| `set` | 42.7% | 3.0 | ~20% | **+23** |
| `agent` | 36.7% | 3.2 | ~21% | **+16** |
| `rich` | 64.7% | 7.0 | ~45% | **+20** |

So the selection layer is **not** the weak component; it is worth roughly **+20 points of superset
at any basket size**, and `set` reaches 42.7% on 3,677 ctx tokens where the sieve needs 6.4
documents and 9,795 tokens for the same number. **Reading beats scoring, and score-cleverness does
not close the gap.** The remaining coverage has to be bought by reading — which retires the
free-mechanism line and leaves the sufficiency gate (§8) as the only live direction.

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
   measurement, and inferring is how we have been wrong eight times.
4. **How good the SELECTOR could be.** *(Was "cross-encoder reranker, still not run" — it has since
   been run and REFUTED, §2.4/D-048. This is what replaces it.)* What is still unmeasured is whether
   a **better-informed or set-shaped** triage closes the 69%-vs-75% gap of probe 2c. Today's triage
   sits at the single weakest selector configuration in the literature — *pointwise* (each candidate
   judged alone), *binary* (take/leave, no comparison), on *one 200-char passage + bare section
   titles*. Reranking is dead; enriching the card and selecting a **set** are different objectives
   and untouched by D-048. `libkb probe-selection` is the harness; **no arm has been run yet.**
5. **FiQA *selection*** — §2.2 measured FiQA's SIEVE (nDCG/Recall vs human qrels). What no one has
   measured, here or in the literature, is what the TRIAGE keeps out of that top-50: FiQA
   qrels + `probe-selection --gold qrels` needs no gold answer, so it is cheap and genuinely new.
6. **Synthesis / aggregation** ("what are the trends across all X?"). No single page answers these,
   so no index fixes them. `agent/synthesizer.py` now EXISTS (D-062, a registry route: wide scan →
   parallel lite MAP per page → strong REDUCE, cited) — but it is **UNMEASURED on purpose**. It needs
   an aggregative held-out set (questions whose gold answer spans many pages) before it earns a number,
   and building that set honestly is the open work, not the route.
7. **Recency.** The catalog has no date column. "What is the newest model?" is a temporal query and
   the sieve is blind to it. Live for the AI-News domain; would be fatal for a legal corpus with
   superseded articles.
8. **Statistical power.** n=30 on the flagship A/B. Most claims in §1 are 1–2 flipped cases.

---

## 6. Metric bugs — nine times the broken thing was the measurement

Kept because the next reader will otherwise re-derive them and be misled the same way.

| # | the bug | what it claimed | the truth |
|---|---|---|---|
| 6.1 | `page_acc` counted ancestors | route B looked worse | it was better |
| 6.2 | The judge failed a *richer* answer for citing material the reference page didn't mention | cascade 83.3% | **90.0%** — *"the reference is a floor, not a fence"* |
| 6.3 | **near-duplicate = cosine ≥ 0.90** | 65% of the corpus is duplicated | the LIVE, working library scores **95.7%** on the same bar. Gemini crowds every cosine into 0.87–0.95 (D-028). **The metric measured nothing.** Replaced by a margin (`score@1 − score@10`), which needs no threshold. |
| 6.4 | `probe-index`'s LOI regime | text-index beats questions by **24 points** | the queries were **generated FROM the pages being searched** — a tautology. The real margin is 2–3 points. |
| 6.5 | **`AllGold@3` is the ceiling on the answer** (my claim, in a decision AND a docstring) | inference queries cannot exceed 14% | they score **93.8%**. `evidence_list` lists *every* supporting fact, not the *minimum set needed*. |
| 6.6 | `both` index fused by max-pool | `both` == `questions`, exactly | question↔question cosines are systematically higher than question↔text, so max-pooling let questions win every tie **by construction**. The text side was never consulted. Fixed with RRF (rank fusion needs no shared scale). |
| 6.9 | **The semantic answer cache replayed arm A's answers to arm B** | `lean` and `rich` are bit-identical on every metric (77.3% / 100% / 6.8%, same by-type breakdown) — a clean null result | arm B ran **zero** cascades and answered nothing; it served cached answers from arm A. The cache (D-062) matches anything within 0.92 cosine, which is right in production and fatal in an A/B. **The contamination INFLATED the score by +6.8 points** (77.3% → 70.5% clean). Fixed in code: the eval forces the cache off, with a regression test — a knob the caller must remember is one that will be forgotten. |
| 6.8 | **Retention compared a ~4-page selector against a 20-page embedder** (and probe 2c, a ~4-page selector against a 10-page embedder) | the agent SELECTS WORSE than the sieve — the premise of a whole research thread | at an EQUAL page budget the agent retains **+28 points** (rich 88.1% on 4.1 pages vs embedder 59.7% on 4). Retention reads like a quality metric and behaves like a BUDGET metric. The control that exposed it was free. **Equalise what each arm may take before comparing selectors.** |
| 6.7 | **FiQA nDCG@10 = 0.621** (this one CONFIRMED) | too high? metric bug? | cross-checked bit-for-bit against **`pytrec_eval`, the official TREC scorer** — identical. **The first metric check this session that confirmed instead of refuting.** The number is real; it is just not good. Verification proves correctness, not quality. |

**Permanent countermeasure:** `libkb eval --save` + `libkb rejudge`, and now `eval-multihop --save`.
**The answers are the expensive artifact; grading them is not.** Save them, and a broken rubric costs
nothing to fix. And when a metric looks surprising, **cross-check against a reference implementation
before quoting it** (6.7) — eight of nine checks refuted us; the discipline is what caught them.

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
| ~~5~~ | ~~**Cross-encoder rerank** between propose and triage~~ **REFUTED (D-048).** qwen3-rerank on FiQA top-50 HURT R@1 by −5.2 (N=2k) to −9.0 (N=57k); R@5/R@10 down too. A strong first stage leaves a reranker nothing to add. *Do not re-add a reranker without a first stage weak enough to need one.* | §2.4 | refuted |
| **5b** | **The SELECTOR, not the ranker** (D-064). The step that loses is triage: it keeps **69%** of the gold where the embedder's own top-10 keeps **75%** (probe 2c). Two mechanisms shipped default-OFF, both zero new LLM calls — `triage_card=rich` (passages + marked sections, not bare titles) and `triage_mode=set` (a covering SET, not page-by-page relevance). **`libkb probe-selection` is the harness; no arm has been run.** | probe 2c; D-048 | one probe run |
| ~~6~~ | ~~**FiQA** — the first externally-valid sieve number~~ **DONE (§2.2):** nDCG@10 **0.621**, R@10 0.701, R@100 0.920, verified bit-for-bit by `pytrec_eval`. What is still open is FiQA **selection** (triage vs qrels) — see §5.5. | §2.2 | done · selection pending |
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
