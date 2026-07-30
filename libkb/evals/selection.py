"""Does the AGENT choosing pages beat just taking the embedder's top-k? (the selection experiment)

This is the harness for the one question the whole "active seeker" thesis rests on. The measured
starting point is uncomfortable — probe 2c, MultiHop n=150:

    triage keeps  69% AllGold        the LLM chose the pages
    embedder top-10  75% AllGold     nobody chose anything

**The LLM selector LOSES to the sieve it was supposed to improve.** A cross-encoder reranker was the
obvious fix and it was measured and REFUTED (D-048: −5.2 to −9.0 R@1 — a strong embedder leaves a
reranker nothing to add). So the honest reading is not "AI selection does not work". It is that our
selector sits at the **single weakest configuration** the selection literature reports, on three
axes at once:

    pointwise      each candidate judged alone, never against the others
    binary         take / leave, with no account of what a page ADDS
    titles-only    ~59 tokens of section headings, mostly uninformative

Every comparative study ranks exactly that configuration last. This probe fixes one axis at a time
and measures, because *fixing all three and reporting one number is how you learn nothing*:

    embedder    top-k by cosine. NO LLM. The baseline that currently wins — beat this or stop.
    headers     the shipped triage: lean card, pointwise, binary.       (today)
    rich        the same call, richer card: several query-relevant passages + marked sections.
                                                                        (Tier 0 — fixes titles-only)
    set         set-selection: "which pages TOGETHER cover this?"       (Tier 2 — fixes pointwise
                Each pick states what it adds; `missing` names the hole.       AND binary)
    set+rich    both.
    read        the refuted cheap-reader selector (D-053), kept so the refutation reproduces.

**What is measured, and why these metrics.** Every arm sees the SAME candidate pool (embedded once,
cached, shared) — so a difference between arms is the selector and nothing else. Then:

    ceiling     the gold the POOL contained. No selector can exceed it. Bounds every column below.
    retention   of the gold that WAS in the pool, the fraction the selector kept.
                ← this is the number the thesis lives or dies on. 1.00 means the agent threw
                  nothing away; below the embedder arm means choosing actively made things worse.
    allgold     every gold document selected — what a correct multi-hop answer requires.
    coverage    the fraction of gold assembled.
    picked      how many pages the selector actually took (it under-fills: probe 2c saw ~4 of 10).

Retrieval-only: no answer is generated and no judge runs, so an arm costs ONE call per query and the
result is not confounded by the answerer. That is deliberate — selection is the thing under test.
"""

from __future__ import annotations

import json
import random
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path

import structlog

from libkb.catalog.store import Catalog, Hit
from libkb.concurrency import parallel_map
from libkb.config import Settings, get_settings
from libkb.evals import setsize
from libkb.evals.multihop import article_of_page
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

# arm name → (triage_mode, triage_card). An EMPTY mode marks a FREE arm: it makes no LLM call at
# all, `estimate()` prices it at zero, and `one()` below dispatches it by name. Three of them now —
# the embedder's fixed top-k, and the two set-SIZE selectors of `evals/setsize.py`, which choose how
# many pages to keep from the sieve's own scores because TP is 2-4 and varies while every selector
# measured so far commits to a near-constant 3.0-3.2.
ARMS: dict[str, tuple[str, str, bool]] = {
    "embedder": ("", "", False),
    "adaptive": ("", "", False),
    "conformal": ("", "", False),
    "headers": ("headers", "lean", False),
    "rich": ("headers", "rich", False),
    "rich+fill": ("headers", "rich", True),
    "set": ("set", "lean", False),
    "set+rich": ("set", "rich", False),
    "trace": ("trace", "lean", False),
    "trace+rich": ("trace", "rich", False),
    "agent": ("agent", "lean", False),
    "read": ("read", "lean", False),
}
DEFAULT_ARMS = ("embedder", "adaptive", "conformal", "headers", "rich", "rich+fill", "set", "agent")

