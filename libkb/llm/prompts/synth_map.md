You are surveying the library for one question. Read the ONE document below and extract ONLY what it
contributes to answering that question — a short, factual finding in one or two sentences, drawn
STRICTLY from this document. Never use your own knowledge, and never invent a figure or claim the
document does not state.

Question:
{{query}}

Document:
<<<
{{document}}
>>>

Do NOT answer the whole question — just this document's piece of it. If this document contributes
nothing to the question, return {"relevant": false}.

Return JSON: {"relevant": true|false, "finding": "<this document's contribution, or empty>"}
