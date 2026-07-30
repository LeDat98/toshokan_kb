# THE SELECTION TARGET — the one mission, and the only way it is scored

> **Read this before proposing, building, or measuring anything in the retrieval/selection layer.**
> It exists because this project has twice drifted onto a wrong question and spent real money
> answering it. The framing below is the user's, set 2026-07-29, and it supersedes every earlier
> framing in `SCORECARD.md`, `DECISIONS.md` and the private research notes.

---

## 1. The mission, in one sentence

**The sieve hands the agent 50–100 candidates. Only 2–4 of them actually hold the answer. The
agent's job is to return a set as close to those as possible — containing all of them, carrying
as little else as it can.**

That set has a name here: **TP** (true pages). Everything below is machinery for measuring how
close a selector gets to it.

## 2. What TP actually is (measured, MultiHop-RAG, free to recompute)

| | value |
|---|---|
| TP size | **2.75 documents** on average (range 2–4, **never 1**) |
| by kind | comparison 2.25 · temporal 2.49 · inference 3.46 |
| the pool contains all of TP | **92.7%** of queries at window 50 — the ceiling no selector can beat |

So the target is not "find the one right page". It is **assemble a small set, and do not leave one
of its members behind.**

## 3. The scoring contract

Optimise **`superset`**. Report the rest. Do not optimise anything else.

| metric | definition | how to read it |
|---|---|---|
| **`superset`** | fraction of queries where selection **⊇ TP** | **THE number.** Below it, the answer is unreachable no matter how good the answerer is |
| `taken` | distinct documents committed | compare arms at similar `taken`, never across |
| `overhead` | `taken` − TP | **1–2 is an acceptable trade.** It buys safety |
| `precision` | \|selection ∩ TP\| / \|selection\| | high precision with low `superset` = **too tight**, the worst failure |
| `ctx_tokens` | tokens of the pages the answerer must read | **the basket is NOT free.** This is the bill selection exists to cut |
| `retention` | fraction of pool-gold kept | ⚠️ partial credit — **rewards taking more**. Diagnostic only, never the objective |

### The three rules that stop the drift

1. **Selecting FEWER pages is not the failure. Selecting fewer than TP is.** A tight, precise set
   that misses one true page is worse than a loose one that contains them all.
2. **Never compare two selectors at different `taken`.** An arm allowed 20 documents will beat an
   arm that takes 4 on any coverage metric, and that comparison measures budget, not skill. This is
   metric bug 6.8, and it inverted the project's founding conclusion for several sessions.
3. **Always price the basket.** `ctx_tokens` is the product value. A selector that matches the
   embedder's coverage on half the tokens has won even if every accuracy number is flat.

## 4. Where it stands (2026-07-29 · MultiHop n=150 · window 50 · qwen-plus · `libkb probe-selection`)

| arm | **superset** | taken | over | precision | **ctx tok** |
|---|---|---|---|---|---|
| pool ceiling | 92.7% | 50 | — | — | — |
| embedder@20 (no LLM) | 61.3% | 11.1 | 8.8 | 23.1% | 18,130 |
| `headers` (**shipped**) | 58.7% | 6.5 | 4.2 | 46.0% | 9,222 |
| **`rich`** | **64.7%** | 7.0 | 4.6 | 44.0% | 10,509 |
| `set` | 42.7% | **3.0** | **1.0** | **71.2%** | **3,677** |
| `agent` (ReAct) | 36.7% | 3.2 | 1.3 | 70.5% | 4,601 |

**Two behaviour families, each solving half the problem:**

- **Loose** (`headers`, `rich`) — reach ~60–65% superset by carrying **4+ extra** documents.
- **Tight** (`set`, `agent`) — land at TP+1 with **70% precision**, exactly the right shape — and
  **miss a true page on ~6 queries in 10.**

**Nothing has both.** `rich` is the current best and still throws away **28 points** of coverage
that was already sitting in the pool.

### The free curve underneath it all (D-071, §2.7) — read every arm against this

Selecting from the sieve's SCORES alone, with no model, costs nothing and is now mapped:

| taken ≈ | 3.2 | 3.8 | 5.4 | 6.4 | 11.1 | 15.8 | 22–24 |
|---|---|---|---|---|---|---|---|
| best free superset | 21% | 25% | 40% | 43% | 65% | 83% | 91% |

Two things follow, and both are load-bearing:

1. **The 90% goal is not reachable without reading.** From scores alone it costs ≈22 documents and
   ~40,000 ctx tokens — about **7×** the budget below. The missing 28 points are not in the scores.
2. **The LLM selector is already worth ~+20 points of superset at the same `taken`** (`set` +23,
   `rich` +20, `agent` +16). Selection is not the weak component. **Never quote an LLM arm again
   without the free number at its own `taken` next to it** — that subtraction is the arm's actual
   contribution, and for two sessions nobody had computed it.

### The goal to beat