# Arms that spend nothing. Kept as a set rather than inferred from an empty mode so that adding a
# paid arm can never make it free by accident.
FREE_ARMS = frozenset({"embedder", "adaptive", "conformal"})


@dataclass
class SelQuery:
    """A query whose GOLD is known — as a set of opaque keys. A key is whatever unit the dataset
    calls an answer-bearing document: a MultiHop article title, a FiQA doc id. The probe never looks
    inside one, so a new dataset is a loader, not a change here."""

    text: str
    kind: str
    gold: set[str]


@dataclass
class ArmRow:
    arm: str
    kind: str
    n: int = 0
    picked: float = 0.0
    hit: float = 0.0
    coverage: float = 0.0
    allgold: float = 0.0
    retention: float = 0.0
    ceiling: float = 0.0
    ceiling_allgold: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    empty: int = 0  # baskets the selector returned EMPTY — the D-035 failure, worth its own column
    # THE SET-vs-TP VIEW. `retention` gives partial credit and rewards taking more, which is how
    # the basket-size confound got in (metric bug 6.8). What the system actually needs is a
    # selection that CONTAINS the true-page set and carries little else:
    #   tp        how many documents genuinely hold the answer (2-4 here, never 1)
    #   taken     how many DISTINCT documents the selector committed to
    #   superset  the fraction of queries where selection ⊇ TP  (== allgold; the number that counts)
    #   overhead  documents taken that are NOT in TP — the acceptable trade-off, 1-2 is fine
    #   precision |selection ∩ TP| / |selection| — how much of the basket earned its place
    #   ctx_tokens the REAL cost: tokens of the pages the answerer must now read
    tp: float = 0.0
    taken: float = 0.0
    overhead: float = 0.0
    precision: float = 0.0
    ctx_tokens: float = 0.0
    # agent arm only: which tools it chose, per question kind. A score cannot say whether a
    # tool-using loop routed ADAPTIVELY; this can.
    tools: dict = field(default_factory=dict)


@dataclass
class Pools:
    """The shared candidate pools: one ranked list per query, embedded ONCE.

    Sharing them is not just a saving. If each arm re-ran the sieve, arms would differ by whatever
    the sieve did differently that run, and the experiment would measure noise."""

    queries: list[SelQuery]
    ranked: list[list[Hit]] = field(default_factory=list)
    fetch_n: int = 0
    basket: int = 0


# --------------------------------------------------------------------------- datasets


def load_multihop(
    root: Path | str, store: LibraryStore, *, limit: int | None = None, seed: int = 11
) -> tuple[list[SelQuery], dict[str, str]]:
    """MultiHop-RAG: gold is the set of ARTICLE titles the evidence came from, and a page is only a
    lead to its article (the splitter cuts one article into several pages). Sampled STRATIFIED by
    question type so a small run still carries comparison/temporal — the two kinds that genuinely
    need more than one document, and therefore the only ones set-selection can prove itself on."""
    rows = json.loads(Path(root, "MultiHopRAG.json").read_text(encoding="utf-8"))
    queries = [
        SelQuery(r["query"], r["question_type"], {e["title"] for e in r.get("evidence_list", [])})
        for r in rows
        if r.get("evidence_list")  # null_query has no evidence: it belongs to the honesty eval
    ]
    key_of = article_of_page(store, Path(root, "src"))
    return _stratify(queries, limit, seed), key_of


def _stratify(queries: list[SelQuery], limit: int | None, seed: int) -> list[SelQuery]:
    if not limit or limit >= len(queries):
        return queries
    rng = random.Random(seed)
    by_kind: dict[str, list[SelQuery]] = {}
    for q in queries:
        by_kind.setdefault(q.kind, []).append(q)
    out: list[SelQuery] = []
    for _, group in sorted(by_kind.items()):
        share = max(1, round(limit * len(group) / len(queries)))
        out += rng.sample(group, min(share, len(group)))
    rng.shuffle(out)
    return out[:limit]


