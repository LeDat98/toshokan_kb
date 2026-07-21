"""Cache lookup + write, with the honesty rules that keep a cache from ossifying a bad answer.

What we REFUSE to cache is what keeps the cache trustworthy:
  - never a NOT_FOUND — a gap must keep being retried (a later ingest may fill it);
  - only a GROUNDED answer (it has citations) at or above a confidence floor;
  - and a hit only clears a conservative similarity threshold, because a wrong hit serves the wrong
    question's answer.
A curated (human-edited) entry is exempt from the confidence/citation checks on write — a human
already vouched for it.
"""

from __future__ import annotations

import numpy as np

from libkb.cache.store import AnswerCache, CacheHit
from libkb.config import Settings
from libkb.llm.client import LLM

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def cache_lookup(
    cache: AnswerCache, query: str, llm: LLM, settings: Settings
) -> tuple[CacheHit | None, np.ndarray | None]:
    """Embed the query and look for a semantically-equivalent cached question. Returns (hit, vec):
    `vec` is returned even on a miss so the caller can reuse it to WRITE the fresh answer without
    embedding twice. Fails open (no hit) on any error — the cache must never break answering."""
    if not cache.is_enabled():
        return None, None
    try:
        vec = np.asarray(
            llm.embed([query], task=settings.answer_cache_embed_task)[0], dtype=np.float32
        )
    except Exception:
        return None, None  # embedding failed → answer normally, cache nothing
    try:
        hit = cache.search(
            vec,
            threshold=settings.answer_cache_threshold,
            margin=settings.answer_cache_margin,
        )
    except Exception:
        return None, vec
    return hit, vec


def cache_put(cache: AnswerCache, query: str, vec, result, settings: Settings) -> None:
    """Store a fresh answer IF it clears the honesty bar. Best-effort; never raises."""
    if vec is None or not cache.is_enabled():
        return
    answer = result.answer
    if answer.status != "answered":
        return  # never cache a NOT_FOUND — the gap must stay retriable
    if not answer.citations:
        return  # only cache a GROUNDED answer
    floor = _CONFIDENCE_RANK.get(settings.answer_cache_min_confidence, 1)
    if _CONFIDENCE_RANK.get(answer.confidence, 1) < floor:
        return  # below the confidence floor — do not enshrine an unsure answer
    try:
        page_ids = [p.page_id for p in result.nav.pages] or [c.page_id for c in answer.citations]
        cache.put(
            query,
            vec,
            answer.text,
            [{"path": c.path, "page_id": c.page_id} for c in answer.citations],
            answer.confidence,
            page_ids,
        )
    except Exception:
        pass  # a failed cache write must never cost the reader their (already computed) answer
