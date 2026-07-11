# LibraryKB — Detailed Function Design

Python 3.11+ · FastAPI · `google-genai` SDK · pydantic v2 · SQLite · filesystem library store.
Package name: `libkb`. Each function below is tagged with its delivery phase `[P0..P4]`.

```
libkb/
  config.py            # Settings (.env)
  llm/
    client.py          # single gateway to Gemini
    prompts/           # *.md prompt templates (versioned like code)
  library/
    models.py          # NodeMeta, NodeCard, TOC, PageContent, Redirect
    store.py           # LibraryStore — fs tree CRUD
    views.py           # materialized-view descriptions (P1 principle)
    aliases.py         # see-also childless redirects
  catalog/
    db.py              # SQLite schema + connection
    store.py           # questions + embeddings CRUD
    search.py          # semantic lookup over questions
  ingest/
    parse.py           # source → markdown
    split.py           # markdown → DraftBook (chapters/pages)
    classify.py        # placement into the tree (confidence-gated)
    questions.py       # question flywheel generation
    pipeline.py        # orchestrates ingest end-to-end
  agent/
    tools.py           # navigator tool defs + hard budget enforcement
    navigator.py       # the walking librarian (isolated context)
    classifier.py      # front-door query classifier
    synthesizer.py     # coverage scan + map-reduce for synthesis
    answerer.py        # evidence → cited answer / honest NOT_FOUND
    orchestrator.py    # entry point: strategy dispatch + streaming events
  trajectory/
    logger.py          # walk recording
    analyzer.py        # misroute mining → suggestions
  evals/
    runner.py          # routing eval over generated questions
    gates.py           # regression gate for tree refactors
  maintenance/
    rebalance.py       # split/merge (offline, eval-gated)
  api/
    main.py            # FastAPI app factory
    routes/            # query, library, ingest, admin
    events.py          # SSE event models shared with UI
  cli.py               # `libkb` CLI: init, seed, ingest, ask, eval
```

---

## 1. `config.py` [P0]

```python
class Settings(BaseSettings):
    # matches existing .env entry `Gemini_API_Key` (case-insensitive, spaces ok)
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    model: str = "gemini-3.5-flash"          # LIBKB_MODEL
    model_lite: str = "gemini-3.5-flash"     # LIBKB_MODEL_LITE
    embed_model: str = "gemini-embedding-001"
    library_dir: Path = Path("./library")
    db_path: Path = Path("./library/_catalog/catalog.db")
    max_hops: int = 12
    max_pages_per_nav: int = 6
    max_ask_librarian: int = 2
    ingest_confidence_gate: float = 0.7
    questions_per_page: int = 4
    question_langs: tuple[str, ...] = ("vi", "en")
    branching_split_threshold: int = 50      # children count that triggers split suggestion

def get_settings() -> Settings   # lru_cached; model_config: env_file=".env", case_sensitive=False, populate_by_name=True
```

## 2. `llm/client.py` [P0]

The **only** module allowed to import `google.genai`. Everything else calls through here.

```python
@dataclass
class LLMResult:
    text: str | None
    tool_calls: list[ToolCall]      # [] when plain text
    usage: Usage                    # input/output tokens, model, latency_ms

class LLM:
    def generate(self, messages, *, model=None, system=None, tools=None,
                 json_schema=None, temperature=0.2) -> LLMResult
        # retries: 3x exponential backoff on 429/5xx; raises LLMError after
        # json_schema → response_schema (structured output); validates + one repair retry
    def embed(self, texts: list[str], *, task="RETRIEVAL_DOCUMENT") -> np.ndarray  # (n, dim) float32, L2-normalized
    def load_prompt(self, name: str, **vars) -> str   # reads llm/prompts/<name>.md, formats {vars}

def get_llm() -> LLM  # singleton
```