# --------------------------------------------------------------------------- the run


def build_pools(
    queries: list[SelQuery],
    catalog: Catalog,
    *,
    llm: LLM | None = None,
    fetch_n: int,
    basket: int,
    progress=None,
) -> Pools:
    """Embed every query ONCE and cache its ranked candidates. The only embedding this probe spends,
    and the only thing every arm shares."""
    llm = llm or get_llm()
    if progress:
        progress(f"embedding {len(queries):,} queries (the only embedding cost)")
    vecs = llm.embed([q.text for q in queries], task="RETRIEVAL_QUERY")
    catalog.vectors()  # warm the matrix once, before any pool thread touches it
    ranked = [catalog.search(vec, top_k=fetch_n) for vec in vecs]
    return Pools(queries=queries, ranked=ranked, fetch_n=fetch_n, basket=basket)


def _page_tokens(page_ids: list[str], store: LibraryStore) -> float:
    """The context the answerer will actually have to read, in tokens.

    This is the number the whole selection layer exists to cut, and leaving it out is how the
    basket came to look free (metric bug 6.8). ~4 chars/token, the estimate used everywhere else."""
    total = 0
    for page_id in page_ids:
        try:
            total += len(store.page(page_id).markdown) // 4
        except Exception:  # a stale row must not break scoring
            continue
    return float(total)


def _keys(page_ids: list[str], key_of: dict[str, str]) -> list[str]:
    """page_ids → DISTINCT gold keys, in order. Several pages of one article are one document to a
    reader, and must be one to the score."""
    out: list[str] = []
    for page_id in page_ids:
        key = key_of.get(page_id)
        if key and key not in out:
            out.append(key)
    return out


def gold_ranks(pools: Pools, key_of: dict[str, str], i: int) -> list[int] | None:
    """Where this query's gold documents sit in its own ranked pool — the deepest one is what a
    score threshold would have to reach. None if any gold is absent from the pool (a sieve failure,
    already counted as `ceiling`; no threshold can repair it and letting it in would poison the
    calibration)."""
    batch = pools.ranked[i][: pools.fetch_n]
    ranks: list[int] = []
    for key in pools.queries[i].gold:
        rank = next((j for j, h in enumerate(batch) if key_of.get(h.page_id) == key), None)
        if rank is None:
            return None
        ranks.append(rank)
    return ranks


def conformal_thresholds(
    pools: Pools,
    key_of: dict[str, str],
    *,
    alpha: float = setsize.DEFAULT_ALPHA,
    folds: int = setsize.DEFAULT_FOLDS,
    seed: int = 11,
) -> list[float]:
    """A per-query score threshold, cross-fitted so no query is scored under a threshold it helped
    calibrate. The calibration target is the SET objective: the margin each query would have needed
    to keep ALL of its gold, so the certified quantity is `superset` itself."""
    required = [
        setsize.required_margin(
            [h.score for h in pools.ranked[i][: pools.fetch_n]], gold_ranks(pools, key_of, i) or []
        )
        for i in range(len(pools.queries))
    ]
    return setsize.cross_fit_thresholds(required, alpha=alpha, folds=folds, seed=seed)


