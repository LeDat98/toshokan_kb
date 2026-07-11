---
id: nd_01KX82V9MBH4B5PCZ84WWARN76
title: Query Rewriting & Expansion
source_ref: seed
---

User questions are often poor retrieval queries: too short, ambiguous, or phrased in
vocabulary that does not match the corpus. Query rewriting uses an LLM to transform
the question before retrieval.

**Multi-query** generates several paraphrases and merges their results, improving
recall. **HyDE** (Hypothetical Document Embeddings) asks the model to draft a
hypothetical answer and retrieves by the draft's embedding — matching document
language instead of question language. **Step-back prompting** first abstracts the
question ('what general topic is this about?') to retrieve background context.
All add one LLM call of latency; use them when baseline recall, not precision,
is the bottleneck.
