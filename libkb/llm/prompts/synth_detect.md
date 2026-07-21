The reader asked a question. Decide whether answering it WELL requires reading and combining
information from MANY documents (an AGGREGATIVE question), or whether one focused passage would
answer it (a single-fact question).

AGGREGATIVE (aggregative = true) — the answer is a synthesis across sources:
- "what techniques for X appear across the library?"
- "what are the common themes in Y?"
- "compare how the different books approach Z"
- "summarise the trends in the <domain> domain"
- "what are ALL the ... / list every ... across ..."

SINGLE-FACT (aggregative = false) — one page can answer it:
- "what is reranking?"        - "how does HNSW work?"        - "what did paper P conclude?"

**When in doubt, choose false.** The library's default path answers single-fact questions better and
far more cheaply; only send the genuinely cross-document questions here.

"scope" is the name of a domain, shelf, or book the question is confined to (e.g. "AI-News", "RAG"),
or empty if it ranges over the whole library.

Reader's message:
{{query}}

Return JSON: {"aggregative": true|false, "scope": "<name or empty>"}
