"""Semantic answer cache: serve a stored answer to a question that MEANS the same as one already
answered, skipping retrieval + generation entirely.

Distinct from the catalog (question -> PAGE, still generates) and the flywheel (feeds retrieval):
this is question -> FINAL ANSWER, and a hit costs zero LLM calls. Honesty is preserved by what it
refuses to cache — only grounded, cited, confident answers, never a NOT_FOUND — and by a tight
similarity threshold, because a wrong hit serves the wrong answer. Entries are editable (a curated
answer overrides) and the whole cache is toggleable.
"""