def run_arm(
    arm: str,
    pools: Pools,
    *,
    store: LibraryStore,
    key_of: dict[str, str],
    llm: LLM | None = None,
    settings: Settings | None = None,
    workers: int | None = None,
    alpha: float = setsize.DEFAULT_ALPHA,
    buffer: int = setsize.DEFAULT_BUFFER,
    seed: int = 11,
    progress=None,
) -> list[ArmRow]:
    """One arm over every query. Runs whole-arm-at-a-time (not arm-inside-query) so the client's
    token counters give an EXACT per-arm bill even under a thread pool, where per-item deltas
    interleave into nonsense."""
    from libkb.agent.roles.librarian import selector_for

    llm = llm or get_llm()
    base = settings or get_settings()
    workers = base.eval_concurrency if workers is None else workers
    mode, card, fill = ARMS[arm]
    s = (
        base.model_copy(update={"triage_mode": mode, "triage_card": card, "triage_fill": fill})
        if mode
        else base
    )
    before = (llm.total_input_tokens, llm.total_output_tokens)
    # Calibrated ONCE for the whole arm, before any query is scored. Cheap (no model, no I/O) but it
    # reads gold labels, so it must never be computed inside `one()` where it would silently see the
    # query it is about to score.
    thresholds = (
        conformal_thresholds(pools, key_of, alpha=alpha, seed=seed)
        if arm == "conformal"
        else [0.0] * len(pools.queries)
    )

    def one(i: int) -> list[str] | None:
        """→ the page_ids this arm selected for query i."""
        batch = pools.ranked[i][: pools.fetch_n]
        if arm == "embedder":
            return [h.page_id for h in batch][: pools.basket]
        if arm == "adaptive":
            k = setsize.adaptive_k([h.score for h in batch], buffer=buffer)
            return [h.page_id for h in batch[:k]]
        if arm == "conformal":
            keep = setsize.conformal_keep([h.score for h in batch], thresholds[i])
            return [batch[j].page_id for j in keep]
        try:
            picked, _ = selector_for(mode)(
                pools.queries[i].text, batch, store, llm, s, pools.basket
            )
        except Exception as exc:
            # A selector that fails on one query costs one query. Returning an empty selection
            # would SCORE it as "the agent chose nothing", which is a claim about the mechanism —
            # a transport error is evidence of nothing, so the row is dropped instead (None).
            log.warning(
                "arm_failed", arm=arm, query=pools.queries[i].text[:60], error=str(exc)[:120]
            )
            return None
        return [item.page_id for item in picked]

    def note(done: int, total: int) -> None:
        if progress and done % 10 == 0:
            progress(f"  {arm}: {done}/{total}")

    # TOOL TELEMETRY (the adaptive-routing question). A score says which arm won on average; it
    # cannot say whether the agent picked the RIGHT tool for THIS question — which is the only
    # thing a tool-using loop is for. `trace` scoring worst while applying its tool to every query
    # is the warning: a tool used unconditionally is not adaptive, it is just overhead.
    tools_by_kind: dict[str, dict[str, int]] = {}
    if arm == "agent":
        import libkb.agent.poolagent as pa

        lock = threading.Lock()
        kind_of = {q.text: q.kind for q in pools.queries}

        def _observe(result, query: str) -> None:
            with lock:
                bucket = tools_by_kind.setdefault(kind_of.get(query, "?"), {})
                for name in result.tool_calls:
                    bucket[name] = bucket.get(name, 0) + 1
                if result.budget.exhausted:
                    bucket["(budget:" + result.budget.exhausted + ")"] = (
                        bucket.get("(budget:" + result.budget.exhausted + ")", 0) + 1
                    )

        pa.OBSERVER = _observe

    try:
        selections = parallel_map(
            one, list(range(len(pools.queries))), workers=workers, progress=note
        )
    finally:
        if arm == "agent":
            import libkb.agent.poolagent as pa

            pa.OBSERVER = None
    calls = 0 if arm in FREE_ARMS else sum(1 for sel in selections if sel is not None)

    kinds = ["all", *sorted({q.kind for q in pools.queries})]
    acc: dict[str, dict[str, float]] = {
        k: dict.fromkeys(
            # fmt: off
            (
                "n",
                "picked",
                "hit",
                "cov",
                "all",
                "ret",
                "ret_n",
                "ceil",
                "ceil_all",
                "empty",
                "tp",
                "taken",
                "over",
                "prec",
                "ctx",
            ),
            # fmt: on
            0.0,
        )
        for k in kinds
    }

    for i, selected in enumerate(selections):
        if selected is None:
            continue
        query = pools.queries[i]
        pool_keys = set(_keys([h.page_id for h in pools.ranked[i]], key_of))
        taken_keys = set(_keys(selected, key_of))
        got = taken_keys & query.gold
        reachable = pool_keys & query.gold  # the ceiling THIS query's pool allows
        # The basket is NOT free: these are the tokens the answerer must now read, and cutting them
        # is the entire product value of selecting well. Counted on the pages actually committed.
        ctx = _page_tokens(selected, store) if store is not None else 0.0
        for kind in ("all", query.kind):
            cell = acc[kind]
            cell["n"] += 1
            cell["picked"] += len(selected)
            cell["empty"] += 1.0 if not selected else 0.0
            cell["hit"] += 1.0 if got else 0.0
            cell["cov"] += len(got) / len(query.gold)
            cell["all"] += 1.0 if got == query.gold else 0.0
            cell["ceil"] += len(reachable) / len(query.gold)
            cell["ceil_all"] += 1.0 if reachable == query.gold else 0.0
            # the set-vs-TP view: did the selection CONTAIN the true pages, and what did it carry
            # along? Overhead of one or two is a fine trade; missing one TP is not.
            cell["tp"] += len(query.gold)
            cell["taken"] += len(taken_keys)
            cell["over"] += len(taken_keys - query.gold)
            cell["prec"] += len(got) / max(len(taken_keys), 1)
            cell["ctx"] += ctx
            if reachable:  # retention is undefined when the pool held no gold — do not score it
                cell["ret"] += len(got) / len(reachable)
                cell["ret_n"] += 1

    rows: list[ArmRow] = []
    for kind in kinds:
        cell = acc[kind]
        n = max(int(cell["n"]), 1)
        rows.append(
            ArmRow(
                arm=arm,
                kind=kind,
                n=int(cell["n"]),
                picked=cell["picked"] / n,
                hit=cell["hit"] / n,
                coverage=cell["cov"] / n,
                allgold=cell["all"] / n,
                retention=cell["ret"] / max(int(cell["ret_n"]), 1),
                ceiling=cell["ceil"] / n,
                ceiling_allgold=cell["ceil_all"] / n,
                empty=int(cell["empty"]),
                tp=cell["tp"] / n,
                taken=cell["taken"] / n,
                overhead=cell["over"] / n,
                precision=cell["prec"] / n,
                ctx_tokens=cell["ctx"] / n,
                tools=tools_by_kind if kind == "all" else {},
                calls=calls if kind == "all" else 0,
                input_tokens=(llm.total_input_tokens - before[0]) if kind == "all" else 0,
                output_tokens=(llm.total_output_tokens - before[1]) if kind == "all" else 0,
            )
        )
    return rows


