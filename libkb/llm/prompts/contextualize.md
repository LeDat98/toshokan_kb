A reader is in an ongoing conversation with a library assistant. Decide whether their NEW message is
a FOLLOW-UP that only makes sense given the recent turns — and if so, rewrite it into a STANDALONE
question that carries all the context it needs, so it can be searched on its own.

FOLLOW-UP (followup = true) — depends on the history to be understood:
- "tell me more about it" (what is "it"?)  → resolve the referent from the history
- "and in Japanese?" / "what about for images?" → carry the prior topic forward
- "why?" / "give an example" → attach the prior subject

STANDALONE (followup = false) — already complete on its own; return it unchanged:
- a fresh topic, a full question, a greeting, anything that reads fine with no history.
**When in doubt, choose false** — never invent a connection that isn't there.

Rewrite rules: keep the reader's intent and language; resolve pronouns/ellipsis using the history;
add nothing the reader didn't imply. Do NOT answer the question — only rewrite it.

Recent conversation:
{{history}}

New message:
{{query}}

Return JSON: {"followup": true|false, "standalone": "<the self-contained question, or empty>"}
