# Routing redesign — the book is a STORAGE unit, not a ROUTING unit

**Status: ✅ CONFIRMED AND SHIPPED (D-031).** The A/B this document demanded was run on the held-out
set it specified, at the sample size it chose. Route B won on every axis; the falsifiable prediction
held. See §3.2 for the result, and for the two things this document got *wrong*.
**Audience:** the implementing agent. Read this top to bottom before touching code.
**Author:** review/analysis pass, 2026-07-12. Supersedes nothing; extends `docs/ARCHITECTURE.md` P1–P10.

> **Result in one line:** `answer_acc` **90.0% → 96.7%**, `page_acc` 66.7% → 80.0%, backtracks
> **2.1 → 0.9**, tokens −9%. Paired: **6 rescues, 0 losses.** But read §3.2's caveats before quoting
> any of it — the accuracy delta is 2 cases, and this document's cost model was wrong by 7x.

---

> ### Nothing is deleted. Read this before anything else.
>
> This document uses the phrase "delete the book hop". That is shorthand, and it is easy to
> misread. **No book is removed** — not from disk, not from `_meta.json` / `toc.json` / `pages/`,
> not from ingest, not from citations, not from the menu the agent reads.
>
> Exactly one thing goes away: **the forced choice of a book BEFORE any page title has been seen.**
> Today `open_book("X")` makes every page of every *other* book on the shelf vanish from the agent's
> view; if X was wrong, the correct page is no longer reachable and the agent can only thrash.
> After the change the agent stands at the shelf, sees the tables of contents of all its books at
> once (grouped by book), and picks a page. It still ends up inside a book — it just arrives there
> by choosing a page rather than by committing to a book first.
>
> A real librarian does not pull one book off the shelf and only then open it. They tilt several,
> glance at each contents page, and *then* pull one. "Which book" and "which page" are one act, not
> two. **The book stops being a door and becomes a label on the page.**
>
> And per §1.5 this applies **only to shelves the measurement condemns** (e.g. `Retail ▸ KPIs`,
> 74.4% separable). Shelves whose books are genuinely distinct (`AI ▸ LLM`, 100%) keep the book hop
> untouched.

## 0a. DO THIS FIRST — `one_line` is 40x too long, and it is costing you half your tokens today

This is independent of everything else in this document. It needs no design decision, no eval, and
no approval. **Measured over all 125 TOC entries in the live library:**

```
TOC one_line lengths (characters):  min 0 · median 1013 · mean 806 · p90 1154 · MAX 1436
```

A `one_line` is supposed to be a spine label. These are **essays**. `library/models.py` even has a
`one_line_of()` helper — the ingest path (`ingest/split.py`) is simply not using it when it writes
`TOCEntry.one_line`.

Consequences, all three of which are live **right now**, before any redesign:

1. **Cost.** Modelled on the real menus with the real hop/backtrack counts (every LLM turn resends
   the whole conversation, so cost is quadratic in turns and linear in menu size):
   | | input tokens per query |
   |---|---|
   | today's walk, `one_line` as-is | **20,382** |
   | today's walk, `one_line` capped at 120 chars | **9,640 (−53%)** |

   Half of every query's token bill is bloat in a field that is supposed to be a single line.

2. **Accuracy — probable.** When every option in a menu is described by a 1000-character paragraph,
   *everything sounds relevant*. This is precisely the "ambiguous decision boundaries between
   semantically similar categories" that Lu et al. (ACL 2024, §1.5) name as the dominant cause of
   LLM mis-selection. **Hypothesis worth testing for free: capping `one_line` raises page accuracy
   as well as halving cost.** Run the eval before and after — it is the cheapest experiment
   available.

3. **It is the ONLY reason the union-TOC design looks expensive.** The worst shelf's union TOC is
   13,999 tokens today and **2,364 tokens** with `one_line` capped at 120 chars.

**Action:** cap `one_line` at render time in `agent/tools.py` (never trust the stored value), AND
fix the ingest path to write a real one-liner. Then re-run the eval to see if accuracy moved.

---

## 0. TL;DR for the implementer

The walk currently loses **all** of its routing accuracy at exactly one hop: choosing which
sibling **book** to open. Two free measurements (no LLM calls, reusing vectors already in
`library/_catalog/catalog.db`) show that hop is **not fixable by writing better descriptions** —
the books themselves are not separable — and that **deleting the hop from the routing path is
worth +8.2 points**.

The change: **stop making the agent commit to a book.** Replace `open_book(title)` with
`open_shelf()`, which returns the **union of every book's TOC on that shelf, grouped by book**.
The book stays visible as context and stays intact as storage/citation. It just stops being a
decision.

Do the prerequisite bug fixes in §4 FIRST — two of them corrupt the very eval you will use to
judge this change.

---

## 1. The evidence

### 1.1 Where the accuracy actually goes

Baseline (n=50, `--mode walk`, seed 7), cumulative → conditional per-hop:

| hop | cumulative | **conditional** |
|---|---|---|
| root → domain | 100% | 100% |
| domain → shelf | 96% | 96% |
| **shelf → book** | 86% | **89.6%** |
| book → page | 86% | **100%** |

Page-selection *inside* a book is already perfect. The entire 14-point loss is the book hop.
(Caveat: domain=100% is cheap — there are only 2 domains. It will decay as the library grows.)

### 1.2 Sibling books are not intrinsically separable — so descriptions cannot save this hop

Method (zero API calls): for every catalog question, build each book's centroid from **its own**
question vectors with the query **left out** (LOO), then ask whether the true book's centroid beats
its siblings' on the same shelf.

```
SIBLING-BOOK SEPARABILITY (content-only, leave-one-out, descriptions not involved)
decisions evaluated : 904
true book wins      : 744/904 = 82.3%
median top1-top2 gap: 0.0189

per-shelf:
   74.4%  n= 336  [5 books]  Retail ▸ KPIs & Performance Analytics
   78.3%  n= 152  [3 books]  Retail ▸ Inventory & Demand Planning
   84.7%  n= 176  [4 books]  AI ▸ RAG
   92.7%  n= 192  [4 books]  Retail ▸ Merchandising & Store Operations
  100.0%  n=  48  [2 books]  AI ▸ LLM

top content confusions (true book -> book that stole it):
   19x  Root Cause Analysis            ->  KPI Interpretation
   14x  KPI Interpretation             ->  Root Cause Analysis      <- bidirectional!
   13x  Homecenter Inventory Patterns  ->  Seasonal Merchandise
   11x  PDF Retrieval Augmented QA     ->  RAG Fundamentals
   10x  Root Cause Analysis            ->  KPI Dictionary
```

Read that carefully. **The books' own content separates them only 82.3% of the time. The LLM
walking with descriptions is already at 89.6% — it is beating the intrinsic ceiling of the tree.**

Corollary, and this is the important one: **rewriting `rebuild_description.md` to be more
contrastive will NOT fix this hop.** You cannot write a discriminative spine label for two books
that say the same thing. `Root Cause Analysis` ⇄ `KPI Interpretation` confusing each other in
*both directions* is the signature of one book that got split in two.

Separability also degrades monotonically with sibling count: 2 books → 100%, 5 books → 74.4%.

### 1.3 Deleting the book hop is worth +8.2 points

Same 904 questions, same LOO centroid method, two routes raced head to head:

