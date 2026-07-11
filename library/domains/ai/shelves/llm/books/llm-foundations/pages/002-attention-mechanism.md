---
id: nd_01KX80W5Z8Y0R9EWXJD0QR6ZT6
title: Attention Mechanism
source_ref: seed
---

Self-attention lets each token gather information from all previous tokens. Each
token produces a query (Q), key (K) and value (V) vector; attention weights are
softmax(QKᵀ/√d), and the output is the weighted sum of values. **Multi-head**
attention runs several such projections in parallel so different heads can track
different relations (syntax, coreference, position).

Attention cost grows quadratically with sequence length, which is why long-context
inference relies on the **KV cache**: keys and values of past tokens are stored so
each new token only computes its own Q against cached K/V. The cache is also why
prompt prefixes can be reused cheaply across calls.
