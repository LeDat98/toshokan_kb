"""A page is not the unit of reading. A SECTION is (docs/RETRIEVAL_REDESIGN.md §3.1).

MEASURED on the live library (125 pages):

    a full page ................. 1,571 tokens  (median 1,644 · MAX 12,842)
    its section headers ......... 59 tokens     — enough to decide whether to open it
    its two largest sections .... 516 tokens    — enough to answer from
                                                  → a section is 13.5x cheaper than a page

78% of pages already carry ≥2 same-level headings, so this structure is free: it is sitting in the
markdown, unused. And the 12,842-token page is a mis-parsed PDF — one read of it wrecks a query's
whole budget. Reading by section defuses that without an ingest migration.

The headings rule is deliberately the same one `ingest/split.py` uses to cut a document into pages:
split at the **shallowest repeated** heading level. A document and a page are the same kind of
object at different scales, and two different splitting rules would eventually disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from libkb.ingest.split import clean_title

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
_FENCE = re.compile(r"^```", re.MULTILINE)


@dataclass
class Section:
    title: str
    body: str  # includes the heading line, so a section reads as a self-contained fragment

    @property
    def tokens(self) -> int:
        return len(self.body) // 4


def split_sections(markdown: str) -> list[Section]:
    """Cut a page at its shallowest repeated heading level. One section if it has no structure."""
    headings = _headings_outside_fences(markdown)
    levels = [level for _, level, _ in headings]
    if not levels:
        return [Section(title="", body=markdown.strip())]

    boundary = next((lv for lv in sorted(set(levels)) if levels.count(lv) >= 2), min(levels))
    cuts = [(start, title) for start, level, title in headings if level == boundary]
    if not cuts:
        return [Section(title="", body=markdown.strip())]

    sections: list[Section] = []
    preamble = markdown[: cuts[0][0]].strip()
    if preamble:
        # The text above the first boundary heading is a section too, and often the important one:
        # it is where a page states its definition before drilling into parts. It must be nameable,
        # or the librarian cannot ask for it. Name it after the page's own H1 when there is one.
        opener = next((t for _, level, t in headings if level < boundary), "(opening)")
        sections.append(Section(title=opener, body=preamble))
    for i, (start, title) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(markdown)
        body = markdown[start:end].strip()
        if body:
            sections.append(Section(title=title, body=body))
    return sections or [Section(title="", body=markdown.strip())]


def section_index(markdown: str) -> list[str]:
    """Just the section titles — what the librarian triages on. ~59 tokens for a whole page."""
    return [s.title for s in split_sections(markdown) if s.title]


# The words that carry no topical signal — a span that overlaps the query only on these is not
# "about" the query. Small, bilingual (vi+en) on purpose: the goal is to strip the connective
# tissue, not to stem, and an over-eager list would drop the very rare term that made the match.
_STOPWORDS = (
    "the a an and or of to in on for with is are was were be as by at from "
    "this that these those it its into what which how why when where who whom whose "
    "do does did can could should would "
    "và của là các một những cho với trong khi về được có không này đó gì làm sao nào để"
)
_STOP = frozenset(_STOPWORDS.split())
_SENT = re.compile(r"[.!?。？！\n]+")
_MD_NOISE = re.compile(r"^[#>\-*\s\d.)]+")  # leading heading/list/quote markers on a line
_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _content_words(text: str) -> set[str]:
    """Lowercased topical words of a string — stopwords and 1-char tokens dropped."""
    words = (w for w in _WORD.split(text.lower()) if len(w) > 1)
    return {w for w in words if w not in _STOP}


def query_passages(
    markdown: str, query: str, *, k: int = 1, max_chars: int = 200, skip_headings: bool = True
) -> list[str]:
    """The k passages of a page that most overlap the query, best first — the sieve's answer to
    "why THIS page?", made visible to triage. MODEL-FREE and deterministic: it scores each sentence
    by how many DISTINCT query content-words it carries.

    Why more than one (the Tier-0 lever): a single sentence is a *point* estimate of relevance, and
    on a multi-part question the one best sentence is by construction about the question's most
    obvious half — which is exactly the failure the coverage work kept hitting. Two or three spans
    from DIFFERENT parts of the page tell the librarian whether the page covers one part or several,
    and that is the judgement being asked of it. Cost is ~50 tokens per extra span and zero LLM.

    Spans are deduplicated by content words, so a page that repeats its thesis three times does not
    spend the whole card saying it once per paragraph. The similarity is **symmetric** (Jaccard) on
    purpose: a containment test lets a two-word HEADING swallow the full sentence underneath it,
    which is precisely backwards — the short span is the one carrying no information.

    `skip_headings` drops markdown heading lines, which are already listed on the card under
    `Sections:` — quoting one back as "the relevant passage" spends tokens to say nothing. It is a
    parameter rather than a rule because `query_snippet` is SHIPPED AND MEASURED (D-050) and must
    keep its exact behaviour; only the new multi-passage path gets the improvement.
    """
    if max_chars <= 0 or k <= 0:  # the A/B off-switch: chars=0 reverts to the bare spine-label card
        return []
    want = _content_words(query)
    if not want:
        return []
    scored: list[tuple[int, int, str, frozenset[str]]] = []
    for order, raw in enumerate(_SENT.split(markdown)):
        if skip_headings and raw.lstrip().startswith("#"):
            continue
        span = _MD_NOISE.sub("", raw).strip()
        if len(span) < 12:
            continue
        words = _content_words(span)
        hits = len(want & words)
        if hits:
            scored.append((-hits, order, span, frozenset(words)))
    scored.sort()  # by descending hits, then document order — ties lean to the definitional opening

    out: list[str] = []
    taken: list[frozenset[str]] = []
    for _, _, span, words in scored:
        if any(len(words & seen) / max(len(words | seen), 1) >= 0.7 for seen in taken):
            continue
        text = re.sub(r"\s+", " ", span).strip()
        out.append(text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…")
        taken.append(words)
        if len(out) >= k:
            break
    return out


def query_snippet(markdown: str, query: str, *, max_chars: int = 200) -> str:
    """The single best query-relevant passage (D-050). A `query_passages(k=1)` wrapper, kept as its
    own name because it is the shipped, MEASURED behaviour (+1.7 answer, 2 seeds × n=200).

    This restores, for a TEXT index, the discriminative line a QUESTION index gave triage for free
    (`Answers questions like: "…"`, D-035). A text row stores an empty display text (questions.py),
    so without this the triage card is just a spine label + section titles — the sieve's reason for
    ranking the page is thrown away exactly where the librarian needs it.

    Returns "" when nothing in the page overlaps the query on a content word: an honest blank beats
    a misleading first sentence. The spine label already carries the page's generic gist.

    `skip_headings=False` keeps this BIT-IDENTICAL to the version the +1.7-answer number was
    measured on. The improvement lives in `query_passages`, where it can be measured before it is
    believed — a shipped baseline that quietly changes is a baseline you can no longer compare to.
    """
    found = query_passages(markdown, query, k=1, max_chars=max_chars, skip_headings=False)
    return found[0] if found else ""


def relevant_sections(markdown: str, query: str, *, k: int = 3) -> list[str]:
    """Which of a page's SECTION TITLES sit on the part of the page the query touches, best first.

    Titles alone are a famously bad selection signal — a section called `3.2 Analysis` says nothing —
    and the librarian is asked to copy one back exactly. This scores each section by how much its
    BODY overlaps the query and hands back the winners, so the card can mark them. The librarian
    still chooses; it is given a reason to choose, which is the thing it did not have.

    MODEL-FREE, computed from the body already fetched. Returns [] when nothing overlaps — an
    unmarked list is the honest signal that the page is relevant as a whole or not at all.
    """
    if k <= 0:
        return []
    want = _content_words(query)
    if not want:
        return []
    scored = []
    for order, section in enumerate(split_sections(markdown)):
        if not section.title:
            continue
        hits = len(want & _content_words(section.body))
        if hits:
            scored.append((-hits, order, section.title))
    scored.sort()
    return [title for _, _, title in scored[:k]]


def pick_sections(markdown: str, titles: list[str], *, max_tokens: int = 4000) -> str:
    """The bodies of the named sections, in document order. Unknown titles are ignored rather than
    failing: the librarian is naming things from a list he was shown, and a near-miss must degrade
    to "give him something" rather than "give him nothing".

    An empty or unmatched request falls back to the WHOLE page — never to silence. Evidence the
    answerer does not receive is evidence that cannot be cited (P6).
    """
    sections = split_sections(markdown)
    wanted = {t.strip().lower() for t in titles if t.strip()}
    chosen = [s for s in sections if s.title.strip().lower() in wanted] if wanted else []
    if not chosen:
        chosen = sections  # asked for nothing recognisable → hand over the page

    out: list[str] = []
    used = 0
    for section in chosen:
        if used + section.tokens > max_tokens and out:
            break  # a mis-parsed 12,842-token "page" must not blow the answer budget
        out.append(section.body)
        used += section.tokens
    return "\n\n".join(out)


def _headings_outside_fences(markdown: str) -> list[tuple[int, int, str]]:
    """(offset, level, title) for every heading that is not inside a ``` code fence."""
    fences = [m.start() for m in _FENCE.finditer(markdown)]
    out: list[tuple[int, int, str]] = []
    for m in _HEADING.finditer(markdown):
        if sum(1 for f in fences if f < m.start()) % 2 == 1:
            continue  # an odd number of fences before it ⇒ we are inside a code block
        # same cleaning as ingest: `## **3 Methodology**` names a section "3 Methodology". The
        # librarian has to copy these titles back exactly, so they must not carry formatting.
        out.append((m.start(), len(m.group(1)), clean_title(m.group(2))))
    return out
