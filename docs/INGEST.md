# LibraryKB — Ingest design (the rulebase)

> How any source — a clean folder, a raw PDF, an HTML page, a URL — becomes
> `Domain ▸ Shelf ▸ Book ▸ TOC ▸ Page` in the library. Written in English (durable doc);
> see `docs/ARCHITECTURE.md` for the Vietnamese overview.

## 1. One pipeline, not many paths

There is a single ingest pipeline. What differs per source is **how much structure the source
already carries** — the pipeline detects that and only asks the AI to fill what's missing. This
is the rulebase: **rules define the frame (the 5 levels); the AI executes only the fuzzy gaps.**

```
source ──► SURVEY ──► DraftTree(provided / missing) ──► RESOLVE gaps ──► COMMIT ──► library
             │            │                                   │              │
        (deterministic    detect which of the 5          fill missing    write nodes,
         extraction)      levels the source gives         slots (rules    toc, pages;
                                                          first, AI when   rebuild views;
                                                          needed, gate      index catalog
                                                          the risky ones)
```

The intermediate `DraftTree` is the contract between stages. A source populates the slots it can;
the resolver fills the rest; the committer writes it into `LibraryStore`. PDF and folder differ
only in how full their DraftTree arrives.

## 2. The five slots — provided vs. missing

| Slot | Provided when the source has… | If missing, filled by |
|------|-------------------------------|-----------------------|
| **Domain** | (rarely in a source) | User flag `--domain`, **or** AI proposes vs. existing domains (create-if-missing) — **gated** |
| **Shelf** | (almost never explicit) | AI groups books into themes, **or** a rule strategy (single / by-priority) |
| **Book** | a sub-folder, or a whole file | (rarely missing — a file with no structure is still one book) |
| **TOC / Pages** | `.md` files in a folder, or headings in a doc | AI splits an unstructured doc into pages + proposes titles |
| **Page title** | frontmatter `title`, first `#` heading, filename | AI proposes from content |
| **Page one-line / desc** | frontmatter `description` | AI generates (or leave for `rebuild-views`) |

**Accuracy principle:** where the source *provides* a slot, we extract it deterministically and do
**not** let the AI second-guess it. The AI's workload scales exactly to what's missing — near-zero
for a clean folder, substantial for a raw PDF. This is why a well-structured import is ~100%
accurate: there is almost nothing for the AI to get wrong.

## 3. Source shapes and their DraftTree

| Source | Domain | Shelf | Book | Pages | AI does |
|--------|--------|-------|------|-------|---------|
| **Clean folder** (retail: `topic/*.md`) | flag | **missing** | each sub-folder | each `.md` (title+desc from frontmatter) | group shelves only |
| **Deep folder** (`domain/shelf/book/*.md`) | folder or flag | folders | folders | files | nothing |
| **Structured doc** (PDF/md with headings) | AI-propose | AI-propose | the file | split on `#`/`##` | placement + shelf |
| **Raw doc** (PDF with no headings) | AI-propose | AI-propose | the file | AI splits + titles | everything but the book |

### Folder depth rule
The importer maps folder depth onto the tree by the **role of the root you point at**:
- point at a folder declared `--domain X` → its child folders are **books**, files are **pages**
  (retail case → shelf slot is missing → AI/rule fills it).
- a folder one level deeper (`domain/shelf/book/*.md`) → child folders are **shelves**, their
  children **books**, files **pages** (nothing missing).
Detection: a folder whose children are folders-of-folders implies an extra container level.

## 4. Import vs. ingest — the two entry points (same pipeline)

- **`libkb import <folder> --domain X`** — the folder already encodes structure. SURVEY is
  deterministic; RESOLVE fills only the shelf slot; no LLM required for placement. Fast, free,
  reproducible. This is for corpora like the retail knowledge folder.
- **`libkb ingest <file|url>`** — a single document. SURVEY extracts what headings/metadata exist;
  RESOLVE runs the **classifier** (top-down placement against the live tree, create-if-missing) and
  splits pages when the doc is unstructured. LLM-driven; risky slots gated.

Both build a DraftTree and commit it the same way.

## 5. "Import the folder or the files?" — both, by role

You import at the **folder** level; the folder gives the *container* structure (shelf/book) and the
files give the *page* content. You never import loose files without a container decision — a file
always lands as a page inside a book. Point the importer at the top folder and declare its role;
recursion + the depth rule do the rest.

## 6. Physical storage (already built in P0)

The library is a **filesystem tree** under `library/`, mirroring the logical tree. Import **copies
content into this canonical store** — it does not read the source in place (the source may be a PDF
to convert; the library needs its own ids/toc/metadata; stable-ids P5 + reshelving P8 require the
library to own the layout). A retail page lands like:

