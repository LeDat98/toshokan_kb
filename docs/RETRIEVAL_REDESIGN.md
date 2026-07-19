# Retrieval redesign — stop using the LLM as a sieve

**Status:** PROPOSED. No code written. Written in response to the user's challenge:
*"the whole knowledge base is ~200k tokens and one answer burns 50k — a quarter of the corpus.
This librarian is not professional; he is wasteful."*

That challenge is correct, and the fix is not another patch. This document argues that the
**agentic tree-walk is the wrong shape of machine**, gives the measurements and the theorems that
say so, and specifies what to build instead.

Everything numeric below is either measured on our own corpus (free, reproducible with `libkb
probe-*`) or cited to a primary source. Where a source is only asserted, it says so.

---

## 0. The one-sentence diagnosis

> **We are using the LLM as the SIEVE. It should be the ORACLE.**

Our own measurements say this plainly, and we ignored them for weeks:

| | what it is good at | what it costs |
|---|---|---|
| embedding | a **bad oracle** (top-1 = 39.3% on an unanticipated intent) but a **good sieve** (right page in top-10 **90.7%** of the time) | ~0 |
| LLM | a **good oracle** (judges a handful of candidates well) | ~2–5k tokens **per call** |

And yet the current design asks the LLM to sift the library hop by hop: **9–13 calls per query**,
each call resending the entire conversation.

---

## 1. Where the 49,120 tokens actually go

Measured across the 30 held-out walks (`--mode walk`, shelf routing):

```
distinct information the walk ever saw :   8,601 tokens / query
what we actually pay                   :  45,268 tokens / query   ← 5.3x the information
```

**Four fifths of the bill is re-reading things the librarian has already seen.** Every LLM turn
resends the whole conversation, so cost is **O(T²)** in the number of turns. The per-turn trace of a
real walk:

```
1,105 → 1,407 → 1,825 → 2,941 → 4,999 → 7,018 → 8,644 → 10,941 → 13,660
```

Each turn adds only ~1–2.7k of genuinely new content. The rest is rent.

This is why every cost fix so far has disappointed. The spine cap (§0a) was worth −62% because it
shrank a thing that gets multiplied by T. The page digest was worth −8% and then **lost the eval
outright (+17%)** because it attacked the symptom while the librarian compensated by reading more.
**You cannot patch your way out of a quadratic.**

---

## 2. Three findings that condemn the walk

### 2.1 The hierarchy does NOT accelerate search. (And I claimed it did — wrongly.)

I measured that pruning to `top-1 domain → top-1 shelf` keeps R@3 at 96.7% while discarding 79% of
the library, and called that saving "free". **It is not a saving at all.** To score a container by
`max` over its pages, you must first score *every page inside it*. The pruning narrows what the
**LLM** sees; it saves no retrieval work whatsoever.

Worse, the sound version of this idea does not survive our dimensionality. A container bound you can
compute *without* touching the leaves (centroid + radius — the **cone bound**, Ram & Gray, *Cone
Trees*, KDD 2012) prunes logarithmically in N but **degrades exponentially in dimension**. At 768-d
it collapses to brute force. That is precisely why the ANN field abandoned trees for **HNSW**.

⚠️ A related trap we avoided by luck, worth writing down: taking the **element-wise max of a
container's leaf vectors** and dotting that with the query is *not* an upper bound on the best leaf.
I verified this — it fails **80.8%** of the time on random unit vectors. (Our code takes the max of
the dot products, which is exact. But anyone "optimising" this later will reach for the other one.)

**Conclusion:** the tree earns its keep for **citation, curation, human browsing, and progressive
disclosure of content**. It does **not** earn its keep as a search accelerator, and it must stop
being the LLM's decision structure.

### 2.2 Greedy descent over a tree is provably not optimal — even with a perfect scorer

Zhuo et al., *Learning Optimal Tree Models Under Beam Search* (ICML 2020, arXiv:2006.15408) prove
that greedy/beam descent over a tree is **not Bayes-optimal even when every node scorer is trained
optimally**, because of the training/testing discrepancy: **a wrong turn at depth 1 is
unrecoverable.**

That is D-029's finding — "`open_book` is an irreversible commitment" — as a general theorem. We
patched *one* level of it by deleting the book hop. The theorem says the disease is the descent
itself.

The principled hierarchical alternative (Probabilistic Label Trees, Wydmuch et al., NeurIPS 2018)
scores a node by **P(some relevant leaf below)** — a *sum/noisy-OR*, not a max — and comes with a
regret bound. Note the split we had conflated:

- **`max` = the safety bound** (what could be down there at best) — for *pruning*;
- **`sum`/noisy-OR = the estimator** (how much evidence is down there) — for *ordering*.

We used max for both. That is a real conceptual error, and it is why our container ordering was
never better than a coin flip's cousin.

### 2.3 PageIndex — the system we set out to beat — does not walk either

Read from their source, not their marketing (`pageindex/retrieve.py`, `cookbook/*.ipynb`):

- Their open-source retrieval is **2 LLM calls**: dump the **whole tree** (titles + summaries, text
  stripped; ~12.3k tokens for a document) into **one** prompt → the model returns a `node_list` →
  fetch those nodes' text → answer. **No embeddings. No hop-by-hop agent.**
- The **MCTS** in their tutorial is *not in the code* ("more details will be released soon").
- There is **no sufficiency loop, no retry, no rollback** in the retrieval code. That exists only in
  a blog post.
- Their tree is **per-document**. For multi-document they concede a separate selection layer — and
  there they go back to **vector search** (`DocScore = (1/√(N+1))·Σ ChunkScore`).

**And the 98.7% is soft.** In their own results file, their LLM judge scores **136/150 = 90.7%**.
The 98.7% appears only after **humans re-labelled 12 of the 14 misses** as benchmark errors. Their
quoted baselines (ChatGPT 31%, Perplexity 45%) are **copied from a competitor's blog**, not re-run.

So: **our 96.7% answer_acc already beats PageIndex's honest number.** We are not losing on quality.
We are losing on architecture — and we invented a hop-by-hop walk that they never had.

---

## 3. The proposal: a cascade, not a walk