```
DOES THE BOOK LEVEL HELP OR HURT ROUTING?  (content-only, leave-one-out)
questions on multi-book shelves : 904

  A) shelf -> book -> page       :   68.3%   (page correct end-to-end)
       of which, book hop right  :   82.3%
  B) shelf -> page  (union TOC)  :   76.4%   <-- book level DELETED

  B rescues cases A lost         : 91
  B loses cases A won            : 17
  net change from deleting book  : +8.2%

  median margin, book choice     : 0.0189
  median margin, page-on-shelf   : 0.0236   <-- decisions are MORE confident too

pages per multi-book shelf (the menu size route B would face):
    42 pages across 5 books   Retail ▸ KPIs & Performance Analytics
    24 pages across 4 books   Retail ▸ Merchandising & Store Operations
    22 pages across 4 books   AI ▸ RAG
    19 pages across 3 books   Retail ▸ Inventory & Demand Planning
     6 pages across 2 books   AI ▸ LLM
```

**Why it works:** `open_book` is an *irreversible commitment*. Choose the wrong book and the right
page leaves the search space entirely — it is no longer in any TOC the agent can see. The only
recovery is to read useless pages and `go_back`, which is exactly the "misroutes correlate with
long thrashing walks (12 hops)" pattern recorded in `.agent/STATE.md`. Route B never makes that
commitment, so it has no such trap. The 91 rescues are precisely those unrecoverable cases.

**Why this is also the librarianship answer:** a reference librarian does not pick a book and then
open it. They walk to the shelf and scan the spines and tables of contents of *everything on it*.
"Which book" and "which page" are resolved in a single act, not as two sequential commitments. The
current design asks the agent to do something no human librarian does.

**Why this closes the PageIndex gap:** PageIndex's 98.7% is *within a single document* — doc →
section → page. **They have no book-selection hop at all.** The system is not losing to them
because it has more levels; it is losing because it invented a lossy commitment they don't have.
The way to compete is not "make every level 99.7% accurate" — it is **have fewer committed
decisions**.

### 1.4 Honest limits of this evidence

Do not oversell these numbers in the commit message.

- This is a **content-centroid proxy, not an LLM walk**. The LLM outperforms the centroid on the
  book hop (89.6% vs 82.3%), so **68.3% / 76.4% are NOT end-to-end predictions.** What is
  trustworthy is the **sign and rough magnitude of the difference** (+8.2%, 91 rescues vs 17
  losses) and the **mechanism** (premature commitment is unrecoverable) — neither depends on
  whether the chooser is a centroid or an LLM.
- The questions are still the leaky ingest-generated ones. LOO removes the exact-row leak, not the
  vocabulary leak. Absolute levels are optimistic; the A-vs-B comparison is not affected.
- Small corpus: 19 books, 6 shelves, 115 pages.
- **Route B does not scale forever.** It trades a 4-way book choice for a 42-way page choice.
  That is a win today. At 200 pages/shelf it will not be. See §5.

---

## 1.5 What the literature says (added after a deep-research pass)

Independently verified by fetching the sources directly. **The research workflow's own adversarial
verifier voted to REFUTE several of these — that vote is not trustworthy**: it marked two
semantically equivalent claims with opposite verdicts, the run was degraded by API quota
exhaustion, and its skeptics are instructed to default to "refuted" when they cannot confirm. The
claims below were re-checked by hand against the primary sources.

**RAPTOR (Sarthi et al., ICLR 2024, arXiv:2401.18059) ran essentially this exact experiment and
reached the same conclusion.** They compare *tree traversal* retrieval (top-k per layer, then
descend — architecturally identical to `browse → open_book → read_page`) against *collapsed tree*
retrieval (flatten every node of every level into one pool, search once). Verbatim from the paper:

> "Collapsed tree with 2000 tokens produces the best results, so we use this querying strategy for
> our main results."
>
> Collapsed tree "offers greater flexibility than tree traversal; i.e., by searching through all
> the nodes simultaneously, it retrieves information that is at the correct level of granularity
> for a given question."

They adopted the collapsed strategy for **all** reported results. This is published, independent
corroboration of the §1.3 measurement and of the premature-commitment mechanism.

Two important refinements from that same paper, which **modify** the design below:
- Non-leaf (summary) nodes contributed **18.5%–57%** of retrieved nodes across datasets, and
  full-tree search beat leaf-only search. Abstraction levels earn their keep **as candidates**, not
  as gates. (LibraryKB cannot adopt this directly — "leaf pages are the single source of truth" is
  a hard rule — but it argues for keeping book identity *visible* in the union menu, which §2.2
  already does.)
- RAPTOR's tree uses **soft clustering** (GMM), so a chunk may belong to several parents. The
  hierarchy is deliberately not a strict single-parent tree. Support for "one storage location,
  many access points."

**Flattening must be SELECTIVE, not wholesale.** This corrects an error in an earlier draft of this
brief.
- *On Flat vs Hierarchical Classification in Large-Scale Taxonomies* (NIPS 2013) proves flat-vs-
  hierarchical is a **formal trade-off between two terms of a generalization bound** — hierarchy
  lowers the complexity term, flat lowers the empirical-error term. **Neither wins universally.**
  Multiplicative decay across levels is therefore *not a law*; it is one side of a tunable
  trade-off. Their node-pruning experiments beat both the full hierarchy and random pruning — but
  only when the pruned nodes are chosen by a **principled data-driven criterion**, and that
  criterion is a *confusion* quantity: the probability that top-1 and top-2 scores differ by less
  than a margin.
- Selective flattening of "inconsistent" internal nodes (arXiv:1706.01214) reports up to **7%
  Macro-F1** over top-down baselines, and explicitly beats blanket level-removal baselines.

**Consequence: `probe-separability` (§3) is not merely a diagnostic — it is the decision function.**
Flatten the book level **per shelf, where the measurement says to**, not across the library.
`AI ▸ LLM` is 100% separable with 2 books — leave it alone. `Retail ▸ KPIs & Performance Analytics`
is 74.4% with 5 overlapping books — flatten that one.

**The option-count ceiling.** *Mitigating Boundary Ambiguity and Inherent Bias for Text
Classification in the Era of LLMs* (Lu et al., ACL 2024, arXiv:2406.07001; title/abstract verified
by hand) finds LLMs are "vulnerable to changes in the number and arrangement of options," and names
the cause as **ambiguous decision boundaries between semantically similar categories** plus token/
position bias — *not* missing knowledge. That is exactly the sibling-book hop. Their fix is two
stages: **self-reduction** of 50–150 options down to a shortlist of ~5, then **pairwise contrastive
comparison in a chain-of-thought manner**. (A research subagent reading the PDF reported 94.29% at
2 options degrading to 32.51% at 60 options on gpt-3.5-turbo, and +54.1% relative from the two-stage
method. **These exact figures were NOT independently verified — treat as directional only.** Note
gpt-3.5 is weak by current standards, so the ceiling for `gemini-3.5-flash` is certainly higher; the
*shape* of the curve is what transfers, not the numbers.)

**This maps onto machinery LibraryKB already has.** The card catalog + `ask_librarian` + the newly
shipped margin gate **is** the self-reduction stage. If a shelf's union TOC grows past the safe
option count, do not reintroduce a book gate — instead: margin-gated catalog lookup to shortlist
~5 pages from that shelf, then let the LLM do an explicit contrastive comparison among them.