```
SOURCE (input only, gitignored):
  Knowledge_Research-main/.../knowledge/P0_KPI_Dictionary/Inventory_Turnover_....md

LIBRARY (canonical, git-committed):
  library/domains/retail/shelves/metrics-kpis/books/kpi-dictionary/
    _meta.json                         # book card
    toc.json                           # page entries (title, one_line, keywords)
    pages/005-inventory-turnover.md    # LibKB frontmatter (id, title, source_ref) + body
```

- Markdown + JSON = source of truth, git-committed (human-inspectable; the library *is* its
  storage metaphor). `library/_catalog/catalog.db` (SQLite: embeddings, trajectories) is
  regenerable → gitignored. (Decision D-002.)
- **Page body** = the source's markdown **content** with its YAML frontmatter stripped (metadata,
  not prose). Extracted title/description/keywords go into the TOC entry + page frontmatter. The
  reading body stays clean. ("Keep the page intact" = keep the prose/tables/sections, not the YAML
  header.) Rich source metadata we don't model yet (sources, confidence, related_kpis,
  business_value_score) is preserved into the page's LibKB frontmatter as pass-through fields where
  scalar; structured blocks are referenced via `source_ref` back to the original.

## 7. Naming & normalization rules

- **Slug**: `store.slugify` (kebab-case ASCII; Vietnamese transliterated; original kept in `title`).
- **Book title from folder**: strip a leading priority prefix (`P0_`, `P1_`, `P2_`) and turn
  `_`/spaces into a clean Title (e.g. `P0_KPI_Dictionary` → "KPI Dictionary"). The stripped priority
  is retained as page/book metadata, usable by the `by-priority` shelf strategy.
- **Page title**: frontmatter `title` → first `#` heading → humanized filename.
- **Filenames with spaces** are handled (the retail folder mixes `_` and spaces).
- **Keywords**: from frontmatter `related_kpis`/`keywords` (capped ~6) for the TOC entry.

## 8. Shelf strategies (filling the always-missing shelf slot)

Because the physical model requires a shelf between domain and book (`VALID_CHILD[domain]={shelf}`),
every import must create ≥1 shelf. Strategies:

- `single` (deterministic): one shelf, name from `--shelf-name` (default "General"). Let the P4
  split-loop divide it later when it grows.
- `priority` (deterministic): group books by their `P0/P1/P2` prefix → shelves "P0 Core" / "P1" /
  "P2". Zero LLM, but priority is a business axis, weaker for topical navigation.
- `auto` (LLM, default for import): the model reads the book titles + one-lines and proposes a
  handful of **discriminative** thematic shelves (title + description + members). This is the AI
  "filling the gap" the rulebase identified. One bounded call; the result is reviewable.

## 9. Confidence gate & review (P10) — for the risky slots

Creating a **new top-level domain** or a placement the model is unsure of is high-stakes and must
not be silent. When RESOLVE's confidence for a slot is below `LIBKB_INGEST_CONFIDENCE_GATE` (0.70):
- the book is parked under the `_uncatalogued` shelf,
- it surfaces in the Ingest **review queue** UI with the proposed path + rationale,
- the human approves / edits before it enters the main tree.
Confidence for a placement chain = **min over levels** (weakest link). Deterministic imports skip
the gate for the slots the folder provided (nothing to be unsure about).

## 10. Idempotency & re-runs

- Domain/shelf/book are **get-or-created by slug** under their parent — re-importing reuses existing
  containers instead of colliding.
- A page whose slug already exists in its book is **skipped** (reported), unless `--replace`.
- Source identity is the content hash + `source_ref`; a changed source updates in place (P2b).

## 11. Pipeline stages → modules

| Stage | Module | LLM? |
|-------|--------|------|
| Survey (folder) | `ingest/survey.py` | no |
| Parse (pdf/html/url) [P2b] | `ingest/parse.py` | no |
| Split unstructured doc [P2b] | `ingest/split.py` | yes |
| Resolve shelves / placement | `ingest/resolve.py` | `auto`/classify only |
| Commit to store | `ingest/importer.py` (`commit`) | no |
| Descriptions (views) | `library/views.py` | yes (opt / `rebuild-views`) |
| Questions flywheel [P2c] | `ingest/questions.py` | yes |
| Catalog index [P2c] | `catalog/` | embeds |

## 12. Delivery order

- **P2a — import** (this pass): survey folder → DraftTree → resolve shelves → commit; `libkb import`;
  load the retail folder for real. Deterministic core; `auto` shelf grouping optional.
- **P2b — ingest a document**: `parse` (pdf via pymupdf4llm, html/url via trafilatura) → `split`
  (structure-aware) → `classify` placement + confidence gate → `_uncatalogued` + review queue.
- **P2c — flywheel + catalog**: generate vi+en questions per page → SQLite catalog + embeddings →
  `search.lookup` → `ask_librarian` tool + lookup shortcut in the orchestrator.
