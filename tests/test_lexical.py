"""BM25 — what it is, what it is not, and the config hypothesis D-032 never separated. LLM-free.

D-032 refuted *fusing BM25 into retrieval*, on two query sets that were both adversarial to it by
construction (an LLM-generated tautology, and a CROSS-LINGUAL paraphrase set — Vietnamese questions
against English pages, where BM25 has no tokens to match at all). The mechanism BM25 exists for — a
rare term appearing verbatim — was in neither.

These tests pin three things a measurement cannot:
  1. BM25 is **lexical, not semantic**. It has no idea "car" and "automobile" are the same thing,
     and no amount of tuning will give it one. Anything that looks like understanding is IDF.
  2. The **shape** of D-032's failure is reproducible in five documents — a crowd echoing the
     question's common words can bury the one document carrying its rare one.
  3. The **rare-term gate** fires on exactly the queries BM25 is for, and stays out of the way
     otherwise. That is the trigger `config.py` promised and nobody built.

Writing (2) already corrected an assumption: **stopword filtering alone does not rescue that
ranking — only the gate does.** And whether either matters once IDF has 57,638 documents to work
with is not something a toy corpus can answer. That is `libkb probe-lexical`'s job.
"""

import pytest

from libkb.evals.lexical import (
    ARMS,
    BM25,
    dense_rankings,
    fold,
    query_terms,
    rank_arm,
    rrf,
    tokenize,
)

# One rare term ("GMROI") and a crowd of common ones — the shape of the real problem.
DOCS = [
    "GMROI is gross margin return on inventory investment.",  # 0 — the only GMROI document
    "This report is about the management of the inventory in the store for the team.",  # 1
    "The management of the store and the management of the team in the report.",  # 2
    "Inventory in the store is about the team and the report and the management.",  # 3
    "Turbochargers force air into an engine.",  # 4 — unrelated
]


# ------------------------------------------------------------------ it is lexical, not semantic


def test_bm25_has_no_idea_what_a_word_means():
    """The headline. A synonym is simply a different token — there is no 'semantic BM25'."""
    index = BM25.build(["A car is a vehicle.", "An automobile is a vehicle."])
    assert index.search(query_terms("car", drop_stopwords=True), top_k=5) == [0]
    assert index.search(query_terms("automobile", drop_stopwords=True), top_k=5) == [1]
    # and a word in neither document matches nothing at all — no "closest" fallback exists
    assert index.search(query_terms("motorcycle", drop_stopwords=True), top_k=5) == []


def test_no_stemming_because_the_live_index_has_none():
    """`unicode61` does not stem. A harness that stemmed would measure a retriever we do not run."""
    index = BM25.build(["running the report", "run the report"])
    assert index.search(["running"], top_k=5) == [0]
    assert index.search(["run"], top_k=5) == [1]


def test_folding_matches_remove_diacritics_2_including_vietnamese_d():
    assert fold("Đầu Tư") == "dau tu"
    assert tokenize("Chạy — nhanh!") == ["chay", "nhanh"]
    assert tokenize("a bc") == ["bc"], "1-character tokens are dropped, as FTS5 is configured"


def test_cross_lingual_matching_is_structurally_impossible():
    """Why D-032's paraphrase set could only ever produce this answer: a Vietnamese question and an
    English page share no tokens, so BM25 scores ~nothing. That is BM25 working as designed, on a
    task it cannot do — not evidence about BM25's value where the language matches."""
    index = BM25.build(["Inventory turnover is COGS divided by average inventory."])
    assert (
        index.search(query_terms("vòng quay hàng tồn kho là gì", drop_stopwords=True), top_k=5)
        == []
    )


# ------------------------------------------------------------------ the scoring function itself


def test_idf_makes_a_rare_term_outweigh_a_common_one():
    index = BM25.build(DOCS)
    assert index.df("gmroi") == 1
    assert index.df("management") == 3
    assert index.idf("gmroi") > index.idf("management")


