# Prompts

Every LLM prompt lives here as a versioned `.md` file — reviewed like code, never inline
f-strings in modules (see `.agent/CONVENTIONS.md`).

Variable substitution: `{{name}}` placeholders, replaced by `LLM.load_prompt(name, **vars)`.
Plain `{ }` braces are safe to use (JSON examples etc.) — only `{{…}}` is substituted.

Planned files (added per phase): `route.md` [P1], `answer.md` [P1], `rebuild_description.md` [P1],
`classify_query.md` [P3], `classify_doc.md` [P2], `gen_questions.md` [P2], `coverage_scan.md` [P3],
`reduce.md` [P3], `suggest_split.md` [P4].