**On PageIndex, for the record.** The 98.7% FinanceBench figure is **vendor self-reported** for a
commercial product (Mafin 2.5) — not peer-reviewed, no per-level ablation, no error bars (Mafin 1
scored 38.0% on the same benchmark). The core PageIndex tree is **within a single document**
(doc → section → page); cross-document selection is a separate, later layer with **no published
number**. The part of the tree they benchmark is the analogue of LibraryKB's `book → page` hop —
**which is already at 100%.** Do not treat 98.7% as a target that measures what this system does.

---

## 2. The change to make

### 2.1 Principle (proposed addition to ARCHITECTURE.md)

> **The book is a unit of storage, authorship and citation. It is not automatically a unit of
> routing.** A level earns the right to be a decision point by being *measurably separable*. Where
> siblings cannot be told apart by their own content, that level must not gate the walk — it is
> flattened into the parent's menu, and the choice is deferred to where the evidence actually is.

Flattening is **per-node and evidence-driven** (NIPS 2013; arXiv:1706.01214), never a blanket
level-wide deletion.

### 2.2 Concrete implementation

All of this lives in `libkb/agent/tools.py`. **Do not touch `libkb/library/store.py`, the on-disk
layout, `_meta.json`, `toc.json`, ingest, or citations.** Books remain exactly as they are on disk.

1. **New tool `open_shelf()`** (no arguments — it opens the shelf the cursor is already on).
   It renders the **union of the TOCs of every book on the current shelf**, grouped by book so the
   book still supplies context:

   ```
   You are in: Retail ▸ KPIs & Performance Analytics  [shelf]

   Everything on this shelf (4 books, 42 pages):

     From "KPI Dictionary":
       - "Gross Margin Return on Investment"  — definition, formula, worked example
       - "Sell-Through Rate"                  — definition, formula, seasonal caveats
       ...
     From "Root Cause Analysis":
       - "Diagnosing a Sales Drop"            — decision tree from symptom to cause
       ...

   Use read_page("<title>") to read any page above.
   ```

2. **`read_page(title)` now resolves against the union TOC**, not against a single open book.
   `NavState.current_toc` becomes the shelf-wide TOC. Keep `open_book_id` only for event/citation
   display; it is no longer a gate on `read_page`.

3. **Keep `open_book(title)` as a deprecated alias** that calls `open_shelf()` and notes in its
   result text which book the model was aiming at. Rationale: the model will still try to call it,
   and there is no reason to punish it. Cheaper than fighting the prompt.

4. **Budgets stay in code (D-008).** `open_shelf` costs 1 hop, same as `browse`.

5. **Flatten per shelf, not library-wide** (this is the correction from §1.5). A shelf is flattened
   iff `probe-separability` says its books are poorly separable. Store the verdict as a field on the
   shelf's `_meta.json` (e.g. `flatten_books: true`, written by the probe, never hand-edited — same
   discipline as descriptions). Shelves whose books ARE separable (e.g. `AI ▸ LLM`, 100%) keep the
   book hop: the literature is explicit that blanket level-removal loses to selective flattening.

6. **Scale guard.** Add `max_shelf_toc_entries` to `Settings` (default 60 — above today's worst
   shelf at 42, below the region where option-count degradation bites). If a shelf's union TOC
   exceeds it, do **not** fall back to a book gate. Instead run the ACL-2024 recipe with machinery
   that already exists: margin-gated catalog lookup to shortlist ~5 candidate pages on that shelf,
   then have the model compare those few contrastively. See §5.

7. **`route.md` prompt:** update the described workflow to `browse` (domain) → `browse` (shelf) →
   `open_shelf` → `read_page`. State explicitly that on a flattened shelf the agent does **not**
   choose a book.

8. **Events:** add a `shelf` action to `NavEvent` and to `libkb/api/events.py` `StepEvent`
   (D-018 — `web/src/api.ts` is one contract with it; the frontend renders unknown actions
   generically, so no frontend change is required, but note it).

9. **Feature flag:** `Settings.routing_mode: Literal["book", "shelf", "auto"] = "auto"`
   (alias `LIBKB_ROUTING_MODE`). `auto` = per-shelf, driven by the probe verdict (item 5); `book`
   and `shelf` force one behaviour library-wide. All three must work, because §3 requires running
   `book` and `shelf` as clean control/treatment arms.

### 2.3 What NOT to do

- **Do not** delete books from disk, from `store`, from citations, or from ingest. The proposal is
  purely about what the *navigator* is allowed to commit to.
- **Do not** rewrite `rebuild_description.md` expecting it to fix the book hop. §1.2 shows it
  cannot. (A contrastive rewrite may still help the *shelf* hop — that is a separate experiment,
  do not bundle it, or you will not know which change did what.)
- **Do not** flatten the book level everywhere. §1.5: blanket level-removal loses to selective,
  measurement-driven flattening in every study that compared them.
- **Do not** ship this on the strength of the centroid proxy. Run §3 first.

---

## 2.4 Cost — route B is a BET, and the eval must settle it

Every LLM turn resends the whole conversation, so **total input ≈ T×system + (T²/2)×avg_menu_size**.
Turn count is quadratic; menu size is only linear. Route B trades a **fatter menu** for **fewer
turns**. That is a good trade only if it actually removes the backtracks.

With `one_line` capped at 120 chars (§0a), on the real library:

| | input tokens per query |
|---|---|
| A) book gate — 5.3 hops, 2.1 backtracks (measured baseline) | 9,640 |
| B) union TOC — ~3 hops, no backtrack (the bet pays) | **3,524 (−63%)** |
| B) union TOC — still backtracks once, reads 2 pages (the bet fails) | 11,655 (**+21%**) |

So: **if route B does what the 91-rescue finding predicts, it is 63% cheaper AND more accurate. If
it does not kill the thrashing, it is 21% more expensive.** A big menu, once emitted, is resent on
every subsequent turn — the quadratic cuts both ways.

**Therefore §3 must report `avg_hops` and `avg_backtracks`, not just accuracy.** If accuracy rises
but hops do not fall, the change is not paying for itself and should be reconsidered.

**Scaling note (for the "what about 1M books" objection).** Menu size is bounded by the *branching
factor* — a knob (`branching_split_threshold`) — not by corpus size. A million books produces *more
shelves*, not *bigger shelves*. What grows is depth, and it grows as O(log N): ~50M pages at
branching ~40 is a 5-level tree. Cost per query stays O(depth × branching). The union TOC is one
menu in that chain, bounded by the split threshold. **What does NOT survive scale is an uncapped
`one_line`** — that multiplies every menu at every level, which is exactly what §0a is about.

The real scaling risk is the one this whole document started from: at depth 5 you have 5 committed
decisions and multiplicative decay returns. The answer is the same at every scale — **branch only
where content is measurably separable** (§1.5), and use shortlist-then-contrast (§5) where a level
must be wide.

---

## 2.5 STATUS — what is done, and the two things blocking the A/B

**Done and verified** (reviewed against the code, not against the report): the four §4 bugs are
correctly fixed; `_scan` swaps a fresh index; `_budget_exhausted` now keeps its pages and lets the
answerer's `sufficient` flag decide; `score_case` expands `touched` to ancestors; `_resolve_child`
and `_fuzzy_toc` share a scored `_best_match`. `open_shelf` / `routing_mode` / `probe-separability`
are in. 89 tests green. A pre-existing test that encoded bug #1 was correctly deleted rather than
appeased.

**BLOCKER 1 — §0a was skipped, and it invalidates the A/B.** `_render_shelf` emits `entry.one_line`
uncapped:

