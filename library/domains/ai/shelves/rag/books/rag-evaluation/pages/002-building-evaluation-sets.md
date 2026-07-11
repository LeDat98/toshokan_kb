---
id: nd_01KX80W5XWEA126WK7W9S9YFFQ
title: Building Evaluation Sets
source_ref: seed
---

An evaluation set is question–evidence pairs: a query plus the passages that answer
it. The cheapest source is **synthetic generation**: for each chunk, ask an LLM to
write questions that the chunk answers, phrased the way a real user would ask —
this doubles as a routing test, since the ground-truth location is known by
construction.

Add a small **golden set** of real, human-verified questions for calibration, and
re-run the full suite on every pipeline change (chunking, embedding model, index).
Watch for leakage: if the question copies the chunk's exact wording, retrieval looks
artificially perfect — paraphrase during generation.
