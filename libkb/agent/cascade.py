"""Retrieval as a CASCADE, not a walk (docs/RETRIEVAL_REDESIGN.md).

The diagnosis, in one line: **we were using the LLM as the sieve. It should be the oracle.**

Our own numbers said so all along. The embedder is a bad oracle (top-1 39.3% on an intent nobody
anticipated) and a good sieve (the right page is in its top-10 **90.7%** of the time; on realistic
reader phrasing, in its top-3 **96.7%** of the time — exactly what the 13-call walk achieves). The
LLM is the reverse: superb on a handful of candidates, and ruinous at ~2–5k tokens *per call*.

So the walk had it backwards. It spent 9–13 LLM calls sifting, and each call resent the entire
conversation — **O(T²)**. MEASURED: a walk sees 8,601 tokens of distinct information and we pay
**45,268** for it. Four fifths of the bill is rent on things already seen.

    ① PROPOSE   0 LLM calls   embed the question, rank every page, take top N
    ② TRIAGE    1 LLM call    the librarian sees PATHS + descriptions + SECTION HEADERS only
                              (~59 tokens/page, not 1,571) and fills a BASKET
    ③ ANSWER    1 LLM call    the basket is opened ONCE: the chosen SECTIONS → cited answer
    ④ EXPAND    only if the answerer says the evidence was insufficient — pop the next
                candidates (free; they were already scored) and answer once more

The basket is the point, and it is not a compression trick. Text in the *navigator's conversation*
is resent every turn (billed T times); text in the *answerer's call* is billed exactly once. So the
full page must never enter the conversation at all. Not read-then-shrink (we tried that — the page
digest — and it cost +17%, because the librarian, robbed of the text, read *more*). **Don't read.**

No diversification, and that is measured, not assumed: NMS costs **10 points of recall** on this
corpus (96.7% → 86.7%) because it suppresses the right page for being *similar to* a good one — and
that similarity was corroboration. See §4.2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from libkb.agent.answerer import Answer, compose_not_found
from libkb.agent.navigator import NavResult
from libkb.agent.pooltools import coverage_map, render_coverage
from libkb.agent.roles.registry import get_registry
from libkb.agent.tools import NavEvent
from libkb.catalog.search import lookup
from libkb.catalog.store import Catalog, Hit
from libkb.config import Settings, get_settings
from libkb.exceptions import NodeNotFound
from libkb.library.models import PageContent, one_line_of
from libkb.library.sections import (
    pick_sections,
    query_passages,
    relevant_sections,
    section_index,
)
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        # A one-line first-person "thought" the model narrates with its pick (D-061). It rides on a
        # call we already make (near-free); not required, so a model that omits it fails open.
        "thought": {"type": "string"},
        "basket": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "string"},
                    "sections": {"type": "array", "items": {"type": "string"}},
                    "why": {"type": "string"},
                },
                "required": ["page"],
            },
        },
        "note": {"type": "string"},
    },
    "required": ["basket"],
}


@dataclass
class BasketItem:
    page_id: str
    path: str
    sections: list[str]
    why: str = ""


@dataclass
class CascadeResult:
    answer: Answer
    nav: NavResult  # the same shape the walk returns, so every caller and the eval work unchanged
    basket: list[BasketItem] = field(default_factory=list)
    rounds: int = 1


def answer_by_cascade(
    query: str,
    *,
    store: LibraryStore,
    catalog: Catalog,
    llm: LLM | None = None,
    event_cb: EventCB | None = None,
    settings: Settings | None = None,
) -> CascadeResult:
    llm = llm or get_llm()
    s = settings or get_settings()
    events: list[NavEvent] = []

    def emit(event: NavEvent) -> None:
        events.append(event)
        if event_cb:
            event_cb(event)

    # Resolve the retrieval-depth dials for THIS corpus (D-058): 'auto' turns the catalog page count
    # into a concrete (window, basket). A big basket on a small library was the token p90 blow-out.
    fetch_n, k, max_pages = s.resolve_cascade(len(catalog.page_ids()))

    # Roles are resolved from the registry (D-061, Phase B), not hardcoded — the triage and answer
    # implementations are swappable, and a new agent plugs in by registering, not by editing here.
    reg = get_registry()
    librarian = reg.get("librarian")
    answerer = reg.get("answerer")

    # ① PROPOSE — free. No gate, no threshold: this is a sieve, and a sieve is allowed to be unsure.
    ranked = lookup(catalog, query, llm=llm, top_k=fetch_n)
    if not ranked:
        emit(NavEvent("lookup", "card catalog", None, None, "notfound", detail="no candidates"))
        return _nothing(query, events, [])
    emit(
        NavEvent(
            "lookup",
            "card catalog",
            None,
            None,
            "done",
            detail=f"{len(ranked)} candidates ranked",
        )
    )

    seen: set[str] = set()
    basket: list[BasketItem] = []
    pages: list[PageContent] = []
    answer: Answer | None = None
    rounds = 0

    for round_no in range(1, s.cascade_max_rounds + 1):
        batch = [h for h in ranked if h.page_id not in seen][:k]
        if not batch:
            break
        seen.update(h.page_id for h in batch)
        rounds = round_no

        # ② TRIAGE — pick the basket. Three mechanisms, resolved by `triage_mode` in the librarian
        # role: the shipped `headers` triage (strong model, one call over the candidate cards);
        # `read` (a cheap subagent reads the top-N bodies — REFUTED, D-053); and `set` (D-064), the
        # same one call asked for a covering SET rather than page-by-page relevance. What each of
        # them SEES is the other dial, `triage_card` — see `build_card`. Both are measured by
        # `libkb probe-selection`, because the diagnostic (backlog 2c) found this step keeps only
        # 69% of the gold the sieve had already found.
        picked, triage_thought = librarian.triage(query, batch, store, llm, s, max_pages)
        for item in picked:
            emit(
                NavEvent(
                    "triage",
                    item.path.split(" ▸ ")[-1],
                    "page",
                    item.page_id,
                    "done",
                    detail=item.why,
                    snippet=", ".join(item.sections) or "(whole page)",
                )
            )
        # The librarian thinking aloud (D-061) — the model's own first-person line, shown in the UI.
        if triage_thought:
            emit(NavEvent("thought", triage_thought, None, None, "done", detail="triage"))
        if not picked:
            continue  # nothing here — go round again with the next candidates

        # ③ ANSWER — the basket is opened once. Sections, not whole pages.
        basket += picked
        opened = _open_basket(picked, store, s)
        pages += opened
        if not pages:
            continue
        # Narrate the MIDDLE of the process (D-061): opening pages and drafting are real phases that
        # used to run silently between TRIAGE and FOUND. Emit them so the timeline shows the full
        # walk — and so "drafting" is the ACTIVE line during the (blocking) answer call.
        emit(
            NavEvent(
                "read",
                "reading the chosen pages",
                None,
                None,
                "read",
                detail=f"{len(opened)} page(s) opened",
            )
        )
        emit(NavEvent("compose", "drafting the answer", None, None, "walking"))
        answer = answerer.compose(query, pages, store, llm=llm, settings=s)
        if answer.status == "answered":
            if answer.thought:
                emit(NavEvent("thought", answer.thought, None, None, "done", detail="answer"))
            emit(NavEvent("found", "FOUND", None, None, "found", detail=f"round {round_no}"))
            break

        # ④ INSUFFICIENT. Before widening, ask the cheaper question: **was it the wrong page, or
        # the wrong PART of the right page?** The librarian chose sections from a list of titles;
        # a title can easily hide the paragraph that answers. Re-opening what we already have costs
        # one call and no search, and the sieve is usually right — in every one of the four cases
        # this architecture lost, it had ranked the target page **#1** (D-035).
        # Only if the page IN FULL still does not answer do we go looking elsewhere.
        if any(item.sections for item in picked):
            emit(
                NavEvent(
                    "expand",
                    "re-opening the same pages in full",
                    None,
                    None,
                    "walking",
                    detail="right page, wrong section?",
                )
            )
            widened = _open_basket(
                [BasketItem(i.page_id, i.path, [], i.why) for i in picked], store, s
            )
            emit(NavEvent("compose", "re-reading in full and drafting", None, None, "walking"))
            answer = answerer.compose(query, widened, store, llm=llm, settings=s)
            if answer.status == "answered":
                pages = pages[: -len(picked)] + widened  # cite the full pages we actually used
                emit(NavEvent("found", "FOUND", None, None, "found", detail="on the second look"))
                break

        # Still nothing. NOW widen to candidates we have not seen — free; they were ranked in ①.
        emit(
            NavEvent(
                "expand",
                "insufficient evidence",
                None,
                None,
                "walking",
                detail=f"round {round_no} → new candidates",
            )
        )
        answer = None

    # ⑤ LAST RESORT. **A librarian may not declare the library empty while the closest pages sit
    # unread on his desk.** MEASURED, and it is damning: of the three queries this cascade gave up
    # on, TWO had already reached the exact target page — the sieve found it, the triage basketed
    # it, and the answerer still said "insufficient" because it was handed one page where the walk
    # would have handed it three (the walk's found_rate is 100%, ours was 90%).
    # So before any NOT_FOUND: open the top candidates IN FULL and let the answerer look once more.
    # It costs one call on the ~10% of queries that get here, and the sieve's top-3 contains the
    # answer 96.7% of the time. Only if THAT is insufficient is the not-found honest (P6).
    if answer is None or not pages:
        fallback = _open_basket(
            [
                BasketItem(h.page_id, store.path_str(h.page_id), [], "last resort")
                for h in ranked[:max_pages]
            ],
            store,
            s,
        )
        if fallback:
            emit(
                NavEvent(
                    "expand",
                    "reading the closest pages in full",
                    None,
                    None,
                    "walking",
                    detail="before declaring the library does not hold this",
                )
            )
            emit(NavEvent("compose", "drafting from the closest pages", None, None, "walking"))
            last = answerer.compose(query, fallback, store, llm=llm, settings=s)
            if last.status == "answered":
                emit(NavEvent("found", "FOUND", None, None, "found", detail="last resort"))
                answer, pages = last, fallback
                basket = basket or [
                    BasketItem(p.page_id, store.path_str(p.page_id), [], "last resort")
                    for p in fallback
                ]

    if answer is None or not pages:
        return _nothing(query, events, [store.path_str(h.page_id) for h in ranked[:k]], rounds)

    nav = NavResult(
        status="FOUND",
        pages=pages,
        # `hops` and `backtracks` keep their meaning for the eval and the trace: a hop is a page the
        # librarian committed to; a "backtrack" is a round he had to widen because the last one did
        # not answer. Both are now bounded by construction — that is the whole point.
        hops=len(basket),
        backtracks=rounds - 1,
        reason="cascade",
        events=events,
        resolved_fetch=fetch_n,
        resolved_basket=max_pages,
    )
    log.info(
        "cascade_done",
        basket=len(basket),
        pages=len(pages),
        rounds=rounds,
        fetch_n=fetch_n,
        max_pages=max_pages,
    )
    return CascadeResult(answer=answer, nav=nav, basket=basket, rounds=rounds)


def build_card(
    query: str, hit: Hit, page: PageContent, one_line: str, path: str, s: Settings
) -> str:
    """The candidate card the selector actually judges — the ONE artefact that decides what the
    librarian knows about a page before choosing it. Two shapes, one dial (`triage_card`):

    **lean** (shipped, MEASURED) — the matched catalog row *or* one query-relevant passage, the
    spine label, and the bare section titles. ~59 tokens.

    **rich** (Tier 0) — the same, plus: the passage is shown *even when* the catalog row matched
    (they answer different questions — "what is this page for" vs "what does it say about YOUR
    question"; the lean card makes them mutually exclusive for no reason), *several* passages
    instead of one, and the section titles that actually overlap the query are MARKED.

    Why this and not a reranker: the reranker was measured and refuted (D-048) — a strong embedder
    leaves nothing to out-rank. This does not re-order anything. It attacks the other axis: the
    selector was choosing on ~59 tokens of mostly-uninformative titles, which is the single weakest
    selector configuration the reranking literature reports. Anthropic's Contextual Retrieval is the
    same move at index time (context prepended before embedding, −35% retrieval failures); this is
    its query-time, zero-LLM cousin. Cost is tokens on ONE call, and no generation at all.
    """
    rich = s.triage_card == "rich"
    card = [f"### {path}"]
    # The strongest signal we have, and it was going to waste: the catalog row that MATCHED.
    # It says what this page is FOR, phrased the way a reader would ask — far more informative
    # than a terse section title. Without it, triage was returning an empty basket on pages the
    # sieve had ranked #1 (D-035).
    if hit.text:
        card.append(f'Answers questions like: "{hit.text}"')
    # A TEXT index stores an empty display text, so the line above never fires and triage was left
    # with only the spine label + section titles — the sieve's REASON for ranking this page
    # discarded exactly where the librarian chooses. Show the passage(s) that most overlap the
    # query: model-free, computed from the body we already fetched (D-050).
    if rich or not hit.text:
        passages = query_passages(
            page.markdown,
            query,
            k=s.triage_passages if rich else 1,
            max_chars=s.triage_snippet_chars,
        )
        for i, passage in enumerate(passages):
            card.append(f'Relevant passage: "{passage}"' if i == 0 else f'  also: "{passage}"')
    if one_line:
        card.append(f"About: {one_line}")
    titles = section_index(page.markdown)
    if not titles:
        card.append("Sections: (none — ask for the whole page)")
        return "\n".join(card)
    # Marking is the second half of the Tier-0 lever. `3.2 Analysis` is a title that says nothing,
    # and the librarian is asked to copy one back EXACTLY; without a reason to prefer one it either
    # guesses or asks for the whole page. The mark is computed from the section BODY, so it is a
    # fact about the page, not a hint from the model.
    marked = set(relevant_sections(page.markdown, query, k=3)) if rich else set()
    card.append("Sections:" + (" (▸ = its text overlaps your question)" if marked else ""))
    card += [f"  {'▸' if t in marked else '-'} {t}" for t in titles]
    return "\n".join(card)


def _fill_block(llm: LLM, s: Settings) -> str:
    """The anti-under-fill instruction, or nothing (D-069).

    MEASURED: every selector may take 20 pages and takes 3-4, and retention tracks pages-taken
    almost perfectly across arms — so the defect is under-filling, not mis-picking. Kept behind a
    dial rather than written into the prompt because the shipped prompt IS the measured baseline,
    and a baseline that quietly changes is one you can no longer compare against."""
    return ("\n" + llm.load_prompt("triage_fill")) if s.triage_fill else ""


def _cards(
    query: str, batch: list[Hit], store: LibraryStore, s: Settings
) -> tuple[list[str], dict[str, str]]:
    """Cards for a whole candidate batch + the path→page_id map used to resolve the model's picks.
    Shared by every card-based selector so they are compared on IDENTICAL evidence."""
    cards: list[str] = []
    by_path: dict[str, str] = {}
    for hit in batch:
        try:
            page = store.page(hit.page_id)
            entry = store.toc_entry(hit.page_id)
        except NodeNotFound:
            continue  # a stale catalog row must not break a query
        path = store.path_str(hit.page_id)
        by_path[path] = hit.page_id
        spine = one_line_of(entry.one_line, s.max_one_line_chars) if entry.one_line else ""
        cards.append(build_card(query, hit, page, spine, path, s))
    return cards, by_path


def _triage(
    query: str, batch: list[Hit], store: LibraryStore, llm: LLM, s: Settings, max_pages: int
) -> tuple[list[BasketItem], str]:
    """One LLM call over section headers. This is the ONLY place a page is chosen.

    Returns the basket AND the model's one-line first-person `thought` (D-061) shown in the UI."""
    cards, by_path = _cards(query, batch, store, s)
    if not cards:
        return [], ""

    # Coverage-aware SELECTION (D-051): a multi-part question needs a page for EACH part, not ten
    # variations of its most obvious half. The instruction lives in its own prompt file (prompts are
    # files) and is injected only when the dial is on — off = the plain best-first prompt, the A/B
    # baseline. It is adaptive by design: the LLM applies it only to questions that name >1 part.
    coverage = llm.load_prompt("triage_coverage") if s.triage_coverage else ""
    prompt = llm.load_prompt(
        "triage",
        query=query,
        candidates="\n\n".join(cards),
        max_pages=max_pages,
        coverage=coverage,
        fill=_fill_block(llm, s),
    )
    data = llm.generate_json(prompt, schema=TRIAGE_SCHEMA)

    out: list[BasketItem] = []
    # `basket` is REQUIRED by the schema, but a required key can still arrive with the value `null`
    # — Qwen returns `{"basket": null}` to mean "nothing here is relevant", and `.get("basket", [])`
    # then yields None, not the default (the key IS present). Slicing None threw. `or []` treats a
    # null basket as an empty one — an empty round, which the caller already handles. Showed up
    # under fetch=50: a 50-candidate triage prompt makes "I pick nothing" a more frequent answer.
    for row in (data.get("basket") or [])[:max_pages]:
        path = str(row.get("page", "")).strip()
        page_id = by_path.get(path) or _fuzzy_path(path, by_path)
        if page_id is None:
            continue
        out.append(
            BasketItem(
                page_id=page_id,
                path=store.path_str(page_id),
                sections=[str(x) for x in (row.get("sections") or [])],
                why=str(row.get("why", "")).strip(),
            )
        )
    return out, str(data.get("thought") or "").strip()


_SET_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "string"},
                    "sections": {"type": "array", "items": {"type": "string"}},
                    "contributes": {"type": "string"},
                },
                "required": ["page"],
            },
        },
        # What the question asks for that NO candidate covers. Not decoration: it is the honest
        # signal the widen/last-resort path is for, and it is free on a call we already make.
        "missing": {"type": "string"},
    },
    "required": ["selected"],
}


