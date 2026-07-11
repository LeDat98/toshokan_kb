---
id: nd_01KX82V9R3GKESCHQ4PE1D5QRG
title: Transformer Architecture
source_ref: seed
---

Modern LLMs are decoder-only transformers: a token embedding layer followed by a
stack of identical blocks, each combining multi-head self-attention with a
position-wise MLP, wrapped in residual connections and layer normalization.
Positional information comes from schemes like RoPE rather than learned absolute
positions.

Generation is autoregressive: the model predicts one next token at a time,
conditioning on everything before it. Depth gives compositional power, width gives
capacity; both are bounded in practice by the memory and latency of attention over
long contexts.