Prompt files [P0–P3]: `route.md`, `classify_query.md`, `classify_doc.md`, `gen_questions.md`,
`rebuild_description.md`, `answer.md`, `coverage_scan.md`, `reduce.md`, `suggest_split.md`.
Rule: prompts are code — reviewed, versioned, never inline f-strings in modules.

## 3. `library/models.py` [P0]

```python
NodeKind = Literal["domain", "shelf", "book", "page"]
NodeID   = str   # "nd_" + ULID; immutable, never reused (P5)

class NodeRef(BaseModel):    id: NodeID; kind: NodeKind; title: str; slug: str
class SeeAlso(BaseModel):    target: NodeRef; note: str; origin: Literal["manual", "misroute"]

class NodeMeta(BaseModel):
    id: NodeID; kind: NodeKind; slug: str; title: str
    description: str            # materialized view — write only via views.py (P1)
    description_rev: int
    parent_id: NodeID | None
    see_also: list[SeeAlso]
    stats: NodeStats            # n_shelves, n_books, n_pages, last_ingest_at
    uncatalogued: bool = False
    created_at / updated_at: datetime

class NodeCard(BaseModel):      # the unit a navigator reads in a menu — keep SMALL
    id: NodeID; kind: NodeKind; title: str
    one_line: str               # ≤ 160 chars, discriminative vs siblings
    stats_line: str             # "3 shelves · 12 books"
    see_also: list[str]         # rendered "for X, see <path>" hints

class TOCEntry(BaseModel):   page_id: NodeID; title: str; one_line: str; keywords: list[str]
class TOC(BaseModel):        book_id: NodeID; chapters: list[Chapter]  # Chapter = title + entries
class PageContent(BaseModel): page_id: NodeID; book_id: NodeID; title: str; markdown: str; source_ref: str | None
class Redirect(BaseModel):   old_id: NodeID; new_id: NodeID; reason: Literal["move", "split", "merge"]; at: datetime
```

## 4. `library/store.py` — `class LibraryStore` [P0]

Filesystem-backed tree. All writes atomic (write temp + rename). Raises `NodeNotFound`,
`InvalidParent`, `SlugCollision`.

```python
def init_library() -> None                       # create skeleton + root _meta.json
def get(self, node_id: NodeID) -> NodeMeta       # follows redirects transparently (P5); logs when followed
def children(self, node_id: NodeID) -> list[NodeCard]   # THE MENU — sorted, includes see_also hints
def toc(self, book_id: NodeID) -> TOC
def page(self, page_id: NodeID) -> PageContent
def path_of(self, node_id: NodeID) -> list[NodeRef]     # breadcrumb root→node, for citations (P6)
def create(self, parent_id, kind, title, description="") -> NodeMeta   # validates kind vs parent kind
def write_page(self, book_id, title, markdown, *, position=None, source_ref=None) -> NodeMeta
def write_toc(self, book_id, toc: TOC) -> None
def move(self, node_id, new_parent_id, *, reason="move") -> None       # writes Redirect row (P5)
def set_description(self, node_id, text, rev) -> None    # ONLY views.py may call (enforced by convention + test)
def iter_subtree(self, node_id) -> Iterator[NodeMeta]
def recompute_stats(self, node_id) -> None               # bubble counts up ancestors
def resolve_path(self, human_path: str) -> NodeID        # "ai/rag/advanced-rag" → id (for CLI/admin)
```

## 5. `library/views.py` [P1] — principle P1 lives here

```python
def rebuild_description(node_id) -> str
    # input: node title + children NodeCards ONLY (bounded by branching factor)
    # prompt rebuild_description.md — REQUIREMENTS:
    #   discriminative vs siblings (receives sibling cards too),
    #   includes "does NOT cover X — see Y" when see_also exists,
    #   ≤ 90 words. Regenerate from scratch; never patch. Bumps description_rev.
def propagate_up(node_id) -> list[NodeID]        # rebuild ancestors chain to root; returns touched
def rebuild_all(root_id=ROOT) -> RebuildReport   # bottom-up full re-derivation (disaster recovery)
def rebuild_toc_lines(book_id) -> None           # one_line + keywords per page from page content
```

