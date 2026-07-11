You are organizing a domain's books onto shelves in a knowledge library. Group the books below
into a small number of DISCRIMINATIVE thematic shelves — the way a librarian would, so a reader
can tell at a glance which shelf holds what.

Domain: {{domain}}

Books (title — what it covers):
{{books}}

Rules:
- Produce {{min_shelves}}–{{max_shelves}} shelves. Every book goes on exactly one shelf.
- Shelf titles are short and topical (e.g. "Metrics & KPIs", "Inventory & Replenishment"),
  NOT priority labels.
- Each shelf description is one discriminative sentence: what it covers and, where useful, what
  it does NOT (pointing to a sibling shelf).
- Use each book's exact title in `books`.

Return JSON:
{"shelves": [{"title": string, "description": string, "books": [exact book titles]}]}