The shape is the oldest one in retrieval and in computer vision: **a cheap stage with very high
recall, feeding an expensive stage with high precision** (Viola & Jones' attentional cascade; Wang,
Lin & Metzler, *A Cascade Ranking Model*, SIGIR 2011; Faster R-CNN's RPN → RoI head).

```
 ① PROPOSE     (0 LLM calls, ~10 ms)
    ANN over every page vector in the corpus → top-N (N ≈ 20)
    HNSW, not a tree. The tree is not in this path at all.
    NO diversification. NO NMS. MEASURED — see §4.2. It costs 10 points of recall.

 ② TRIAGE      (1 LLM call, ~1.5–2k tokens)
    Show the librarian, for each of K ≈ 5 candidates: its PATH, its DESCRIPTION, and its
    SECTION HEADERS (~59 tokens per page). He puts pages in a BASKET, and names the
    sections he wants. **He never sees a full page here.**

 ③ ANSWER      (1 LLM call, ~5–7k tokens)
    The basket is opened ONCE: the chosen SECTIONS (not whole pages) → cited answer +
    an explicit sufficiency verdict.
    This call is never resent, so its payload is billed exactly once.

 ④ STOP or EXPAND   (arithmetic, not vibes)
    Fagin's Threshold Algorithm: τ = the best score anything unseen could still have.
    Stop when τ < the k-th best CONFIRMED score. Otherwise pop the next candidates
    from the queue (free) and repeat ③ — at most once.
```

**Budget: 2 LLM calls, ~7–9k tokens** — against 9–13 calls and 49k today. **~5–6× cheaper.**

### 3.1 The basket, and why the full text must never enter the navigator's conversation

This is the user's contribution, and it is the sharpest structural point in the whole redesign:

> *Read the description first and decide whether to keep the page in a reference basket — instead
> of reading it all and only then declaring it useless.*

The reason it matters is not that a description is smaller. It is **where** the text sits:

- Text in the **navigator's conversation** is resent on **every later turn** → billed **T times**.
- Text in the **answerer's call** is billed **exactly once** — that call is never resent.

So the fix is not to compress what the librarian has read (the page digest — which we shipped,
measured, and had to switch off: it cost **+17%** because the librarian, robbed of the text,
compensated by reading *more*). The fix is that **the full text must never enter the conversation at
all.** Don't read-then-shrink. **Don't read.**

MEASURED on the live library (125 pages):

| unit | tokens |
|---|---|
| a full page (what the librarian reads today) | **1,571** (median 1,644 · **max 12,842**) |
| its section headers — enough to triage | **59** |
| its two largest sections — enough to answer | **516** |
| **a section vs a page** | **13.5× cheaper** |

78% of pages have ≥2 same-level headings, so sectioning is free structure that is already there.

⚠️ **But do not oversell this.** Section-reading alone, inside the *current walk*, is worth **−21%**
(≈49k → 36k), not the 2.7× first hoped: page text is only ~30% of the bill, and the menu — resent
every turn — is **49%**. Cutting a 30% component by 13× cannot fix a quadratic. It is worth doing
because it is cheap, it makes the *answer* more precise (less off-topic text), and it defuses the
12,842-token mis-parsed page that can wreck a single query. It is **not** a substitute for §3.

**Accuracy: the same ceiling.** Measured on the 30 held-out colloquial questions:

| | R@1 | R@3 | R@5 |
|---|---|---|---|
| dense proposal over every page | 83.3% | **96.7%** | 96.7% |
| *(the agentic walk, for comparison)* | | *96.7% answer_acc, 49k tokens* | |

A **3-candidate** shortlist contains the right page as often as the 13-call walk finds it.

---

## 4. The user's two objections — answered, and one of them only partly

### 4.1 "If the documents are not enough, how do you roll back?"

Rollback becomes **easier**, not harder. The walk had to physically un-walk (`go_back`), and a wrong
book put the answer out of reach entirely (§2.2's theorem). A cascade keeps a **priority queue**:
"not enough" simply means *pop the next candidates*. They were already scored. It costs nothing.

And the decision to pop is not a vibe. **Fagin, Lotem & Naor, *Optimal Aggregation Algorithms for
Middleware* (JCSS 2003)** describe exactly our setting — cheap **sorted access** (the embedding
ranking) plus expensive **random access** (the LLM's judgment) — and their Threshold Algorithm is
**instance-optimal**. The rule is arithmetic: maintain τ = the best possible score of anything not
yet examined; stop when τ falls below the k-th best confirmed score.

This replaces "LLM, do you think you have enough?" with a test that cannot hallucinate.

### 4.2 "At scale, near-identical documents will flood the candidate list with redundant paths"

The objection is right. **The obvious fix is wrong, and we measured it before shipping it.**

I proposed NMS (Non-Maximum Suppression, from object detection) plus facility-location facet
coverage. Then I ran it on the 30 held-out questions. **Diversification does not merely fail to
help — it destroys recall:**

```
  K     plain     NMS(τ=0.93)
  1     83.3%       83.3%
  2     90.0%       86.7%
  3     96.7%       86.7%   ← plain is already at the ceiling here
 10     96.7%       86.7%
 50    100.0%       86.7%   ← NMS never recovers. It DELETED the right page.
```

NMS suppresses the correct page **because it is too similar to a higher-ranked one** — and that
similarity was corroboration, not redundancy. The research literature warned about exactly this:
diversity pays only when a query has multiple facets; for a single-fact question ("what is the GMROI
formula?") near-duplicate pages are **evidence**, and forcing diversity throws it away.

**So: no diversification in the retrieval path.** That is the third theoretically-sound idea this
project has had to kill on measurement (after hybrid BM25 and the page digest).

The objection still needs an answer, and it is a **different** one:

1. **Deduplicate at INGEST, not at query time.** Two pages with the same content are a *library*
   defect, not a *ranking* problem. `probe-misshelved` already finds the mutually-stealing pairs;
   the mutual ones are merge candidates for a human.
2. **Keep K small.** The recall curve above is flat from K=3. A 5-candidate shortlist cannot be
   "flooded" — the flooding problem is an artefact of returning 50 paths, which the measurement says
   we should never do.
3. **If a query really is multi-faceted, diversify THEN** — gated on a detected multi-aspect query,
   and only after an eval shows the gate works. Not by default. Never by default.

### 4.3 The design constants, measured rather than guessed

| constant | value | how it was decided |
|---|---|---|
| `K` (candidates the LLM sees) | **5** | the recall curve flattens at **3** (96.7%); 5 gives headroom |
| `N` (ANN fetch depth) | **20** | recall is saturated well before this; deeper only adds noise |
| diversification | **off** | measured: −10 points of recall (§4.2) |
| triage payload per page | **~59 tok** (section headers) | vs 1,571 for the full page |
| answer payload per page | **~516 tok** (the chosen sections) | vs 1,571 for the full page |

---

## 5. What this costs us — the honest ledger

**It changes a founding principle, and we should say so out loud.** P1 says the AI is an *active
seeker* that *walks*. After this change it no longer walks hop by hop.

What is genuinely preserved:
- **Progressive loading.** Nothing is bulk-dumped: a shortlist of spines, then only the chosen pages.
- **Agency where it matters.** The librarian still chooses which pages to read, still judges
  sufficiency, still asks for more, still returns an honest NOT_FOUND.
- **The library metaphor at the human layer.** Citations, shelves, cross-references, curation — all
  unchanged. The *reader* still sees a library.

What is genuinely lost:
- The aesthetic of the walk. And with it, **a machine we can now prove was suboptimal** (§2.2).

What we should *stop claiming*:
- That the hierarchy makes retrieval fast. It does not (§2.1). **HNSW does.** The tree is for
  provenance and for people.

**The ceiling.** Our sieve's recall is ~90% on intents nobody anticipated. No downstream cleverness
beats a candidate list that does not contain the answer. So the highest-value work after this
redesign is **raising recall**, not saving tokens:
- a **cross-encoder reranker** between ② and ③ (the classic middle tier of a cascade — it is what
  lifts R@1, and R@1 = 39.3% is our weakest number);
- a **stronger embedding model** (the user's own suggestion, and it is well-aimed);
- **the demand-side flywheel** (§8.4, already shipped): real queries → real (question, page) pairs.
  This is the only source of the *head* of a Zipf query distribution, and generated questions
  provably cannot cover it.

---

## 6. What to measure before writing any of it

1. ✅ **Reproduce the O(T²) claim** on the eval logs — **8,601 distinct tokens vs 45,268 paid (5.3×)**.
2. ✅ **Recall curve**, K = 1…50, held-out set — **flat from K=3 at 96.7%**. Design constant fixed.
3. ✅ **Diversification** — **REFUTED. NMS costs 10 points of recall** (96.7% → 86.7%, and it never
   recovers). Do not ship it. See §4.2.
4. ✅ **Page vs section economics** — section = **59 tok** (headers) / **516 tok** (2 largest) vs
   **1,571** for a full page. **13.5×.** 78% of pages are already sectioned by their own headings.
5. ⏳ **Ingest prerequisites** (needed by both architectures, so no work is wasted):
   - **the 12,842-token page** is a mis-parse. Cap and split at ingest.
   - a raw page with no `description` needs one — and it is **free**: `gen_questions` already makes
     one `model_lite` call per page at ingest. Add `description` to that schema. No new call.
   - persist the **section index** so triage never has to load a page body.
6. ⏳ **Cross-encoder rerank, offline** — take top-20 from ANN, re-rank, measure R@1/R@3. *Costs
   tokens; one batch, no walks.* **R@1 = 39.3% (LOI) is our weakest number and the true ceiling on
   everything downstream.** This is the highest-information experiment left.
7. ⏳ **Then** build the cascade behind a flag and A/B it against the walk on the *same* 30 held-out
   questions with the *same* judge. **Prediction to falsify: `answer_acc` ≥ 96.7% at ≤ 15k tokens and
   ≤ 3 LLM calls.** If tokens fall but `answer_acc` falls with them, the walk was buying something
   real and this document is wrong.

---

## 7. Sources

- **Zhuo et al., *Learning Optimal Tree Models Under Beam Search*, ICML 2020** (arXiv:2006.15408) —
  greedy/beam tree descent is not Bayes-optimal even with optimal node scorers.
- **Wydmuch et al., *A no-regret generalization of hierarchical softmax*, NeurIPS 2018**
  (arXiv:1810.11671) — PLT; node score = P(relevant leaf below) = sum/noisy-OR, not max.
- **Ram & Gray, *Maximum Inner-Product Search Using Cone Trees*, KDD 2012** — tree pruning is
  logarithmic in N but exponential in dimension; why ANN abandoned trees.
- **Fagin, Lotem & Naor, *Optimal Aggregation Algorithms for Middleware*, JCSS 2003** — the Threshold
  Algorithm; instance-optimal stopping with cheap sorted + expensive random access.
- **Wang, Lin & Metzler, *A Cascade Ranking Model for Efficient Ranked Retrieval*, SIGIR 2011**;
  **Viola & Jones, CVPR 2001** — high-recall cheap stages feeding precise expensive ones.
- **Ding & Suel, *Faster Top-k Document Retrieval Using Block-Max Indexes*, SIGIR 2011** — the IR
  name for hierarchical max-bounds with rank-safe skipping.
- **Lampert, Blaschko & Hofmann, *Efficient Subwindow Search*, CVPR 2008 / PAMI 2009** — the same
  branch-and-bound theorem in computer vision.
- **Bodla et al., *Soft-NMS*, ICCV 2017**; **Agrawal et al., *Diversifying Search Results*, WSDM
  2009** (IA-Select); **Nemhauser, Wolsey & Fisher 1978** — (1 − 1/e) for submodular greedy.
- **Hearst, CACM 2006** — a strict single-parent tree forces a misfiling on any item with two
  legitimate homes. (Our `see_also` cross-references, §8.1, are the standard remedy.)
- **PageIndex** — github.com/VectifyAI/PageIndex, `retrieve.py` + cookbooks;
  Mafin2.5-FinanceBench `result_gpt4o.json`. Read directly, 2026-07-13.
