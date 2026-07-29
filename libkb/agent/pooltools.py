"""Tools the agent uses ON THE CANDIDATE POOL — not on the corpus (D-066).

The scope rule that produced this file: the sieve is not the bottleneck. FiQA R@100 = **0.920**,
MultiHop AllGold@20 = **93.5%** — the evidence is nearly always already inside the top 50–100.
What loses it is SELECTION: triage keeps 69% of the gold where taking the embedder's own top-10
keeps 75%. The agent is being asked to pick from a list of section TITLES and is, measurably,
guessing.

So these are not retrievers. Every one of them takes the pool the cascade already proposed and
answers a question the agent would otherwise have to guess at:

    find_in_candidates   "which of these 50 pages literally contain this phrase, and where?"
    coverage_map         "this question has 3 parts — which page covers which part?"
    locate_passages      "show me the line in each page that touches my question"

All three are **0 LLM calls**, computed from bodies already fetched. That matters twice: it makes
them free to call in a loop, and it makes their output a FACT about the page rather than a second
model's opinion about it — which is the thing a reranker was (D-048) and which did not work.

Note what `find_in_candidates` is NOT. D-065 measured BM25 fused into the sieve across all 57,638
FiQA documents and it lost badly (−0.18 nDCG@10), with only 0.6% of gold found that dense missed.
That settles lexical *retrieval*. It says nothing about lexical *inspection* of documents already
retrieved — there is no ranking to corrupt here, and the 0.6% figure is about documents never
retrieved at all. Different question, different tool, still open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from libkb.library.sections import _STOP, _content_words, split_sections

# A question is split on coordination and clause punctuation. Deliberately DETERMINISTIC and
# deliberately crude: an LLM split is a whole extra call (`decompose_split.md` exists if that is
# ever wanted), and this tool's value is being free enough to call inside a loop. It over-splits
# more often than it under-splits, which is the safe direction — an extra part costs a column,
# a missed part costs the coverage answer.
_SPLIT = re.compile(
    r"\s+(?:and|or|but|versus|vs\.?|as well as|còn|và|hoặc|hay là)\s+|[;?]|\s+—\s+", re.IGNORECASE
)
_MIN_PART_WORDS = 2


@dataclass
class Hit:
    page_id: str
    path: str
    section: str
    line: str


@dataclass
class CoverageCell:
    page_id: str
    path: str
    covered: list[int] = field(default_factory=list)  # indices into `parts`


@dataclass
class Coverage:
    parts: list[str]
    cells: list[CoverageCell] = field(default_factory=list)
    uncovered: list[int] = field(default_factory=list)  # parts NO candidate covers

    def best_set(self, limit: int) -> list[str]:
        """A greedy minimal covering set — the pages that between them touch the most parts.

        Greedy set-cover is the textbook approximation and it is the right one here: the agent gets
        a *suggestion* it can override, not a decision, and the whole pool is ≤100 items so the
        approximation ratio is academic. Ties break toward the earlier (better-ranked) page, so a
        pool ordered by the sieve stays respected."""
        need = {i for cell in self.cells for i in cell.covered}
        chosen: list[str] = []
        for _ in range(limit):
            best, gain = None, 0
            for cell in self.cells:
                got = len(need & set(cell.covered))
                if got > gain:
                    best, gain = cell, got
            if best is None:
                break
            chosen.append(best.page_id)
            need -= set(best.covered)
            if not need:
                break
        return chosen


def split_question(query: str) -> list[str]:
    """A question → its parts. One part for a single-fact question; several for a compound one.

    This is the tool that attacks the measured multi-hop floor (comparison 74%, temporal 58%): a
    compound question retrieved as ONE blurred vector ranks none of its parts sharply, and a
    selector judging pages one at a time has no way to notice that it has covered the same half
    twice. Naming the parts is what makes "which page covers which" answerable at all."""
    parts = [p.strip(" ,.-") for p in _SPLIT.split(query) if p and p.strip(" ,.-")]
    kept = [
        p for p in parts if len([w for w in _content_words(p) if w not in _STOP]) >= _MIN_PART_WORDS
    ]
    return kept or [query.strip()]


def coverage_map(
    query: str, pages: list[tuple[str, str, str]], *, parts: list[str] | None = None
) -> Coverage:
    """Which candidate covers which part of the question. `pages` is (page_id, path, markdown).

    A part is "covered" by a page when the page's text carries at least half of that part's content
    words. Half, not all: a page that says "international orders ship in 60 days" covers "how long
    for international orders" without repeating it. And not *any*, which would make every page
    cover every part through one shared word — the failure BM25 has and this deliberately does not,
    because it thresholds per part instead of summing across them."""
    parts = parts or split_question(query)
    want = [{w for w in _content_words(p) if w not in _STOP} for p in parts]
    cells: list[CoverageCell] = []
    covered_any: set[int] = set()
    for page_id, path, markdown in pages:
        words = _content_words(markdown)
        covered = [i for i, need in enumerate(want) if need and len(need & words) * 2 >= len(need)]
        cells.append(CoverageCell(page_id=page_id, path=path, covered=covered))
        covered_any.update(covered)
    return Coverage(
        parts=parts,
        cells=cells,
        uncovered=[i for i in range(len(parts)) if i not in covered_any],
    )


def find_in_candidates(
    pattern: str, pages: list[tuple[str, str, str]], *, regex: bool = False, limit: int = 40
) -> list[Hit]:
    """Literal (or regex) search across the candidate BODIES — the agent's grep, scoped to the pool.

    Returns the SECTION each match sits in, not just the page: the agent's next move is to ask for
    a section by name, so a hit that cannot name one is half an answer.

    A bad regex from a model must not crash a query — an invalid pattern degrades to a literal
    search, which is what the agent almost always meant anyway."""
    if not pattern.strip():
        return []
    try:
        probe = re.compile(pattern if regex else re.escape(pattern), re.IGNORECASE)
    except re.error:
        probe = re.compile(re.escape(pattern), re.IGNORECASE)

    hits: list[Hit] = []
    for page_id, path, markdown in pages:
        for section in split_sections(markdown):
            for raw in section.body.splitlines():
                line = raw.strip()
                if len(line) < 3 or not probe.search(line):
                    continue
                hits.append(
                    Hit(
                        page_id=page_id,
                        path=path,
                        section=section.title,
                        line=line if len(line) <= 200 else line[:199].rstrip() + "…",
                    )
                )
                break  # one line per section is enough to point the agent; it can open the section
            if len(hits) >= limit:
                return hits
    return hits


def render_coverage(coverage: Coverage, *, max_rows: int = 24) -> str:
    """The coverage map as the compact block a selector prompt can carry.

    Only pages covering something are listed — a table of mostly-empty rows spends the tokens the
    tool was supposed to save, and a page covering nothing is exactly the page the agent does not
    need to be told about."""
    if len(coverage.parts) < 2:
        return ""  # a single-part question has nothing to map; say nothing rather than say it
    lines = ["The question has these parts:"]
    lines += [f"  [{i + 1}] {part}" for i, part in enumerate(coverage.parts)]
    rows = [c for c in coverage.cells if c.covered][:max_rows]
    if rows:
        lines.append(
            "Which candidate covers which part (computed from the page text, not guessed):"
        )
        for cell in rows:
            covers = ", ".join(f"[{i + 1}]" for i in cell.covered)
            lines.append(f"  {covers} ← {cell.path}")
    if coverage.uncovered:
        missing = ", ".join(f"[{i + 1}]" for i in coverage.uncovered)
        lines.append(f"NO candidate covers: {missing} — say so rather than substituting for it.")
    return "\n".join(lines)


def render_hits(hits: list[Hit], pattern: str, *, max_rows: int = 20) -> str:
    if not hits:
        return f'Nothing in the candidates contains "{pattern}".'
    lines = [f'Candidates containing "{pattern}":']
    for hit in hits[:max_rows]:
        where = f" ▸ {hit.section}" if hit.section else ""
        lines.append(f"  {hit.path}{where}\n      {hit.line}")
    return "\n".join(lines)
