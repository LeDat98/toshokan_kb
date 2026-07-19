"""The card catalog index (principle P5 / decisions D-005, D-039) — and the ingest CONTRACT.

`index_page` is the hook ingest calls after a page is written; `index_kind` (config.py) decides
what the sieve holds:

  - **text** (the default, D-039): embed the page body directly. ZERO generation calls, and it wins
    every external metric we have. This is the only representation a real corpus can afford.
  - **questions**: the flywheel — generate a handful of user-phrased vi+en questions the page
    answers, and embed those. One artifact then serves three jobs: card-catalog entry points, the
    routing eval set, and a user→library vocabulary bridge. Kept because on our own colloquial-VI
    held-out set it still wins R@1 (SCORECARD §5.1); not the default, and not retired.
  - **both**: measured worse than text alone so far (metric bug 6.6); for experiments.

**The contract.** Every leaf in the library must end up with the same furniture — `title`,
`one_line`, `keywords` — no matter which source it came from. When the sieve indexes *questions*,
the missing fields are generated in the SAME call that generates the questions, for free. When it
indexes *text*, nothing is generated and the page keeps the deterministic first-sentence `one_line`
the splitter gave it — so the furniture never depends on the source format either way.

That is deliberate, and it is the difference between a product and a pile of exceptions. The AI-news
corpus writes its summary under `summary:`; the retail corpus writes it under `description:`; a raw
PDF writes it nowhere. Special-casing key names would mean a code change for every new source and a
library whose spine labels are richer on some shelves than others — which quietly biases the sieve,
because a page with a good spine label is easier to find than a page without one. So we do not read
key names at all beyond the obvious ones: **if the source did not give it, we make it.**
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.models import one_line_of
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

_CONTENT_LIMIT = 6000  # the recursive splitter bounds a page, so this rarely bites now
_MAX_KEYWORDS = 6
# A text-index row embeds the whole page body. gemini's embedder truncates a long input anyway; be
# explicit about where, and match evals/indexing.py exactly so the catalog we WRITE holds the same
# vector the `probe-index` MEASUREMENT scored (D-039).
_TEXT_LIMIT = 8000

_SCHEMA = {
    "type": "object",
    "properties": {
        # The ingest contract: the model always offers these, and we use them only where the source
        # left a hole. Free — same call, same tokens.
        "one_line": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"vi": {"type": "string"}, "en": {"type": "string"}},
                "required": ["vi", "en"],
            },
        },
        # The entry vocabulary (§8.2): the words a reader reaches for that are NOT the library's
        # words. Same generation call, so it is free. Stored with kind='term' so its effect on
        # retrieval can be measured separately instead of quietly mixed into the questions.
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"vi": {"type": "string"}, "en": {"type": "string"}},
                "required": ["vi", "en"],
            },
        },
    },
    "required": ["questions"],
}


@dataclass
class Question:
    text: str
    lang: str
    kind: str = "question"  # question | term


@dataclass
class PageCard:
    """Everything one lite call yields about a page.

    `indexed_rows` is not from the model — it is how many rows `index_page` actually wrote to the
    catalog. The caller uses it to tell a real indexing success from a page that produced nothing,
    which under a TEXT index can no longer be inferred from `questions` (a text index writes rows
    and generates no questions at all)."""

    questions: list[Question] = field(default_factory=list)
    one_line: str = ""
    keywords: list[str] = field(default_factory=list)
    indexed_rows: int = 0


def generate_card(
    title: str,
    markdown: str,
    *,
    book_title: str = "",
    n: int | None = None,
    llm: LLM | None = None,
) -> PageCard:
    """One call: the questions this page answers, its spine label, and its keywords."""
    llm = llm or get_llm()
    settings = get_settings()
    n = n or settings.questions_per_page
    prompt = llm.load_prompt(
        "gen_questions",
        book=book_title or "(standalone)",
        title=title,
        content=markdown[:_CONTENT_LIMIT].strip() or "(empty)",
        n=n,
    )
    # summarising one page into questions is easy but high-volume (1 call per page, the bulk of
    # a reindex) → run it on the cheap tier; navigation keeps the strong model (D-027).
    data = llm.generate_json(prompt, schema=_SCHEMA, model=settings.model_lite)

    rows: list[Question] = []
    for kind in ("question", "term"):
        for item in data.get(f"{kind}s") or []:
            rows += _read_item(item, kind, settings.question_langs)

    keywords = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
    return PageCard(
        questions=rows,
        # a spine label is a spine label whoever wrote it — the cap is enforced here too, because a
        # model asked for "<=120 chars" will one day return 400 (ROUTING_REDESIGN §0a)
        one_line=one_line_of(str(data.get("one_line") or "").strip(), settings.max_one_line_chars),
        keywords=keywords[:_MAX_KEYWORDS],
    )


def _read_item(item: object, kind: str, langs: tuple[str, ...]) -> list[Question]:
    """Read one generated row, whatever shape the model chose to send it in.

    A schema is a REQUEST, not a guarantee. Gemini enforces `response_schema` server-side; DashScope
    only honours `json_object` and leaves the shape to the model — so Qwen periodically returns
    `"questions": ["…", "…"]` (a flat list of strings) where the schema asked for
    `[{"vi": …, "en": …}]`. Valid JSON, wrong shape, and `item.get(lang)` raised AttributeError.

    MEASURED, and this is the part that stings: `index_page_safe` swallowed that exception per
    page, so **439 of 2,079 pages (21%) were written to the library and never entered the catalog**
    — the sieve could not see a fifth of the corpus. The import printed "2079 pages · catalog now
    18050 questions" and said nothing. A parser that crashes on an unexpected shape, inside a caller
    that logs and continues, is how a silent 21% data loss looks from outside: exactly like success.
    """
    if isinstance(item, str):
        text = item.strip()
        # a bare string carries no language claim; label it by the first configured language rather
        # than throw it away — a usable entry point beats a missing one
        return [Question(text=text, lang=langs[0], kind=kind)] if text else []
    if not isinstance(item, dict):
        return []
    out = [
        Question(text=str(item[lang]).strip(), lang=lang, kind=kind)
        for lang in langs
        if str(item.get(lang, "")).strip()
    ]
    if out:
        return out
    # a dict with none of the expected language keys — take any string value it does have
    text = next((str(v).strip() for v in item.values() if isinstance(v, str) and v.strip()), "")
    return [Question(text=text, lang=langs[0], kind=kind)] if text else []


def generate_questions(
    title: str,
    markdown: str,
    *,
    book_title: str = "",
    n: int | None = None,
    llm: LLM | None = None,
) -> list[Question]:
    """Ask the model for `n` bilingual question intents this page answers."""
    return generate_card(title, markdown, book_title=book_title, n=n, llm=llm).questions


def index_page(
    catalog: Catalog,
    *,
    page_id: str,
    book_id: str,
    path: str,
    title: str,
    markdown: str,
    book_title: str = "",
    n: int | None = None,
    llm: LLM | None = None,
    index_kind: str | None = None,
) -> PageCard:
    """Embed a page's chosen representation and (re)write its catalog rows.

    `index_kind` (default from Settings, see config.py) decides WHAT the sieve holds — `text` (the
    body, zero generation, the default), `questions` (the flywheel, one lite call), or `both`. Under
    `text` the model is never called: the whole economic case for text-indexing is that a real
    corpus cannot afford a generation call per page, so this path must make none.

    Idempotent: existing rows for `page_id` are removed first, so re-indexing replaces rather than
    duplicates. Returns the card so the caller can fill any spine label/keyword the source left
    empty — but a text index generates neither; the page keeps the deterministic first-sentence
    `one_line` the splitter already gave it.
    """
    settings = get_settings()
    index_kind = index_kind or settings.index_kind
    llm = llm or get_llm()
    want_questions = index_kind in ("questions", "both")

    # generate ONLY when the sieve needs questions — otherwise no LLM call at all
    card = (
        generate_card(title, markdown, book_title=book_title, n=n, llm=llm)
        if want_questions
        else PageCard()
    )

    texts: list[str] = [q.text for q in card.questions]
    langs: list[str] = [q.lang for q in card.questions]
    kinds: list[str] = [q.kind for q in card.questions]
    if index_kind in ("text", "both"):
        body = f"{title}\n\n{markdown}".strip()[:_TEXT_LIMIT] or title or "(empty)"
        texts.append(body)
        langs.append("*")  # a page body is not one language; '*' marks a body row, not a question
        kinds.append("text")

    catalog.remove_page(page_id)
    if not texts:  # e.g. `questions` mode and the model returned nothing usable
        return card
    embeddings = llm.embed(texts)  # RETRIEVAL_DOCUMENT
    # A text row is EMBEDDED from the full body but STORED with an empty display text: its 8,000
    # chars must never ride into a triage card (which surfaces `Hit.text` at a ~59-token/page
    # budget). Triage falls back to the spine label + section titles — the signal it was built on.
    display = [t if k != "text" else "" for t, k in zip(texts, kinds, strict=True)]
    catalog.add_page(
        page_id=page_id,
        book_id=book_id,
        path=path,
        texts=display,
        langs=langs,
        embeddings=embeddings,
        kinds=kinds,
        # stamp the coordinate system these vectors live in; the catalog refuses a second one
        embed_model=settings.embed_model,
        # and the representation — the catalog refuses a page indexed a different way (bug 6.6)
        index_kind=index_kind,
    )
    card.indexed_rows = len(texts)
    n_terms = sum(1 for k in kinds if k == "term")
    n_text = sum(1 for k in kinds if k == "text")
    log.info(
        "indexed_page",
        page_id=page_id,
        kind=index_kind,
        n_questions=len(texts) - n_terms - n_text,
        n_terms=n_terms,
        n_text=n_text,
    )
    return card