```python
row = f'    - "{entry.title}"'
if entry.one_line:
    row += f" — {entry.one_line}"      # 1000+ chars each, in the live library
```

**BLOCKER 2 — the scale guard counts the wrong unit.** `max_shelf_toc_entries = 60` counts *rows*,
not *tokens*. The `KPIs & Performance Analytics` shelf has 50 pages → **passes the guard** → emits a
**~14,000-token menu**, which every subsequent LLM turn then resends.

Route B has therefore been shipped under the worst possible conditions **for route B**. Running the
A/B now would burn ~60 strong walks to produce a result that is both (a) meaningless on cost and
(b) biased against the treatment arm, because 42 options each described by a 1000-character
paragraph is the textbook definition of the "ambiguous decision boundary" failure that Lu et al.
(§1.5) identify. If route B lost that experiment, **we would not know whether the design or the
bloat was at fault.**

**Do §0a first. It is free and independent.** Cap `one_line` at render time, and change the guard to
budget **tokens** (a character/token estimate over the rendered menu), not rows.

### The queue, in order

1. ✅ **§0a — cap `one_line`.** DONE (D-030). Capped at render (`agent/tools.py`, all three
   renderers — the stored value is never trusted, so the live library is fixed with no migration)
   *and* at the source: `ingest/survey.py` was copying each file's whole frontmatter `description:`
   into `TOCEntry.one_line`. Also capped in the description prompts (`views.py`) and the API TOC
   (`routes.py`). Knob: `max_one_line_chars=120`.
   **MEASURED on the real union-TOC menus: 28,032 → 6,319 tokens (−77%).** Worst shelf (KPIs)
   **14,221 → 2,584 (−82%)** — the estimate in this document (13,999 → 2,364) was accurate.
   *(The accuracy half of the hypothesis is still untested — it needs the eval, i.e. step 4.)*
2. ✅ **Scale guard.** DONE (D-030). Rows and tokens are **two independent ceilings** and both are
   kept: rows bound the option count (an LLM cannot rank 200 titles however short they are), tokens
   bound the cost. Over either ⇒ book-by-book fallback. Added `max_shelf_menu_tokens=6000`.
   Note: with the cap in place **no live shelf trips either guard** (worst = 2,584). Had the token
   guard shipped *without* §0a, the KPIs shelf would have fallen back to book mode — and route B
   would never have been tested on the very shelf it exists to fix.
3. ✅ **§3.0 — the eval metric.** DONE (D-030). `answer_acc` (LLM judge on `model_lite`,
   `evals/judge.py`) is primary; `page_acc` is demoted to a diagnostic; `mean_input_tokens` is
   reported (judge calls excluded — scaffolding, not product). Every mode now runs through
   `answer_query`, so what gets graded is the answer a reader would actually have received.
   **The gates are DISARMED** (§3.1 item 5): every threshold we had was calibrated in book mode, on
   the leaked set, against `page_acc` — all three premises are now false.
   `libkb make-holdout` is built (writes the paraphrase set to disk so both arms score identical
   questions) but **not yet run** — it costs tokens.
4. ✅ **§3.1 — the A/B.** DONE (D-031). Route B won on every axis; **6 rescues, 0 losses**; gate
   armed at `min_answer_acc=0.90`. Full result and caveats in **§3.2** below.
5. **§2.2 item 5 — `routing_mode="auto"`**: per-shelf flattening driven by `probe-separability`,
   which §1.5 says is the correct form of this change. Currently only the library-wide `book` /
   `shelf` arms exist (fine for the A/B, not the end state). **Now the top code item.**
6. **§5 shelf hygiene** — merge `Root Cause Analysis` + `KPI Interpretation`; split the
   `Retail ▸ KPIs` shelf. Land **separately**, after the A/B, so credit is attributable.
7. **NEW — page-read cost.** Not in the original plan, and now the biggest lever: see §3.2.

---

## 3.2 THE RESULT — and the two things this document got wrong

n=30, the same 30 held-out paraphrased questions in both arms (`evals/holdout.json`), `--mode walk`
(no catalog, no shortcut — pure description routing), strong model on both sides.

| | A: `routing_mode=book` | B: `routing_mode=shelf` | Δ |
|---|---|---|---|
| **answer_acc** (the gate) | 90.0% | **96.7%** | **+6.7** |
| page_acc (diagnostic) | 66.7% | **80.0%** | +13.3 |
| book_acc | 83.3% | 83.3% | 0 |
| found_rate | 100% | 100% | — |
| **avg hops** | 5.2 | **4.3** | −0.9 |
| **avg backtracks** | 2.1 | **0.9** | **−57%** |
| mean input tokens | 53,941 | 49,120 | −9% |

**Paired, per case** — the only honest way to read n=30: on `answer_acc`, shelf **rescues 2, loses
0**; on `page_acc`, shelf **rescues 4, loses 0**. Thrashing walks (≥5 backtracks): **5 → 3**. There
is not a single regression in either metric. **Route B dominates; it does not trade.**

**The prediction held.** §3.1 item 4 demanded `answer_acc` UP **and** `hops`/`backtracks` DOWN, and
said that if accuracy rose while hops did not fall, route B was buying accuracy with tokens and
should be reconsidered rather than shipped. Accuracy rose, hops fell, backtracks more than halved,
and tokens fell too.

### Do not oversell this
The accuracy delta is **2 flipped cases**. McNemar exact: p≈0.5 (answer), p≈0.125 (page). **At n=30
the accuracy delta alone is not statistically significant.** What carries the conclusion is the
convergence of three *independent* measurements on one mechanism:
- the free centroid proxy over 904 questions (§1.3: +8.2%, 91 rescues / 17 losses);
- the **backtrack collapse** — the direct fingerprint of "wrong book ⇒ the right page leaves the
  search space ⇒ the agent can only thrash" (§1.3's "why it works");
- 6 rescues / **0** losses here.

Any one of these alone would be thin. They agree on sign, magnitude and *cause*.

### WRONG #1 — §2.4's cost model, by 7x
It predicted **−63%** input tokens if the bet paid. The measurement says **−9%**.

The model was only counting the *menu*. After §0a capped `one_line`, the union TOC is ~2,500 tokens
of a **~50,000-token** bill. **The real cost driver is the PAGES the librarian reads** — 2.1–2.3 per
walk, each one full markdown, each one **resent on every subsequent turn**. Neither this document
nor the implementer had looked at it.

Consequences: (a) the cost argument never really favoured either arm — the case for route B is
accuracy and thrash, full stop; (b) **page-read cost is now the largest untouched lever in the
system**. Candidate moves, all unvalidated: read fewer pages (`max_pages_per_nav=6`, while the walk
averages 2.1 — it is the tail that hurts); evict a page's full text from the conversation once the
agent has judged it irrelevant; summarise rather than re-send. **Measure before believing any of
them** — this same style of model already misled us by 7x.

### WRONG #2 — the baseline was ~20 points lower than we thought
Held-out, book-mode `page_acc` is **66.7%** — not the **86%** quoted throughout §1 of this document
(and everywhere else). §1.4 warned the questions were leaky and that "absolute levels are
optimistic"; it was right, and the size of the effect is large. **66.7% is the honest number.** The
per-hop decomposition in §1.1 was computed from the 86% run, so its *levels* are optimistic too —
its *shape* (all the loss on one hop) is what survived, and that shape is what the redesign acted on.