def _triage_set(
    query: str, batch: list[Hit], store: LibraryStore, llm: LLM, s: Settings, max_pages: int
) -> tuple[list[BasketItem], str]:
    """SET-SELECTION: one call over the SAME cards as `_triage`, but a different QUESTION asked of
    the model — *"which pages, TOGETHER, cover this question?"* rather than *"is this page
    relevant?"*, asked of one page at a time.

    Why this is the D-048-safe move. The refuted reranker tried to out-RANK a strong embedder and
    had nothing to add. This does not rank. It optimises **coverage of a set**, which is the metric
    a multi-source answer actually needs (AllGold, not R@1) and which no similarity function can
    express: cosine cannot know that page B is worth taking *because* page A left a hole. That makes
    it a different objective, not a better scorer — so D-048's mechanism ("a strong first stage
    leaves a reranker nothing to add") simply does not reach it.

    It also removes, in one change, the two axes that put the current triage at the weakest
    configuration in the selection literature: it is COMPARATIVE (candidates are judged against each
    other, not in isolation) and it is not a binary take/leave (each pick must state what it
    contributes that the others do not). `missing` is the third thing it buys — an explicit "nothing
    here covers X", which is exactly the signal the widen round needs and currently has to infer.

    Section naming is KEPT (unlike the refuted `read` selector, D-053, which picked whole pages and
    short-circuited the last-resort net the accuracy actually rides on).
    """
    cards, by_path = _cards(query, batch, store, s)
    if not cards:
        return [], ""

    prompt = llm.load_prompt(
        "select_set",
        query=query,
        candidates="\n\n".join(cards),
        max_pages=max_pages,
        tools="",
        fill=_fill_block(llm, s),
    )
    data = llm.generate_json(prompt, schema=_SET_SCHEMA)
    return _resolve_set(data, by_path, store, max_pages)


