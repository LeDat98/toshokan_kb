---
id: nd_01KX80W5TGFJ0W7AF5R0MZQND2
title: Chunking Strategies
source_ref: seed
---

Chunking splits documents into retrievable units. **Fixed-size** chunking (e.g. 512
tokens with 10–15% overlap) is simple and predictable but cuts across semantic
boundaries. **Structure-aware** chunking follows headings, paragraphs and code blocks,
preserving meaning at the cost of variable sizes. **Semantic** chunking groups
sentences by embedding similarity, producing coherent units but at higher indexing
cost.

The trade-off: small chunks improve retrieval precision but lose surrounding context;
large chunks preserve context but dilute the embedding and waste prompt budget.
A common compromise is structure-aware splitting targeting 400–1200 tokens, with
parent-document retrieval when more context is needed at generation time.