## 6. `library/aliases.py` [P2]

```python
def add_see_also(node_id, target_id, note, origin) -> None   # childless pointer only (P4); cycle-check
def remove_see_also(node_id, target_id) -> None
# NOTE: creation is normally demand-driven from trajectory.analyzer (P9); manual add allowed via admin
```

## 7. `catalog/` [P2]

`db.py`: SQLite (WAL) tables —
`questions(id, page_id, book_id, text, lang, embedding BLOB, created_at)` ·
`redirects(old_id, new_id, reason, at)` ·
`trajectories(id, query, qtype, status, hops, backtracks, duration_ms, answered_at)` ·
`hops(traj_id, seq, node_id, action, note)` · `eval_runs(id, at, overall, report_json)`.

```python
# store.py
def add_questions(page_id, book_id, items: list[Question]) -> None   # embeds in batch via llm.embed
def remove_for_book(book_id) -> None
def count() -> CatalogStats

# search.py
def lookup(query: str, k=8) -> list[EntryPoint]
    # embed query (task="RETRIEVAL_QUERY") → cosine over questions matrix (numpy, in-memory cache
    # invalidated on add) → group by book → EntryPoint(book_id, page_ids, best_score, matched_questions)
    # Scale note: fine to ~100k questions; swap to sqlite-vec behind same signature when slow.
def nearest_pages(query, k=3) -> list[PageRef]   # fallback ladder step (orchestrator)
```

## 8. `ingest/` [P2]

> **Superseded by `docs/INGEST.md` (D-019).** Ingest is now ONE pipeline —
> survey → DraftTree(provided/missing slots) → resolve gaps → commit — with two entry points:
> `import` (folders, deterministic) and `ingest` (documents, LLM). Modules: `ingest/models.py`
> (DraftTree), `ingest/survey.py`, `ingest/resolve.py`, `ingest/importer.py` [P2a];
> `ingest/parse.py`, `ingest/split.py`, `ingest/classify.py` [P2b]; `ingest/questions.py` +
> `catalog/` [P2c]. The function sketches below remain valid for the P2b/P2c LLM stages.

```python
# parse.py
def parse_to_markdown(source: Path | str) -> ParsedDoc      # .md passthrough; .pdf via pymupdf4llm;
    # url via httpx+trafilatura; ParsedDoc(title, markdown, source_ref, lang)

# split.py
def split_book(doc: ParsedDoc) -> DraftBook
    # structure-aware: split on headings; target 400–1200 tokens/page; never split code blocks
    # or tables; tiny sections merge with neighbors. DraftBook(title, chapters[(title, pages[])])

# classify.py
def classify_placement(draft: DraftBook, store) -> Placement(path: list[NodeID], confidence: float, rationale: str)
    # descend tree top-down with MODEL_LITE reading NodeCards; at each level choose child or
    # "new shelf: <name>" or "stop here"; confidence = min over levels (weakest link);
    # < settings.ingest_confidence_gate ⇒ placement under _uncatalogued (P10)

# questions.py
def generate_questions(page: PageContent, *, n, langs) -> list[Question]
    # prompt gen_questions.md: questions a USER would ask that THIS page answers;
    # phrased in user vocabulary, not the page's headings; vi + en (P2 flywheel)

# pipeline.py
def ingest(source, *, dry_run=False, progress_cb=None) -> IngestReport
    # parse → split → classify → file (create book, write pages+toc) → rebuild_toc_lines
    # → generate+add questions → views.propagate_up → recompute_stats
    # progress_cb(IngestEvent) drives the UI stepper; report: location path, confidence,
    # n_pages, n_questions, tokens spent, duration; idempotency: source content hash — re-ingest updates in place
def review_uncatalogued(book_id, approved_parent_id) -> None   # move + propagate_up + re-embed nothing (ids stable)
```