def _resolve_set(
    data: dict, by_path: dict[str, str], store: LibraryStore, max_pages: int
) -> tuple[list[BasketItem], str]:
    """A set-selection reply → the basket. Shared by every set-shaped selector so the arms differ
    by what they were TOLD, never by how their answer was parsed."""
    out: list[BasketItem] = []
    seen: set[str] = set()
    for row in (data.get("selected") or [])[:max_pages]:
        path = str(row.get("page", "")).strip()
        page_id = by_path.get(path) or _fuzzy_path(path, by_path)
        if page_id is None or page_id in seen:
            continue
        seen.add(page_id)
        out.append(
            BasketItem(
                page_id=page_id,
                path=store.path_str(page_id),
                sections=[str(x) for x in (row.get("sections") or [])],
                why=str(row.get("contributes", "")).strip(),
            )
        )
    thought = str(data.get("thought") or "").strip()
    missing = str(data.get("missing") or "").strip()
    if missing:
        thought = f"{thought} (still missing: {missing})".strip()
    return out, thought


def _triage_trace(
    query: str, batch: list[Hit], store: LibraryStore, llm: LLM, s: Settings, max_pages: int
) -> tuple[list[BasketItem], str]:
    """SET-SELECTION, with a TOOL RESULT in hand (D-066): before choosing, the coverage map is
    computed over the pool and handed to the model.

    The difference from `_triage_set` is one block of text and zero extra calls. That block is not
    another model's opinion — it is arithmetic over the page bodies: *the question has these three
    parts; page A covers 1 and 3; page B covers 2; nothing covers part 4.* The selector stops having
    to infer coverage from titles and starts being told it.

    This is the shape every method takes from here (D-066): a tool that answers, over the 50–100
    candidates the sieve already proposed, a question the agent would otherwise guess at.
    """
    cards, by_path = _cards(query, batch, store, s)
    if not cards:
        return [], ""

    pages: list[tuple[str, str, str]] = []
    for path, page_id in by_path.items():
        try:
            pages.append((page_id, path, store.page(page_id).markdown))
        except NodeNotFound:
            continue
    coverage = coverage_map(query, pages)

    prompt = llm.load_prompt(
        "select_set",
        query=query,
        candidates="\n\n".join(cards),
        max_pages=max_pages,
        tools=render_coverage(coverage),
        fill=_fill_block(llm, s),
    )
    data = llm.generate_json(prompt, schema=_SET_SCHEMA)
    return _resolve_set(data, by_path, store, max_pages)