def test_term_frequency_saturates():
    """The 20th occurrence is worth far less than the 2nd (k1). Without saturation, keyword-stuffing
    would win every ranking outright.

    All three documents are padded to the SAME length with unique filler, so length normalisation is
    held constant and what is left is saturation alone."""
    filler = [f"w{i}" for i in range(19)]
    index = BM25.build(
        [
            " ".join(["alpha", *filler]),  # tf = 1
            " ".join(["alpha", "alpha", *filler[:18]]),  # tf = 2
            " ".join(["alpha"] * 20),  # tf = 20
        ]
    )
    s = index.score_docs(["alpha"])
    assert s[0] < s[1] < s[2], "more occurrences still ranks higher"
    assert s[2] < 3 * s[0], "but 20x the occurrences buys under 3x the score"
    marginal_early = s[1] - s[0]  # the 2nd occurrence
    marginal_late = (s[2] - s[1]) / 18  # each of occurrences 3..20
    assert marginal_late < marginal_early / 5, "each extra occurrence is worth steeply less"


def test_a_long_document_is_not_rewarded_for_being_long():
    """Length normalisation (b): without it, padding a document with filler would raise its score
    for every query, and the 12,842-token mis-parsed PDF page would outrank everything."""
    index = BM25.build(["alpha beta", "alpha beta " + "filler " * 200])
    assert index.search(["alpha"], top_k=2) == [0, 1]


def test_a_document_matching_nothing_never_appears():
    index = BM25.build(DOCS)
    assert 4 not in index.search(query_terms("gmroi inventory", drop_stopwords=True), top_k=5)


# ------------------------------------------------------------------ THE config hypothesis


def test_the_common_word_crowd_can_bury_the_one_document_that_answers():
    """**The point of the file** — and note carefully what it does and does NOT establish.

    Production ORs every word of the question and filters none (`catalog/store.py::_fts_terms`).
    BM25 sums a contribution per matched term, so documents that merely echo the question's *common*
    words accumulate several small scores and can outrank the single document carrying the rare one.
    That is the shape of "BM25 latches onto the common ones and drags noise up" (D-032).

    **What this test does not prove:** that it happens at FiQA scale. IDF's protection grows with
    the corpus — here "management" sits in 3 of 5 documents, so its IDF is barely below "gmroi"'s;
    at 57,638 documents "the" is in ~all of them and "GMROI" in three, and IDF may well handle it
    alone. Writing this test is what exposed that: stopword filtering alone does NOT rescue the
    ranking below. Only the rare-term GATE does. Which of the two matters in a real corpus is
    exactly what `libkb probe-lexical` is for — the hypothesis is not the finding."""
    index = BM25.build(DOCS)
    question = "what is the GMROI in the report about the management of the inventory in the store"

    unfiltered = index.search(query_terms(question, drop_stopwords=False), top_k=5)
    filtered = index.search(query_terms(question, drop_stopwords=True), top_k=5)
    gated = index.search(
        index.rare(query_terms(question, drop_stopwords=True), max_df_ratio=0.25), top_k=5
    )

    assert unfiltered[0] != 0, "the common-word crowd buries the one document that answers it"
    assert filtered.index(0) <= unfiltered.index(0), "dropping stopwords does not make it worse"
    assert gated == [0], "searching ONLY the rare term is what actually rescues it"


def test_stopword_filtering_reuses_the_one_list_the_project_already_has():
    """A second stopword list would be a second source of truth for 'what carries no signal'."""
    assert "the" not in query_terms("the report", drop_stopwords=True)
    assert "của" not in query_terms("của báo cáo", drop_stopwords=True)
    assert query_terms("the report", drop_stopwords=False) == ["the", "report"]


def test_query_terms_are_deduplicated():
    assert query_terms("report report report", drop_stopwords=True) == ["report"]