Note the counterweight: `answer_acc` in the same arm is **90%**. The system was serving readers far
better than `page_acc` ever admitted. Both facts — the harder baseline and the better service — were
invisible until §3.0's metric fix landed.

---

## 3. How to validate — run this before claiming anything

Prerequisites, in order: **§0a** (it changes the token baseline *and* possibly the accuracy that
everything else is measured against), then the §4 bugs (done).

### 3.0 Fix the primary metric first — it currently penalises route B for being right

The eval scores a case by whether the walk reached **the exact page that generated the question**.
That is not a symmetric approximation of "did it work" — **it is biased against route B**:

- Route A commits to a book and then chooses among ~8 pages. Little opportunity to answer correctly
  from a *different* page.
- Route B sees ~42 pages at once. It has far more opportunity to land on a **sibling page that also
  answers the question perfectly** — and today that is scored as a **MISS**.

The very property that makes route B better is being counted as a defect.

**Change the primary metric to answer-level correctness:** an LLM judge over the *final answer*,
with the target page's content as reference — "does this answer correctly address the question?"
Run it on `model_lite` (D-027): one cheap call per case, negligible next to a strong walk. Keep
`page_acc` as a **secondary diagnostic**, not the gate.

**Also report tokens.** `llm/client.py` already logs `input_tokens` per call — sum them per case and
report **mean input tokens per query** for each arm. That converts the cost argument in §2.4 from a
model into a measurement, for free.

### 3.1 The run

**Chosen plan: 30 cases per arm, on a held-out paraphrase set.** (Rejected: 50 cases. If the effect
is large — the proxy predicts ~+8 points — 30 shows it. If it is small enough that 30 cannot see it,
the honest answer is "this redesign is not worth its complexity", and 50 cases would not change
that. Spend the saved budget on §0a and the judge instead.)

1. Freeze a **held-out** eval set. The current one is leaked: questions come from the same catalog
   rows the system indexes. Generate a paraphrase/"Q4" variant set — take each eval question and
   have `model_lite` restate it the way a real user would (vague, wrong jargon, colloquial,
   Vietnamese) — and eval on that. Expect the 86% baseline to drop; **that lower number is the real
   baseline**, and it is the one both arms are scored against.
2. Run both arms on the **same seed** and the **same 30 cases**: `LIBKB_ROUTING_MODE=book`
   (control) vs `=shelf` (treatment), `--mode walk`.
3. Report, for each arm:
   - **`answer_acc`** (§3.0 judge) — the **primary** metric and the only one the gate may use
   - `page_acc` — secondary diagnostic only
   - **`avg_hops`, `avg_backtracks`** — the mechanism check
   - **`mean_input_tokens`** — the cost check (§2.4)
4. **The prediction to falsify:** `answer_acc` up **AND** `avg_hops` / `avg_backtracks` down. If
   accuracy rises but hops do **not** fall, route B is not doing what the 91-rescue finding says it
   does — it is paying for accuracy with tokens (§2.4 shows that costs +21%), and it should be
   reconsidered rather than shipped.
5. Only if the treatment wins: set `EvalGates` from the **new** baseline minus a noise margin. Do
   not lock a gate before the A/B — the current default (`routing_mode="shelf"`) has already moved
   the thing the gate is supposed to protect.

**Make the two diagnostics of §1 permanent and free.** Done: `libkb probe-separability`. It should
run after every `reindex` — and per §1.5 its per-shelf verdict is what decides which shelves get
flattened once `routing_mode="auto"` lands (§2.2 item 5, still outstanding).

---

## 4. Prerequisite bug fixes — ✅ DONE, verified against the code

All four are fixed correctly (reviewed in the source, not taken on report). Kept here as the record
of *why* they mattered. The first two corrupted the eval itself, which is why they were gated ahead
of everything else.

1. **`evals/runner.py` — `book_acc`/`shelf_acc`/`domain_acc` are wrong in `shortcut` mode.**
   `score_case` builds `visited` from event `node_id`s plus read pages. In `shortcut` mode the
   `lookup`/`found` events carry `node_id=None`, so `visited` holds only the returned page. If the
   shortcut returns the wrong page but the *right book*, `_deepest_reached` scores it `miss`.
   Every level below `page` is systematically understated. Fix: expand `visited` with the ancestors
   of everything touched — `visited |= {r.id for n in list(visited) for r in store.path_of(n)}`.

2. **`agent/tools.py` — hop-budget exhaustion throws away pages already read.**
   `_budget_exhausted()` returns `Terminal(status="NOT_FOUND")`, and `navigator.py:106` then does
   `pages=... if terminal.status == "FOUND" else []`. A walk that read the correct page and then ran
   out of hops reports NOT_FOUND and discards its own evidence. These are exactly the long-thrash
   cases, i.e. the ones this whole redesign is about. Fix: on budget exhaustion, if
   `state.pages` is non-empty, compose from them and let the answerer's `sufficient` flag decide.

3. **`library/store.py` — `_scan()` races with concurrent readers.**
   `_scan()` starts with `self._index.clear()` and the store is a process-wide singleton in
   `app.state`, mutated from worker threads (`move()` calls `_scan()`). An `/ingest/review/approve`
   running next to a `/query` can make `_entry()` raise `NodeNotFound` for an innocent request.
   Fix: build a fresh dict and swap it in one assignment (`self._index = new_index`).

4. **`agent/tools.py:360` — `_resolve_child` matches substrings in both directions, first match wins.**
   `if key in name or name in key` means a short title ("RAG", "CV") matches almost anything
   containing it, and the winner is dict insertion order, not similarity. Fix: exact → prefix →
   `difflib.SequenceMatcher` ratio, take the **best** score, and return `_not_here()` below a floor.

Also dead code to remove: `answerer.path_refs`, `routes._cards`. Stale comments: `tools.py:74`
("the six P1 tools… ask_librarian arrives with P2" — it's here), `NavEvent.action` docstring
(missing `ask`/`lookup`). Untracked junk at repo root: `3605-21973-3-PB2.PDF`, `abcxyz.pdf`.

---

## 5. What this does NOT solve, and what comes next

**Scale — now with an answer from the literature (§1.5).** Route B converts a 4-way choice into a
42-way choice. LLM selection accuracy *does* degrade with option count (Lu et al., ACL 2024), and
the named cause — ambiguous boundaries between semantically similar options, plus token/position
bias — is exactly the sibling-book disease. But the evidenced mitigation is **NOT** "put a
hierarchical gate back". It is **two-stage shortlist-then-compare**:

1. **self-reduction** — narrow the shelf's union TOC to ~5 candidate pages;
2. **pairwise contrastive comparison** — make the model explicitly argue the finalists against each
   other, rather than pick from a long list.

**LibraryKB already owns stage 1.** The card catalog + `ask_librarian` + the newly shipped
top1−top2 margin gate *is* a self-reduction mechanism. It was built as a shortcut around the walk;
its real job is to be the shortlister **inside** the walk. Wire it there when a shelf outgrows
`max_shelf_toc_entries` rather than reintroducing the book gate.

Note the numbers behind the degradation curve (94.29% at 2 options → 32.51% at 60, gpt-3.5-turbo)
were reported by a research subagent from the PDF and **were not independently verified** — and
gpt-3.5 is far weaker than `gemini-3.5-flash`. Treat the *shape* as real and the *thresholds* as
unknown. The 60-entry default in §2.2 item 6 is a guess; measure it.

**Shelf hygiene the data is already asking for** (do NOT bundle with the routing change; land it
separately so the eval attributes credit correctly):
- **Merge `Root Cause Analysis` + `KPI Interpretation`.** 19x and 14x mutual confusion means they
  are one book.
- **Split the `Retail ▸ KPIs & Performance Analytics` shelf.** 5 overlapping books, 42 pages, 74.4%
  separability — the worst on every metric.

**The catalog's real job.** The leave-intent-out probe (39.3% top-1 on questions the ingest-time
generator did not anticipate) settles it: **generated questions cannot cover the question space.**
They remain valuable as (a) the routing eval set and (b) a vocabulary bridge — but the catalog's
future is **demand-side**: log real user queries and the page the librarian actually landed on,
then index *those*. Real query distributions are Zipf-shaped: you never cover the infinite tail,
you cover the head, and the head can only be learned from traffic. That is the trajectory logger
(P3) and it is the highest-leverage thing left after this redesign.

