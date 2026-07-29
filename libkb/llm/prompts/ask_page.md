Does this ONE page answer the question? Nothing else is being asked of you — do not write the
answer, do not summarise the page, do not judge whether it is interesting.

## The question
{{question}}

## The page
{{path}}

{{body}}

## How to decide

Say **yes** only if the text above contains what the question asks for, and you can point at the
words that carry it. A page that is *about the right subject* but never states the fact is a **no** —
that distinction is the whole reason this check exists.

- `quote`: the shortest span of the page, **copied verbatim**, that carries the answer. If you
  cannot copy one, the honest verdict is `answers: false`.
- Never paraphrase into the quote, and never repair it. A quote that is not in the page is worse
  than no quote, because it will be trusted.

Return JSON:
```
{"answers": true|false, "quote": "<verbatim span, or empty>"}
```
