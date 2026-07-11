---
id: nd_01KX80W5TWQ3V36N3HQ6JW1DQ9
title: Embeddings & Indexing
source_ref: seed
---

Dense retrieval maps text to vectors so that semantic similarity becomes geometric
proximity, usually cosine similarity over L2-normalized embeddings. Quality depends
on the embedding model and on task-appropriate encoding (query vs document modes).

At scale, exact nearest-neighbor search is too slow, so approximate indexes are used:
**HNSW** (graph-based, fast and accurate, memory-hungry) and **IVF** (cluster-based,
cheaper, needs tuning). Most production systems combine the vector index with
metadata filters (source, date, access level) applied pre- or post-search.
Index freshness matters: embeddings must be recomputed when content or the
embedding model changes.
