---
id: nd_01KX82V9T8HZXEG748BBDT3PNS
title: Few-shot Prompting
source_ref: seed
---

In-context examples steer a model without changing weights. **Zero-shot** relies on
instructions alone; **few-shot** prepends worked examples that fix the task's format,
style and edge-case handling.

What matters most is example *selection* and *format consistency*: examples similar
to the current input help; inconsistent labels or formatting actively hurt. Order
effects are real — models weight later examples more. For classification, cover the
label space evenly to avoid biasing the prior. Few-shot competes with instruction
quality: with strong instructions and schemas, fewer examples are needed.
