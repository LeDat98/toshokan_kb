---
id: nd_01KX80W61X3FJM7FBX45W8EQFW
title: Structured Output & JSON Mode
source_ref: seed
---

Programs need parseable output. **JSON mode / structured output** constrains
generation to a schema — either by constrained decoding (the sampler masks tokens
that would break the grammar) or by validation-and-retry at the application layer.

Practical rules: keep schemas flat and small; describe each field, because field
names and descriptions act as prompts; make enums explicit rather than free text.
Even with schema enforcement, values can be semantically wrong — validate
post-parse and retry once with the error message included. Structured output pairs
naturally with function calling, where the schema is the tool signature.