def run(
    pools: Pools,
    *,
    store: LibraryStore,
    key_of: dict[str, str],
    arms: tuple[str, ...] = DEFAULT_ARMS,
    llm: LLM | None = None,
    settings: Settings | None = None,
    workers: int | None = None,
    alpha: float = setsize.DEFAULT_ALPHA,
    buffer: int = setsize.DEFAULT_BUFFER,
    seed: int = 11,
    progress=None,
) -> list[ArmRow]:
    out: list[ArmRow] = []
    for arm in arms:
        if progress:
            progress(f"arm {arm}")
        out += run_arm(
            arm,
            pools,
            store=store,
            key_of=key_of,
            llm=llm,
            settings=settings,
            workers=workers,
            alpha=alpha,
            buffer=buffer,
            seed=seed,
            progress=progress,
        )
    return out


def matched_control(
    taken: float,
    pools: Pools,
    *,
    store: LibraryStore,
    key_of: dict[str, str],
    llm: LLM | None = None,
    settings: Settings | None = None,
    workers: int | None = None,
) -> ArmRow | None:
    """`embedder` re-run at whatever fixed basket makes it commit to the SAME NUMBER OF DOCUMENTS —
    the control an adaptive arm has to beat before its adaptivity has been shown to do anything.

    This exists as code, not as advice, because the advice was already written down and the project
    still spent several sessions on a conclusion that was a basket-size artefact (metric bug 6.8).

    **The basket is measured in PAGES and `taken` in DOCUMENTS**, and they are not the same number —
    the splitter cuts one article into several pages, so a basket of 7 pages commits to about 5
    documents. Matching one to the other is the same category error the rule exists to prevent, so
    the basket is SEARCHED for: `taken` is monotone in it, which makes a bisection exact and cheap.
    Free either way: no model call, ~6 passes over pools already in memory.
    """
    target = max(1.0, taken)
    cache: dict[int, ArmRow | None] = {}

    def at(k: int) -> ArmRow | None:
        if k not in cache:
            rows = run_arm(
                "embedder",
                replace(pools, basket=k),
                store=store,
                key_of=key_of,
                llm=llm,
                settings=settings,
                workers=workers,
            )
            cache[k] = next((r for r in rows if r.kind == "all"), None)
        return cache[k]

    lo, hi = 1, max(1, pools.fetch_n)
    best: tuple[int, ArmRow] | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        row = at(mid)
        if row is None:
            break
        if best is None or abs(row.taken - target) < abs(best[1].taken - target):
            best = (mid, row)
        if row.taken < target:
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    k, row = best
    row.arm = f"embedder@{k}"
    return row