def _triage_agent(
    query: str, batch: list[Hit], store: LibraryStore, llm: LLM, s: Settings, max_pages: int
) -> tuple[list[BasketItem], str]:
    """The pool agent (D-067): the librarian is given TOOLS over the candidates and decides for
    itself what to check before committing. See `agent/poolagent.py` for the loop and its budgets.

    **Falls back to the shipped triage when the loop selects nothing.** An agent that spends its
    budget and learns nothing must not also cost the reader the answer — that is the D-035 failure
    (an empty basket on pages the sieve had ranked #1) with extra steps.
    """
    from libkb.agent.poolagent import PoolAgent

    result = PoolAgent(query, batch, store, llm, s, max_pages).run()
    if not result.selected:
        log.info("pool_agent_empty_falling_back", exhausted=result.budget.exhausted or None)
        return _triage(query, batch, store, llm, s, max_pages)

    thought = result.thought
    if result.missing:
        thought = f"{thought} (still missing: {result.missing})".strip()
    return [
        BasketItem(
            page_id=sel.page_id,
            path=store.path_str(sel.page_id),
            sections=sel.sections,
            why=sel.why,
        )
        for sel in result.selected
    ], thought


_SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "needed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"doc": {"type": "integer"}, "why": {"type": "string"}},
                "required": ["doc"],
            },
        }
    },
    "required": ["needed"],
}