## 9. `agent/tools.py` [P1] — hard budgets live HERE, not in prompts

```python
class NavState:  # per-navigation
    cursor: NodeID; path: list[NodeRef]; visited: set[NodeID]
    hops: int; pages_read: int; librarian_calls: int; trajectory: list[Hop]

TOOLS = [browse, open_book, read_page, go_back, ask_librarian, found, not_found]

def browse(state, node_id) -> Menu            # NodeMeta.description + children NodeCards; hop++
def open_book(state, book_id) -> TOC          # hop++
def read_page(state, page_id) -> PageContent  # cap max_pages_per_nav; content returned in delimited
                                              # evidence block marked untrusted (see ARCHITECTURE §7)
def go_back(state) -> Menu                    # pops path; marks branch rejected (menu pruned from LLM context — P7 hygiene)
def ask_librarian(state, query) -> list[EntryPoint]  # catalog.search.lookup; cap max_ask_librarian [P2]
def found(state, page_ids, note) -> Terminal
def not_found(state, reason, closest: list[NodeID]) -> Terminal
# enforcement: hops > max_hops ⇒ forced not_found("budget_exhausted"); visited re-entry ⇒ warning then forced go_back
```

## 10. `agent/navigator.py` [P1]

```python
def navigate(query: str, *, entry_points: list[EntryPoint] | None = None,
             read_budget: int | None = None, event_cb=None) -> NavResult
    # NavResult(status: FOUND|NOT_FOUND|AMBIGUOUS, path, pages: list[PageContent],
    #           hops, backtracks, trajectory_id)
    # - fresh chat per run (P7): system = prompts/route.md (librarian persona, tool rules,
    #   "absence of evidence in menu ≠ not in library — check see_also before leaving")
    # - starts at root menu, or jumps to entry_points when given (lookup shortcut)
    # - context hygiene: after go_back, replace the rejected subtree's menus in history with
    #   one line "visited <title>: not relevant because <reason>"
    # - emits NavEvent(enter|open|read|back|found|not_found) → event_cb for SSE + trajectory.logger
```

## 11. `agent/classifier.py` [P3]

```python
def classify_query(q: str) -> QueryPlan(qtype: Literal["lookup","synthesis","exploratory"], rationale: str)
    # MODEL_LITE, enum json_schema, temperature=0; ~1 short call; on LLM error default "lookup"
```

## 12. `agent/synthesizer.py` [P3]

```python
def coverage_scan(q: str, *, level=1) -> list[CoverageHit(node_id, sub_path_hint, why)]
    # asyncio.gather: one MODEL_LITE call per level-1 node: "Given this card + children cards,
    #   do you hold content relevant to <q>? which child?" → yes/no + pointer (parallel ⇒ flat latency)
def synthesize(q, hits, *, per_branch_read=3, event_cb) -> SynthesisEvidence
    # navigate() each hit in parallel (cap 4 concurrent) → collect pages per branch
def reduce(q, evidence) -> Answer               # prompts/reduce.md: contrast/aggregate, cite per-branch paths
```

## 13. `agent/answerer.py` [P1]

```python
def compose_answer(q, pages: list[PageContent], path: list[NodeRef]) -> Answer
    # Answer(text_md, citations: list[Citation(path_str, page_id, quote|None)], confidence: float)
    # prompt answer.md: answer ONLY from evidence blocks; every claim maps to a citation;
    # insufficient evidence ⇒ raise InsufficientEvidence (orchestrator turns into honest NOT_FOUND) (P6)
def compose_not_found(q, closest: list[NodeRef]) -> Answer   # names nearest shelves + suggests ingest
```

## 14. `agent/orchestrator.py` [P1 minimal, P3 full]

