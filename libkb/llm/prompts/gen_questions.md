You are building the card catalog for a knowledge library. For the page below, write the
questions a real user would type that THIS page answers well — the exact phrasings someone
would search with, in their own words (not the page's own wording).

Book: {{book}}
Page title: {{title}}
Page content:
{{content}}

Return JSON:
{
  "one_line":  "<spine label, English, <= 120 chars>",
  "keywords":  ["<up to 6 keywords>"],
  "questions": [{"vi": "<question in Vietnamese>", "en": "<the same question in English>"}],
  "terms":     [{"vi": "<term ring in Vietnamese>", "en": "<term ring in English>"}]
}

## one_line — the SPINE LABEL
What is printed on the spine of a book so a browser can pick it off the shelf. It is NOT an
abstract and NOT a summary.

- One clause. Under 120 characters. English. No trailing full stop.
- It must DISTINGUISH this page from its neighbours on the same shelf — say what is specific to it,
  not what is true of the whole subject. "How RAG works" is useless if every page is about RAG.
- Name the concrete thing: the metric, the model, the formula, the decision it supports.

## keywords
Up to 6. The nouns a cataloguer would file this page under — entities, metrics, algorithms,
standards. No generic words.

## questions
- Produce exactly {{n}} question intents. Each intent has BOTH a Vietnamese and an English
  phrasing of the SAME question — a bilingual vocabulary bridge to the same page.
- Ask what a user wants to know, using everyday words and synonyms — do NOT reuse the page's
  headings verbatim.
- Every question must be answerable from THIS page alone. No yes/no questions.
- Keep each question to one sentence.

## terms — the ENTRY VOCABULARY
A reader does not arrive with the library's words. They arrive with their own: a synonym, an
abbreviation, a brand name, the wrong-but-close term a beginner reaches for. The term ring is the
set of words that should lead HERE.

- Produce 1–2 term rings. Each is a short ` · `-separated list of the words and phrases that point
  at this page's subject: the canonical term, its abbreviation and expansion, common synonyms,
  a beginner's imprecise name for it, and any named entities the page is really about (algorithms,
  models, metrics, standards, product or SKU codes).
- Example: `reranking · cross-encoder · re-rank · sắp xếp lại kết quả · ColBERT · MonoT5`
- Include the terms a reader would use even if this page never uses them itself. That is the point.
- Do NOT pad with generic words ("data", "system", "analysis") — a term that leads everywhere leads
  nowhere.
