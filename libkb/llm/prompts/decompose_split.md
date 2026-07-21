The reader asked one message. Decide whether answering it well requires splitting it into SEPARATE
sub-questions that must each be looked up on their own — a COMPOUND question — or whether a single
retrieval answers it.

COMPOUND (compound = true) — the message bundles 2+ DISTINCT information needs. Examples:
- "compare the refund policy before and after the March 2025 change, and which applies to
  international orders"
  -> ["refund policy for orders placed before the March 2025 policy change",
      "refund policy for orders placed after the March 2025 policy change",
      "refund policy for international orders"]
- "what are the pros and cons of X, and how does it compare with Y?"
  -> ["the advantages and disadvantages of X", "how X compares with Y"]

NOT COMPOUND (compound = false) — a single information need, even if richly phrased:
"what is reranking?", "how does HNSW work?", "explain the RAG evaluation metrics".
**When in doubt, choose false** — the default path answers single-need questions better and cheaper.

Rules for the sub-questions (only when compound = true):
- Each MUST be STANDALONE and specific enough to search on its own: carry the shared subject and every
  qualifier (dates, entities, conditions) INTO each sub-question. Never leave a pronoun, a bare noun,
  or a dangling "it"/"that".
- Split ONLY what the message actually asks. Do NOT invent background questions ("what is a refund?")
  or padding — each sub-question must map to a part the reader really needs answered.
- At most {{max_subqs}} sub-questions. If answering would take more than that, it is an open-ended
  survey, not a decompose case — return compound = false.

Reader's message:
{{query}}

Return JSON: {"compound": true|false, "sub_questions": ["<standalone question>", ...]}