def _triage_read(
    query: str, batch: list[Hit], store: LibraryStore, llm: LLM, s: Settings, max_pages: int
) -> tuple[list[BasketItem], str]:
    """SELECTION by READING (D-053): a cheap subagent reads the top-N candidate BODIES and names the
    documents the answerer needs. Contrast with `_triage`, which reads only section titles on the
    strong model — the diagnostic showed that drops 24 pts of gold on multi-source questions.

    The economics only work if the number of bodies read is BOUNDED: reading is the expensive act,
    so the selector reads `triage_read_n` candidates, each truncated to `triage_read_chars`, on the
    lite tier. It picks WHOLE pages (no section naming — a short news body is opened whole anyway);
    the strong answerer then opens only the picks."""
    shortlist = batch[: s.triage_read_n]
    docs: list[str] = []
    ids: list[str] = []
    for hit in shortlist:
        try:
            page = store.page(hit.page_id)
        except NodeNotFound:
            continue  # a stale catalog row must not break a query
        ids.append(hit.page_id)
        body = f"{page.title}\n\n{page.markdown}".strip()[: s.triage_read_chars]
        docs.append(f"[{len(ids)}] {store.path_str(hit.page_id)}\n{body}")
    if not docs:
        return [], ""

    prompt = llm.load_prompt("select_read", query=query, documents="\n\n---\n\n".join(docs))
    data = llm.generate_json(prompt, schema=_SELECT_SCHEMA, model=s.model_lite)

    out: list[BasketItem] = []
    seen: set[int] = set()
    for row in (data.get("needed") or [])[:max_pages]:
        try:
            num = int(row.get("doc"))
        except (TypeError, ValueError):
            continue
        if num < 1 or num > len(ids) or num in seen:
            continue  # the model may hallucinate a number; ignore rather than crash
        seen.add(num)
        page_id = ids[num - 1]
        out.append(
            BasketItem(
                page_id=page_id,
                path=store.path_str(page_id),
                sections=[],  # whole page — the selector already read the body
                why=str(row.get("why", "")).strip(),
            )
        )
    return out, str(data.get("thought") or "").strip()


