---
id: nd_01KX82V9N88M982YYFNTMB6XAD
title: Reranking & Cross-encoders
source_ref: seed
---

Reranking is a second scoring pass over the top-k candidates from first-stage
retrieval. First-stage **bi-encoders** embed query and document separately, so
scoring is a cheap vector comparison — fast but approximate. A **cross-encoder**
reads the query and a candidate *together* through one transformer, modeling
token-level interaction between them, which is far more accurate but too expensive
to run over the whole corpus.

Hence the two-stage design: retrieve ~50–100 candidates cheaply, rerank the top
10–20 with the cross-encoder, keep the best 3–5 for the prompt. Reranking typically
adds 100–500 ms but is often the single highest-leverage precision upgrade in a RAG
stack. Alternatives include LLM listwise reranking (prompt the model to order
candidates) and late-interaction models like ColBERT, which sit between the two
extremes in cost and quality.
