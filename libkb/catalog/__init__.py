"""The card catalog (P2c): SQLite-backed question embeddings for fast entry-point lookup.

`store.Catalog` owns storage + brute-force cosine search; `search.lookup` is the query-side
helper (embed the question, rank, threshold). Kept behind one API so a real vector index
(sqlite-vec) can slot in later without touching callers — see decision D-002.
"""