**Caution on a claim in circulation:** the 98.3% cross-lingual result does *not* justify dropping
the Vietnamese rows. It was measured on vi/en pairs that are translations of the *same generated
question* — near-identical in meaning. It shows the embedder matches translations; it says nothing
about matching a novel, colloquial, wrong-jargon Vietnamese query. Keep both languages until a
proper Q4-style probe says otherwise.

---

## 6. Reproducing the measurements

Both diagnostics read only `library/_catalog/catalog.db` and make **zero API calls**. Console must
be forced to UTF-8 (cp932 machine, D-012):

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe <script> library/_catalog/catalog.db
```

- **Sibling separability** — group vectors by `book_id`, build LOO centroids, ask whether the true
  book beats its shelf-siblings for each of its own questions.
- **Route A vs route B** — same LOO machinery; route A picks the best sibling book then the best
  page inside it, route B ranks every page on the shelf directly. Compare top-1 page accuracy,
  count rescues and losses.

Port both into `libkb/evals/separability.py` as described in §3. Per §1.5 the probe is not just a
report — its per-shelf verdict is what decides which shelves get flattened.

---

## 7. Sources

Verified by hand against the primary source (the research pass's automated verifier was unreliable
here — see §1.5):

- **RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval** — Sarthi et al.,
  ICLR 2024. arXiv:2401.18059. *Collapsed tree beats tree traversal; adopted for all main results.
  Non-leaf nodes supply 18.5–57% of retrieved context. Soft (GMM) clustering ⇒ not a strict
  single-parent tree.*
- **On Flat versus Hierarchical Classification in Large-Scale Taxonomies** — NIPS 2013.
  *Flat vs hierarchical is a formal bound trade-off, not a law. Selective node pruning by a
  data-driven confusion/margin criterion beats both the full hierarchy and random pruning.*
- **Mitigating Boundary Ambiguity and Inherent Bias for Text Classification in the Era of LLMs** —
  Lu et al., ACL 2024. arXiv:2406.07001. *LLMs are vulnerable to the number and arrangement of
  options; cause is ambiguous boundaries between similar categories + token/position bias; fix is
  self-reduction to a shortlist + pairwise contrastive CoT.* (Title/abstract verified; the specific
  accuracy figures were not.)
- **Selective flattening of inconsistent hierarchy nodes** — arXiv:1706.01214. *Up to 7% Macro-F1
  over top-down baselines; beats blanket level-removal.* (Reported by the research pass; not
  hand-verified.)
- **PageIndex / Mafin 2.5 FinanceBench** — github.com/VectifyAI/PageIndex,
  github.com/VectifyAI/Mafin2.5-FinanceBench. *98.7% is vendor self-reported for a commercial
  product, no peer review, no per-level ablation, no error bars; Mafin 1 scored 38.0%. The core
  tree is within a single document; cross-document selection is a separate layer with no published
  number.*

---
---

# PART II — the next three moves (specs for the implementing agent)

Written after the A/B landed. Everything here is backed by a **free** measurement (zero API calls,
reusing the vectors already in `library/_catalog/catalog.db`). Reproduce before you build.

Part I fixed *where the librarian walks*. Part II fixes *what he carries*, *how he narrows*, and
*what he remembers*.

> ## ⚑ STATUS after implementation (D-032, D-033) — read this before trusting anything below
>
> All of Part II was reproduced, then built. **138 tests green.** Consolidated eval on the same 30
> held-out questions: **`answer_acc` 96.7% → 96.7% (Gate PASS)**, but **tokens 49,120 → 57,667
> (+17%)**.
>
> **Three of this document's recommendations were refuted by measurement.** Each was theoretically
> sound. That is the point of measuring.
>
> | § | verdict |
> |---|---|
> | **§6 page digest** | ❌ **OFF.** It made queries **17% dearer** at identical accuracy. The compression works — per-turn input *plateaus* instead of climbing — but the librarian, robbed of the full text, **reads more pages** (6 vs 5, hitting the budget) and takes more turns (13 vs 11). §6's own falsifier caught it. Also: §6's cost diagnosis was wrong — the menu is resent every turn too, so it is **49% of the bill** (2,707 × 5), not 2.5k of it. §0a's spine cap was the −62% lever; this one is −8% at best. |
> | **§7.3 hybrid BM25** | ❌ **OFF.** Recall drops on **both** query distributions at **every** fusion weight, monotonically: LOI page R@10 90.7% → 78.6%; held-out colloquial R@1 83.3% → 43.3%. A reader's paraphrase reuses almost none of the library's exact words, so BM25 grabs the common ones and drags noise up. Mechanism is real (a unit test shows it rescuing "GMROI"); it is just not what these queries are made of. |
> | **§2.2 item 5 `routing_mode="auto"`** | ❌ **DROPPED — on this document's own test.** §9 asked how many A/B cases landed on a well-separated shelf: **9 of 30**, and shelf mode lost **0 of the 9**. On `Merchandising` (92.7%) flattening *improved* things. No cow, no fence. |
> | §8.1 cross-references | ✅ shipped; reproduced **exactly** (56/115 = 49%, top delta +0.078) |
> | §7 shortlist + escape hatch | ✅ shipped — and the test written to enforce §7.4 **caught §2's `open_book` alias turning the shortlist into a gate.** The promised exit did not exist. |
> | §8.2 entry vocabulary | ✅ built, **deliberately unmeasured** (`kind='term'` so it can be A/B'd, not quietly mixed in) |
> | §8.3 `reframe` | ✅ shipped |
> | §8.4 trajectory logger | ✅ shipped — `libkb harvest`. **The answer to the founding worry.** |
>
> Two bugs the implementation would have shipped, caught by the probes themselves:
> - `build-crosslinks --dry-run` would have written a link from a **tracked** AI book to a
>   **private, gitignored** Retail page (D-020) — a private title, into git. Cross-domain refused.
> - `read_page` had no re-read guard: a page read twice entered the evidence twice and burned two
>   budget slots. Harmless until the digest existed; then a trap. Re-reads are now free.

---

## 6. THE COST BOTTLENECK — the librarian never puts a book back

### 6.1 What is actually happening

`navigator.py` runs `llm.generate(turns, ...)` in a loop, and `turns` is the **entire conversation**.
Every tool call is one LLM call, and **every LLM call resends everything seen so far**.

So when the librarian reads a page, judges it useless, and walks on — **that page's full markdown
stays in context forever**, and is re-billed on every remaining turn.

Measured on the live library:

```
125 pages · median 1,644 tok · mean 1,571 · p90 2,356 · max 12,842
whole library, bulk-dumped:   196,320 tok
measured cost of ONE query:    49,120 tok   <-- 25% of the entire corpus
```

A page read on turn 3 of an 8-turn walk is resent 5 more times: **1,644 x 5 = 8,220 tokens for one
page that may have been rejected.** After section 0a capped `one_line`, *navigation* costs ~2,500
tokens. The other ~46,000 is **page text, re-billed**.

**The walk is not wandering.** 4.3 hops, 0.9 backtracks — it walks quite straight. The problem is
that it **never forgets**. It carries every book it has touched and pays for the weight at every
step. A real librarian skims a page, decides "not this one", and **puts the book back on the shelf**.

### 6.2 The fix — and why it cannot lose information

**`compose_answer(query, nav.pages, store)` does not read the navigator's conversation.** It rebuilds
the evidence blocks from the `PageContent` objects in `nav.state.pages`, which live entirely outside
the LLM context. Verify this in `agent/answerer.py` before starting — it is the whole basis of the
change.

Therefore the full markdown sitting in the navigator's `turns` is **pure redundancy after the turn in
which it was read.** Compress it and the *answer* loses nothing.

**Implement:** after a page's read-turn, rewrite that tool response inside `turns` to a digest:

```
[PAGE - Retail > KPIs > Root Cause Analysis > Diagnosing a Sales Drop]
(read - retained as evidence) - Decision tree from the symptom "sales down" to a cause:
traffic, conversion, ATV. Does not cover inventory.
```

~50 tokens instead of ~1,644.

**Do NOT delete the page entirely.** The navigator still has to judge *"do I have enough now?"* to
call `found()`. A digest preserves that; a bare path does not. Keep the **most recently read page in
full** for one extra turn so the model can still compare two candidates head to head, then digest it
too.

Source the digest from the page's TOC `one_line` (now capped) plus the first ~2 sentences of the
body. **No LLM call** — this must not add a round-trip.

Add `Settings.page_digest_after_turns: int = 1` so the behaviour is switchable and A/B-able.

**Expected effect:** this is the largest untouched lever in the system. Do not predict a number —
section 2.4's cost model was already wrong by 7x because it modelled instead of measuring. Measure
it: the eval already reports `mean_input_tokens`.

**Falsifier:** if `answer_acc` drops, the digest is too lossy — lengthen it, or keep two pages in
full. Accuracy is the constraint; tokens are the objective.

---

## 7. EMBEDDING — it is a SHORTLISTER, not an answerer. Measured.

### 7.1 The 39.3% number does not mean what everyone thought

The leave-intent-out probe found dense top-1 page accuracy of **39.3%** on questions the ingest-time
generator never anticipated, and the conclusion drawn was "generated questions cannot cover the
question space, so the catalog is near-useless".

**That is a *precision* number being used to condemn a *recall* job.** A shortlister does not have to
be right on the first try. It only has to **keep the answer inside the top-k** and hand those k to
the LLM, which does the precision work — exactly the two-stage self-reduction then
contrastive-compare recipe of Lu et al. (ACL 2024, section 1.5).

Measured, free, on the real catalog (920 rows / 115 pages / 19 books / 6 shelves):

```
RECALL@k - PAGE level (the shortlist an LLM would receive)
regime      R@1     R@3     R@5    R@10    R@20
LOO       70.9%   92.1%   97.3%   99.8%  100.0%    paraphrase of an anticipated question
LOI       39.3%   65.8%   78.2%   90.7%   94.8%    an intent we NEVER anticipated  <-- the hard case