def _open_basket(basket: list[BasketItem], store: LibraryStore, s: Settings) -> list[PageContent]:
    """Turn the basket into evidence. Only the chosen sections — and a hard cap, because one
    mis-parsed 12,842-token 'page' must not be allowed to eat the whole answer budget."""
    out: list[PageContent] = []
    for item in basket:
        try:
            page = store.page(item.page_id)
        except NodeNotFound:
            continue
        body = pick_sections(page.markdown, item.sections, max_tokens=s.cascade_max_page_tokens)
        out.append(page.model_copy(update={"markdown": body}))
    return out


def _fuzzy_path(path: str, by_path: dict[str, str]) -> str | None:
    """The model may return a path with a stray quote or a shortened prefix. Do not punish it."""
    key = path.strip().strip('"').lower()
    if not key:
        return None
    for candidate, page_id in by_path.items():
        low = candidate.lower()
        if low == key or low.endswith(key) or key.endswith(low.split(" ▸ ")[-1]):
            return page_id
    return None


def _nothing(
    query: str, events: list[NavEvent], closest: list[str], rounds: int = 1
) -> CascadeResult:
    events.append(NavEvent("not_found", "NOT FOUND", None, None, "notfound"))
    return CascadeResult(
        answer=compose_not_found(query, closest),
        nav=NavResult(
            status="NOT_FOUND",
            closest=closest,
            backtracks=rounds - 1,
            reason="cascade",
            events=events,
        ),
        rounds=rounds,
    )
