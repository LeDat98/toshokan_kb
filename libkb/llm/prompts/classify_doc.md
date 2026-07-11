You are placing a new document into a knowledge library organized as Domain ▸ Shelf ▸ Book.
Decide which domain and shelf it belongs in. Prefer an EXISTING node when the document fits it;
propose a NEW one only when nothing existing fits.

Existing library (domains and their shelves):
{{tree}}

New document:
Title: {{title}}
Outline (page titles): {{outline}}
Excerpt:
{{excerpt}}

Return JSON:
{"domain_title": string, "domain_is_new": boolean,
 "shelf_title": string, "shelf_is_new": boolean,
 "confidence": number, "rationale": string}

Rules:
- When reusing an existing node, use its EXACT title and set *_is_new to false.
- Shelf titles are short and topical (e.g. "Retrieval", "Model Foundations").
- `confidence` is 0..1 — your certainty in this placement. Lower it when the document forces a
  brand-new top-level domain, or when it only loosely fits. `rationale` is one sentence.