# ------------------------------------------------------------------ the rare-term gate


def test_the_gate_fires_only_on_queries_bm25_is_actually_for():
    """`config.py` promised this and nobody built it: *the lexical index stays OFF until real
    traffic shows queries where those terms actually appear.*"""
    index = BM25.build(DOCS)
    rare = index.rare(query_terms("what is GMROI", drop_stopwords=True), max_df_ratio=0.25)
    assert rare == ["gmroi"]
    # a question made of words the corpus is saturated with has nothing for BM25 to add
    common = index.rare(
        query_terms("the management of the report", drop_stopwords=True), max_df_ratio=0.25
    )
    assert common == []


def test_the_gate_ignores_a_rare_word_the_corpus_does_not_contain():
    """df == 0 is not 'rare', it is absent — gating on it would fuse an empty ranking."""
    index = BM25.build(DOCS)
    assert index.rare(["kryptonite"], max_df_ratio=0.5) == []


# ------------------------------------------------------------------ fusion


def test_rrf_fuses_by_rank_and_needs_no_shared_scale():
    """Cosines crowd into 0.87–0.90 (D-028) and BM25 scores are on an unrelated scale, so any
    weighted sum would be calibrating noise."""
    assert rrf([[1, 7, 2], [1, 3, 7]], top_k=2) == [1, 7]
    assert rrf([[5, 6], []], top_k=2) == [5, 6], "an empty ranking degrades cleanly, not to garbage"
    assert rrf([], top_k=3) == []


def test_a_document_both_rankers_agree_on_beats_one_each_ranker_tops_alone():
    """Corroboration is the whole reason to fuse. Document 1 is never ranked first by EITHER
    retriever and still wins, because both put it second — which is a stronger signal than one
    enthusiastic ranker and one that never heard of it."""
    assert rrf([[7, 1], [8, 1]], top_k=1) == [1]


def test_dense_rankings_are_ordered_by_cosine():
    import numpy as np

    docs = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float32)
    qs = np.array([[1.0, 0.0]], dtype=np.float32)
    assert dense_rankings(docs, qs, top_k=3) == [[0, 2, 1]]


# ------------------------------------------------------------------ the arms


def test_every_arm_produces_a_ranking_and_the_gate_reports_its_selectivity():
    index = BM25.build(DOCS)
    queries = ["what is GMROI", "the management of the report"]
    dense = [[1, 0, 2], [2, 1, 0]]

    _, plain = rank_arm("hybrid", index=index, queries=queries, dense=dense, top_k=3)
    _, gated = rank_arm(
        "hybrid-rare", index=index, queries=queries, dense=dense, top_k=3, max_df_ratio=0.25
    )
    assert plain.fused == 2, "today's hybrid fuses on every query, informative or not"
    assert gated.fused == 1, "the gate spends BM25 only where a rare term actually occurs"


def test_the_dense_arm_is_exactly_the_dense_ranking():
    """The baseline must be untouched, or every comparison against it is meaningless."""
    index = BM25.build(DOCS)
    dense = [[3, 1, 0]]
    ranked, plan = rank_arm("dense", index=index, queries=["anything"], dense=dense, top_k=3)
    assert ranked == dense and plan.fused == 0


def test_cli_arm_names_do_not_drift_from_the_probe():
    from libkb.cli import _LEX_ARMS, _LEX_DEFAULT_ARMS
    from libkb.evals.lexical import DEFAULT_ARMS

    assert tuple(ARMS) == _LEX_ARMS
    assert _LEX_DEFAULT_ARMS == DEFAULT_ARMS


@pytest.mark.parametrize("arm", list(ARMS))
def test_no_arm_crashes_on_an_empty_or_stopword_only_query(arm):
    index = BM25.build(DOCS)
    ranked, _ = rank_arm(arm, index=index, queries=["", "the of and"], dense=[[0], [1]], top_k=3)
    assert len(ranked) == 2
