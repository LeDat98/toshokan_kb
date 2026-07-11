---
id: nd_01KX82V9MV6G67P6QQWJZKSS9J
title: Hybrid Search: BM25 + Dense
source_ref: seed
---

Lexical search (BM25) matches exact terms — strong for identifiers, names, and rare
keywords, but blind to synonyms. Dense retrieval matches meaning — strong for
paraphrases, but it can miss exact tokens like error codes or function names.

Hybrid search runs both and fuses results, most simply with **Reciprocal Rank
Fusion**: score(d) = Σ 1/(k + rank_i(d)) across the ranked lists, k≈60. RRF needs no
score calibration between systems, which is why it is the default fusion choice.
Hybrid + reranking is the standard recipe for technical corpora where both jargon
and paraphrase queries occur.