> **superset ≥ 90% with `taken` ≈ 4 (TP + 1), at ≲ 6,000 ctx tokens.**

## 5. The diagnosis this points at

The tight selectors do not fail at *judging* — their precision is 70% against the embedder's 23%.
They fail at **knowing they are not finished**. `set` already emits a `missing` field and the agent
already has `coverage_map`; neither is used to *check itself before committing*.

**The untried direction: a completeness check before `select`.** Not more instruction — instruction
was measured and does nothing (`triage_fill`: 4.5 → 4.7 documents, §2.6c). A mechanism: verify every
part of the question has a source, and only then commit.

**D-071 narrowed this to one live option.** The cheap way out — let a score threshold size the set —
is measured and closed (above): the coverage is not in the scores. So the check has to READ. Three
constraints the literature and our own refutations put on it together:

- It must be a **separate judge over the assembled set**, not a line added to the selector's own
  prompt. `triage_coverage` (D-051), `trace` (D-068) and `triage_fill` (D-069) all failed the same
  way — telling the selector about completeness convinces it that it is finished.
- It must score the **set**, not the passages. Set-level sufficiency is not visible passage by
  passage; a purpose-built set-level verifier beats GPT-4o-as-judge by 18 F1 on exactly this task
  (SURE-RAG, arXiv 2605.03534).
- **A tighter basket without this gate costs honesty, not just accuracy.** Insufficient context does
  not make a model abstain — it makes it improvise (Gemma 10.2% → 66.1% hallucination with
  insufficient context, *Sufficient Context*, ICLR 2025, arXiv 2411.06037). Our honesty is at 100%
  and it is the one number the project calls non-negotiable.

Reference for the gate itself: a prompted sufficiency autorater needs no ground truth and agrees
with human judgement ≥93% of the time (ibid.). That makes it one lite call, and it composes with the
WIDEN step already in the cascade.

## 6. Already measured — do NOT re-propose

| tried | verdict | where |
|---|---|---|
| Cross-encoder reranking | **REFUTED** −5.2…−9.0 R@1 | D-048 |
| Hybrid BM25 in the sieve | **REFUTED** −0.18 nDCG@10; 0.6% complement | D-065, §2.5 |
| Coverage map forced on every query (`trace`) | **REFUTED** — worst LLM arm; convinces the model it is done | D-068 |
| Cheap-reader selector (`read`) | **REFUTED** −7.0 answer | D-053 |
| Coverage *prompt* (`triage_coverage`) | **REFUTED** | D-051 |
| "Please fill the basket" (`triage_fill`) | **NULL** — 4.5 → 4.7 | D-069 |
| Adaptive-k (cut at the sharpest score drop) | **NULL** — 0 to +2 at matched `taken`; sits on the embedder curve | D-071, §2.7 |
| Conformal filtering (certified coverage) | **+3…+5 wide, negative tight.** Hits its target exactly, but buys coverage with documents, not skill | D-071, §2.7 |
| Any further score-only set sizing | **CLOSED.** 90% from scores costs ~22 docs / 40k tokens, ~7× the budget | D-071, §2.7 |
| ReAct pacing fixes (batch, deadline, +steps) | mechanism fixed (commit 35%→98%), score flat, **cost the agent its adaptive tool routing** | D-069 |
| Query decomposition | **REFUTED** −11…−17 | SCORECARD §3.2 |

**Tool routing DOES work and is worth keeping:** unprompted, the agent used `coverage_map` on 79% of
comparison questions and 27% of inference ones. That instinct is the loop's best property — do not
destroy it again by telling the agent to fire everything at once.

## 7. How to run it

```
# preflight — prices the run on 3 real pools, spends nothing, warns if on the expensive tier
LIBKB_DB_PATH=benchmarks/multihop/catalog-text.db LIBKB_LIBRARY_DIR=benchmarks/multihop/library \
  libkb probe-selection --root benchmarks/multihop --limit 150

# run it — qwen-plus is ~4x cheaper per input token and measures the same DIFFERENCE
LIBKB_MODEL=qwen-plus ... libkb probe-selection --limit 150 --arms embedder,headers,rich,set,agent --yes
```

The equal-budget control is **free** (0 LLM calls) and must be run before any comparison is quoted.
`embedder`, `adaptive` and `conformal` all cost nothing, so a run of only those needs no `--yes` and
prints the **matched control automatically** — the probe bisects the basket until the embedder
commits to the same number of DOCUMENTS, because a basket is counted in pages and `taken` is not:

```
libkb probe-selection --arms embedder,adaptive,conformal          # free, no --yes needed
libkb probe-selection --arms conformal --alpha 0.03               # what 90% actually costs
libkb probe-selection --arms embedder --basket 4                  # and 5, 10, 20
```

**Answer-level confirmation** (`eval-multihop`) is the last gate before changing a default —
`superset` is a proxy, not the product. The eval forces the answer cache off; do not re-enable it
(metric bug 6.9: it replayed arm A into arm B and inflated a score by 6.8 points).