RECALL@k - BOOK level        MEAN-pool (centroid) vs MAX-pool
LOI  mean 54.1%   85.4%   94.0%   99.0%
LOI  max  62.1%   91.3%   97.1%   99.7%            <-- max wins everywhere

RECALL@k - SHELF level       MEAN-pool vs MAX-pool
LOI  mean 72.5%   99.5%  100.0%
LOI  max  80.9%   99.7%  100.0%
```

**Read the LOI row at R@10: 90.7%.** The same embeddings that answer correctly only 39.3% of the time
keep the right page inside a 10-item shortlist **90.7%** of the time — on questions nobody
anticipated. Embedding is a **bad oracle and a good sieve.** Use it as a sieve.

### 7.2 Use MAX-pooling, never the centroid

A container is a **union of topics, not one topic**. The centroid of a 5-topic shelf sits in empty
space, resembling nothing it holds. The right question is not *"is this shelf's average close to the
query"* but **"does this shelf CONTAIN anything close to the query"** — that is a max, not a mean.

Measured: at book level, LOI R@3 goes **85.4% (mean) -> 91.3% (max)**. At shelf level, R@1 goes
**72.5% -> 80.9%**. Use max-pooling over the subtree's page vectors. **Container vectors cost zero
new API calls** — they are pooled from page vectors already stored.

### 7.3 The limits, and how to handle each

| Limit | Evidence | Mitigation |
|---|---|---|
| **A shortlist is also a FILTER — it can hide the truth.** LOI R@10 = 90.7% means that for **9.3%** of unanticipated questions the right page falls *outside* the top-10. | measured above | **THE SHORTLIST MUST BE A HINT, NEVER A GATE.** See 7.4 — this is the same sin as `open_book`. |
| Dense retrieval misses **rare terms and named entities** (HNSW, BM25, ColBERT, SKU codes, Japanese retail terms) | well established; this corpus is full of them | **Hybrid**: add a SQLite **FTS5** index over question text + page titles + entity terms, fuse the two rankings (reciprocal rank fusion). Cheap; no new embedding cost. |
| **Vocabulary gap** — the reader's words are not the library's words. LOI R@1 collapses 70.9% -> 39.3%. | measured | **Entry vocabulary** (8.2) plus demand-side logging (8.4). |
| **Cosine score compression** (0.87-0.90) makes absolute thresholds meaningless | measured; already fixed with a margin gate | Irrelevant for shortlisting — **ranking is unaffected by compression.** Do not reintroduce a threshold here. |
| **Cold start** — a new page has no real queries yet | structural | Generated questions ARE the cold-start bootstrap. That is their real job; they were never meant to be the whole catalog. |
| **Small-corpus caveat** | 19 books, 6 shelves | Shelf-level R@3 = "3 of 6" is a weak test. **Do not extrapolate these numbers to 100k books.** The mechanism is standard ANN shortlisting; the numbers are not a proof at scale. |

### 7.4 The one rule that must not be broken

**A shortlist the librarian cannot escape is `open_book` all over again.**

The entire finding of Part I is that an *irreversible commitment made on partial information* is what
destroys routing. A hard embedding gate — "you may only look at these 5 shelves" — recommits exactly
that sin, and 9.3% of the time it would delete the answer from the universe.

So at a level too wide to render in full, show the shortlist **with an escape hatch**:

```
The card catalog suggests these 5 shelves (of 312):
  - ...