```python
async def answer_query(q: str, *, event_cb) -> Answer
    # P1: navigate(root) → compose_answer
    # P3: classify_query →
    #   lookup:      catalog.lookup → navigate(entry_points)          → compose_answer
    #   synthesis:   coverage_scan → synthesize → reduce
    #   exploratory: navigate(root, read_budget+2)
    # fallback ladder: NOT_FOUND → catalog.nearest_pages sanity check → compose_not_found
    # always: trajectory.logger.log_run(...); event_cb streams QueryEvent(classified|nav|answer_delta|done)
```

## 15. `trajectory/` [P3]

```python
# logger.py
def log_run(query, qtype, nav_result, answer_status) -> str    # persists trajectories + hops rows
# analyzer.py
def misroutes(window_days=14) -> list[MisrouteSignal(node_id, wrong_child, right_child, freq)]
    # mined from hops where go_back/backtrack preceded success elsewhere
def suggest_fixes() -> list[Fix]     # Fix = AddAlias(P9) | RewriteDescription | SuggestSplit — surfaced in admin, applied on approval
```

## 16. `evals/` [P3]

```python
# runner.py
def run_routing_eval(*, sample=100, with_hints=False, seed=42) -> EvalReport
    # sample catalog questions (stratified by domain) → navigate(question, entry_points=None)
    # → landed page == source page ⇒ hit; same book ⇒ partial (0.5)   [set-based truth]
    # EvalReport(overall, by_node: dict[NodeID, acc], avg_hops, p50/p95 latency, failures[])
    # persisted to eval_runs; costs real tokens ⇒ only via explicit `libkb eval` / admin button
# gates.py
def refactor_gate(before: EvalReport, after: EvalReport, *, tolerance=0.02) -> GateResult   # P8
```

## 17. `maintenance/rebalance.py` [P4]

```python
def suggest_split(node_id) -> SplitPlan(new_shelves: list[(title, one_line, member_book_ids)], rationale)
    # triggers when children > branching_split_threshold; labels must be GUESSABLE by a fresh LLM
def apply_split(plan) -> None    # create shelves → move books (redirects, P5) → propagate_up
                                 # → run_routing_eval → refactor_gate → auto-revert on regression (P8)
def merge_nodes(node_ids, into_title) -> None   # same gate
```

## 18. `api/` [P1 query+library, P2 ingest, P3+ admin]

```
POST /api/query                  {q}  → SSE: classified | nav_event | answer_delta | citations | done
GET  /api/library/tree?depth=2   → nested NodeCards (explorer initial load)
GET  /api/library/node/{id}      → NodeMeta + children + breadcrumb
GET  /api/library/page/{id}      → PageContent (+ its catalog questions)
POST /api/ingest                 file | {url} | {text} → {job_id}
GET  /api/ingest/jobs/{id}       → SSE: IngestEvent stepper states
GET  /api/ingest/review          → uncatalogued queue;  POST .../approve {parent_id}
GET  /api/admin/trajectories?window=   /api/admin/eval (POST = run)   /api/admin/fixes (GET/POST approve)
GET  /api/health                 → {ok, model, library_stats}
```

## 19. `cli.py` [P0]

`libkb init` · `libkb seed` (demo mini-library: AI→{RAG, LLM, CV}, ~6 books, so P1 is testable
before ingest exists) · `libkb ingest <path|url>` · `libkb ask "<q>" [--trace]` · `libkb eval` ·
`libkb rebuild-views`.

---

## Build order within P1 (walking skeleton)

1. `config` → `llm.client` (smoke: one generate + one embed) [P0]
2. `library.models` + `store` + `cli seed` [P0]
3. `agent.tools` + `navigator` + `cli ask --trace` ← **first end-to-end walk**
4. `answerer` + minimal `orchestrator` + `api /query` SSE
5. Minimal chat UI (from approved mockup) consuming SSE events

Definition of done, P1: `libkb ask "reranking là gì?"` walks seed library, answers with path
citation, and an off-library question returns honest NOT_FOUND. Both visible in the chat UI trace.
