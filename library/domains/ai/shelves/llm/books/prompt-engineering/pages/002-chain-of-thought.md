---
id: nd_01KX82V9TSG12P0BAJTJGQSNM2
title: Chain-of-Thought
source_ref: seed
---

Chain-of-thought (CoT) prompting asks the model to reason step by step before
answering. It helps on tasks with multi-step structure — arithmetic, logic, planning,
multi-hop questions — because intermediate tokens give the model working memory.

On simple lookup or extraction tasks CoT mostly adds latency and cost. Verbosity is
not accuracy: models can produce confident-looking reasoning that is wrong, so for
high-stakes use pair CoT with verification (self-consistency voting, or a separate
checker pass). Reasoning-tuned models internalize much of this, making explicit CoT
prompts less necessary.