There are 307 more. Use browse_all() to see every shelf on this floor.
```

Reversible. The librarian may overrule the catalog. That is what makes it a *hint*.

### 7.5 Where this goes in the code

`ask_librarian` already exists and already has the margin gate. **Its role is wrong**: today it is a
shortcut *around* the walk. Its real job is to be the **shortlister inside the walk**, fired
automatically when a level exceeds `max_shelf_toc_entries` — not a tool the model has to remember to
call.

---

## 8. LIBRARIAN CRAFT — mechanisms buildable today

Ranked by value divided by effort. 8.1 costs nothing and can ship immediately.

### 8.1 SHELF-READING — the misshelved-item sweep (zero API calls) — BUILD FIRST

Librarians walk the stacks asking of each spine: *does this belong here?* The machine version: for
each page, rank every book by max-similarity over that book's **other** pages (leave-one-out), and
report the pages that fit a **different** book better than their own.

Run on the live library it produces:

```
SHELF-READING - 56 of 115 pages fit another book better than their own (49%)

d+0.078  "Labor Scheduling From Hourly and Daily Foot Traffic Patterns"
            filed in : Operational Insight      [Retail > Merchandising & Store Operations]
            fits best: KPI Interpretation       [Retail > KPIs & Performance Analytics]   CROSS-SHELF
d+0.062  "Inventory Issue Root Cause Analysis Framework"
            filed in : Root Cause Analysis      [Retail > KPIs & Performance Analytics]
            fits best: Inventory Management     [Retail > Inventory & Demand Planning]    CROSS-SHELF
d+0.050  "Sell Through Rate Definition Formula and Interpretation"
            filed in : KPI Dictionary           [Retail > KPIs & Performance Analytics]
            fits best: Seasonal Merchandise     [Retail > Inventory & Demand Planning]    CROSS-SHELF
```

**Now read what it is actually saying — because it is NOT "49% of the library is misfiled".**

Take *Inventory Turnover: Definition and Formula*, filed under `KPI Dictionary`, fitting `Inventory
Management` better. Which is right? **Both.** It is a KPI *definition* about *inventory*. It is a
two-faceted item, and a single-parent tree forces an arbitrary choice.

This is Ranganathan's argument against strict hierarchical classification, and the library world's
answer is not to move the book — it is **one physical location, many catalog access points** (added
entries / cross-references). LibraryKB already has the field: `NodeMeta.see_also`, currently manual
and unused.

**So the deliverable is NOT a move queue. It is a CROSS-LINK generator:**

1. `libkb probe-misshelved` — the report above, sorted by delta, cross-shelf flagged. Free.
2. **Auto-generate `see_also` edges** from it: when page P (in book A) strongly fits book B, add a
   cross-reference on **B** pointing at P. Zero LLM calls. The navigator's menu already renders
   `see_also` (`tools.py` `_render_menu`), so the walk picks the new links up for free.
3. **Only the extreme, mutually-stealing pairs are true merge candidates.** A *bidirectional* theft
   (section 1.2: `Root Cause Analysis` and `KPI Interpretation` stealing 19x and 14x from each other)
   means one book was split in two. Everything else is a facet, not a filing error.

Guard rails: (a) require delta above a floor **and** cross-shelf, or the report is noise; (b)
max-pooling favours books with more pages — normalise or cap; (c) the output is a **review queue**
and moves go through `_uncatalogued` review (P10). **Never auto-move.**

### 8.2 ENTRY VOCABULARY — the reader's words are not the library's words

`gen_questions.md` produces questions. It should also produce, per page, a small **term ring**:
synonyms, aliases, abbreviations and named entities, in vi + en — `USE / UF / RT` in thesaurus terms
(ISO 25964).

```
reranking - cross-encoder - re-rank - xep hang lai - ColBERT - MonoT5
```

Index those rows next to the questions (same table; add a `kind` column: `question | term`). They
cost nothing extra — same generation call — and they attack both measured weaknesses of dense
retrieval at once: the **vocabulary gap** (LOI 70.9% -> 39.3%) and **rare-entity misses**. Combined
with the FTS5 lexical index (7.3), this is the cheapest recall win available.

### 8.3 TRACE / pearl-growing — let the query evolve as the walk proceeds

Bates (1989): a real search is *berrypicking* — the query is **rewritten at every stop** using the
vocabulary just learned. LibraryKB freezes the query at t=0 and never revises it.

**New tool: `reframe(new_query, why)`.** After reading a page the librarian may restate the question
in the library's own language (the reader said *"why did sales drop"*; this shelf calls it
*"basket-size decline root-cause"*) and continue with the improved query.

Log both. The pair (reader's words -> library's words) is **exactly the entry-vocabulary training
data** that 8.2 wants, and it comes for free. Cheap, contained in `agent/tools.py`, and it directly
attacks the frozen-query weakness.

### 8.4 TRAJECTORY LOGGER — the flywheel that is actually missing

This answers the original worry: *"can ingest-time generated questions ever be enough?"* No — and
they were never supposed to be. **They are the cold start.** The library's real memory is the
questions it has actually been asked.

Log per query: `(reader's question -> path walked -> page landed on -> answerer's verdict)`. Then:

- **index the real questions.** Real query distributions are Zipf-shaped: you never cover the
  infinite tail, but the head is small and it can only be learned from traffic.
- **a successful walk becomes a pathfinder** — a curated route for a recurring question, replayed as
  a *hint* (never a gate — see 7.4).
- **a failed walk names the description that lied** — feed it to the view-regeneration queue.

An expert librarian's real edge is not that they memorised the collection. It is that **they remember
the questions.** The current flywheel spins on *content* (page -> guessed questions). This one spins
on *behaviour* (question -> route -> outcome -> better route). Only the second one compounds.

---

## 9. ORDER OF WORK

1. **8.1 `probe-misshelved` + auto `see_also`** — zero API cost, ships immediately, and the
   cross-links land in the menu the navigator already reads.
2. **6. page digest** — the largest cost lever in the system; no information loss by construction.
   Gate on `answer_acc` not dropping.
3. **7. shortlist** — wire `ask_librarian` as an *automatic, escapable* shortlister with max-pooling,
   plus the FTS5 hybrid. **Obey 7.4.**
4. **8.2 entry vocabulary** — folds into the next `reindex`.
5. **8.4 trajectory logger** — the real flywheel. Highest idea-value, most work.
6. **8.3 `reframe`** — cheap; do it whenever.

**Deferred indefinitely: `routing_mode="auto"`** (section 2.2 item 5). The A/B found **zero losses**
for route B, so there is no measured harm to hedge against. First check the per-case results: **how
many of the 30 cases even landed on a well-separated shelf** (`AI > LLM` 100%, `Merchandising`
92.7%)? If the answer is "one or two", then "0 losses" proves nothing about those shelves and `auto`
stays a live question. If it is "plenty", drop `auto` and spend the effort on 6-8.

**Do not build a fence around a cow nobody has seen.**

---

## 10. Reproducing the Part II measurements

All three are zero-API-call, reading only `library/_catalog/catalog.db`. Force UTF-8 (cp932 console,
D-012): `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe <script>`.

- **page/book/shelf token census** — iterate the store, count `len(markdown)//4`; that is where the
  196,320-token corpus figure and the 1,644-token median page come from.
- **recall@k** — for each catalog row, exclude it (LOO) or exclude both language variants of its
  generated intent (LOI), rank targets by max-similarity, and check whether the true target is in
  the top k. Do it at page, book and shelf level, and compare mean-pooling against max-pooling.
- **shelf-reading** — for each page, exclude its own rows, rank every book by max-similarity, and
  report pages whose best-fitting book is not their own. Flag cross-shelf. Count the book pairs that
  steal from each other in both directions.

Port all three into `libkb/evals/` next to `probe-separability`, and run them after every `reindex`.
They are the library's health check and they cost nothing.