# --------------------------------------------------------------------------- the preflight


@dataclass
class Estimate:
    arm: str
    calls: int
    input_tokens: int
    card_chars: int


def estimate(
    pools: Pools,
    *,
    store: LibraryStore,
    arms: tuple[str, ...],
    settings: Settings | None = None,
    sample: int = 3,
) -> list[Estimate]:
    """What the full run WILL cost, measured from real cards on a few queries — no generation call.

    The rule this exists for: **always price a run on a handful before paying for all of it.** The
    cards are built by the same code the run uses, so the estimate is the real prompt size and not a
    guess; only the extrapolation to `n` is an assumption, and it is a linear one.
    """
    from libkb.agent.cascade import _cards

    base = settings or get_settings()
    n = len(pools.queries)
    out: list[Estimate] = []
    for arm in arms:
        mode, card, fill = ARMS[arm]
        if not mode:  # embedder / adaptive / conformal — scores only, nothing is generated
            out.append(Estimate(arm, 0, 0, 0))
            continue
        s = base.model_copy(update={"triage_mode": mode, "triage_card": card, "triage_fill": fill})
        if mode == "agent":
            # The pool agent is a LOOP, not one call, and a preflight that prices it as one call is
            # worse than no preflight — it under-reports the only arm that can run away with the
            # bill. Price the ceiling the budget actually allows: `max_steps` turns whose context
            # grows by roughly one tool result each, plus the close-out, plus the lite consults.
            # Its prompt carries PATHS only (the tools fetch bodies), so the base is small.
            paths = (
                sum(len(store.path_str(h.page_id)) for h in pools.ranked[0][: pools.fetch_n])
                if n
                else 0
            )
            steps = s.pool_max_steps + 1
            per_call = paths // 4 + 700
            out.append(
                Estimate(
                    arm,
                    n * steps,
                    n * (steps * (steps + 1) // 2) * per_call // 2
                    + n * s.pool_max_lite_calls * (s.pool_ask_chars // 4),
                    paths,
                )
            )
            continue
        if mode == "read":
            # the `read` selector's prompt is bounded by construction, not by the cards
            chars = s.triage_read_n * s.triage_read_chars
        else:
            widths = [
                len(
                    "\n\n".join(
                        _cards(pools.queries[i].text, pools.ranked[i][: pools.fetch_n], store, s)[0]
                    )
                )
                for i in range(min(sample, n))
            ]
            chars = int(sum(widths) / max(len(widths), 1))
        # ~4 chars/token, + the prompt scaffold (instructions, question, JSON shape) ≈ 700 tokens.
        out.append(Estimate(arm, n, n * (chars // 4 + 700), chars))
    return out
