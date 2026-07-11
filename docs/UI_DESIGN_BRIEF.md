# LibraryKB — UI Design Brief

> Context file for an AI design tool. Goal: a complete desktop web-app mockup (1440×900,
> light + dark). Every screen, component, and state below must appear in the mockup.
> **Colors: do not follow a preset palette — choose them during design.** Semantic roles are
> defined in §2; map your palette onto those roles.

## 1. Product & metaphor

**LibraryKB** is a personal AI knowledge base organized like a physical library. An AI
"librarian" **visibly walks** the stacks to answer questions: Domain hall → Shelf → Book →
Table of contents → Page. The UI's signature idea: retrieval is not a spinner — it is a
**watchable walk**. Every answer carries its walking path as a citation
(`AI ▸ RAG ▸ Advanced RAG ▸ p.12 — Reranking`). When the library lacks an answer, the system
says so honestly instead of guessing — "not found" is a designed state, not an error.

Primary user: a single developer/researcher (technical, reads Vietnamese and English).
Tone: calm scholarly library × modern minimal software. Think quiet reading room, not
enterprise dashboard: generous whitespace, disciplined type, small moments of warmth
(book spines, paper texture *hints* only — no skeuomorphic clutter).

## 2. Design language

- **Semantic color roles** (assign actual colors at design time; must hold in light & dark):
  - `surface` / `surface-raised` (app bg, cards), `ink` (primary text), `ink-muted`
  - `accent` — the librarian/brand color: active nav step, primary buttons, links
  - `walk` — navigation-trace color family: current step (vivid), completed step (calm), rejected/backtracked step (desaturated + strikethrough feel)
  - `success` (FOUND, eval pass), `warning` (low confidence, uncatalogued), `danger` (failed, regression), `info` (synthesis mode)
  - Four node-kind tints used subtly on chips/icons: `domain`, `shelf`, `book`, `page`
- **Typography**: a serif display face for library headings (domain/shelf/book titles — the "library voice") + a clean sans for UI/chat + mono for paths, IDs, and token/cost numbers.
- **Iconography**: outline icons; consistent set for node kinds — domain: columns/building, shelf: bookshelf, book: closed book, TOC: list, page: file/bookmark.
- **Motion**: subtle only — walk steps appear sequentially (150ms stagger), pulsing dot on the current step, gentle check on FOUND. No large animations.
- **Density**: comfortable default; tables in Observatory switch to compact.

## 3. App shell (all screens)

- **Left sidebar** (collapsible to icons, 240px → 64px): logo "LibraryKB" (small book glyph),
  nav items with icons — **Ask** (chat bubble), **Library** (bookshelf), **Ingest** (inbox-plus),
  **Observatory** (telescope/chart). Bottom: settings gear, theme toggle (light/dark), and a
  tiny model badge `gemini-3.5-flash`.
- **Top bar**: global quick-ask input ("Hỏi thư viện… / Ask the library…", ⌘K), right side:
  library stats pill (`3 domains · 14 shelves · 128 books`), health dot (green ok / amber degraded).
- Ingest nav item shows a small badge count when the **review queue** (uncatalogued) is non-empty.

## 4. Screen 1 — Ask (default screen, the star)

Two-column layout: **conversation** (left, ~62%) + **Navigation Trace panel** (right, ~38%,
collapsible). Empty state (first run): centered illustration of library aisles, headline
"Thư viện đang mở cửa" / "The library is open", 3 sample query chips.

### 4.1 Conversation column
- **User message**: right-aligned compact bubble.
- **Librarian answer card** (left, wide): 
  - header row: small librarian avatar (owl or lamp glyph), **query-type badge** — `Lookup`
    (accent), `Synthesis` (info), `Explore` (neutral) — plus duration `4.2s`;
  - answer body in rendered markdown (show a code block in one sample);
  - **citations footer**: one **PathChip** per citation — a breadcrumb-shaped chip
    `AI ▸ RAG ▸ Advanced RAG Techniques ▸ p.12 Reranking` with a page icon; hover reveals the
    matched quote; click opens Library screen at that page. Confidence tag (`High/Med/Low`);
  - footer actions: copy, re-ask deeper (Explore), thumbs up/down (feeds trajectory logs).
- **NOT_FOUND answer card** (must be shown in mockup): calm, honest style (never red-alarm):
  icon of empty shelf, text "Thư viện chưa có nội dung này." + "Closest shelves:" 2–3 PathChips
  + primary button **“Ingest a document about this”** → jumps to Ingest with topic prefilled.
- **Synthesis answer card** (show one): sections per source branch, each section header is a
  PathChip; a small "coverage: 4/5 shelves scanned" line.
- **Input bar** (bottom, sticky): textarea, send button, live **auto-detected mode badge**
  inside the field while typing, stop button while streaming.

### 4.2 Navigation Trace panel (signature component)
A vertical timeline of the current/last walk, room-by-room:
- Each **step row**: node-kind icon + title + one-line description (truncated) + status:
  - `walking` — vivid `walk` color, pulsing dot;
  - `done` — calm check;
  - `backtracked` — desaturated, small return-arrow, collapsed by default ("visited, not relevant — why" on expand);
  - `read` — page steps show a tiny page-preview snippet (2 lines).
- Terminal chip at bottom: **FOUND** (success) with N pages read, or **NOT FOUND** (neutral-warning).
- Counters row: hops `7/12`, pages `2/6`, librarian-calls `1/2` as tiny meters.
- Steps are clickable → Library screen. Panel header: "Đường đi của thủ thư / The librarian's walk"
  + collapse toggle. While synthesis runs, the panel shows **parallel mini-traces** (one per branch, stacked).

## 5. Screen 2 — Library (explorer)

**Miller columns** (3 panes, resizable) + **reader**. Header: breadcrumb PathChip (always visible),
search-in-library field, view toggle (columns / tree).
- **Column 1 — Domains**: cards with serif title, description (2 lines), stats line
  (`4 shelves · 32 books`), freshness dot. Selected card gets accent edge. Include the special
  **Uncatalogued** shelf pinned at bottom with warning tint + count.
- **Column 2 — Shelves**: same card anatomy + **see-also chips** at card bottom
  (`↗ for cross-encoders, see AI ▸ ML ▸ Ranking`) in muted style. Shelves can nest — show one
  nested shelf row with an expand caret.
- **Column 3 — Books**: **BookSpine cards** in a grid: spine-like vertical accent edge, serif title,
  one-line summary, meta row (`24 pages · ingested 2026-07-02 · source: pdf`), tiny sparkline
  "asked 12× this month". Low-confidence books show a warning corner-tag.
- **Book view** (replaces column 3 or opens as wide drawer): book header (title, summary, source
  link, Re-shelve button) + **TOC list** grouped by chapter: each row = page number, title,
  one-line, keyword chips; hover shows the page's generated questions ("Người ta hỏi gì ở trang này?").
- **Page reader** (right pane or full drawer): rendered markdown, header with PathChip + page
  stats (times cited, last cited), footer: **generated questions list** (VI + EN, small chips)
  and source reference. Buttons: "Ask about this page", copy link.
- Empty states: empty shelf ("Kệ trống — ingest something"), empty library (points to Ingest).

## 6. Screen 3 — Ingest

Two-tab screen: **New ingest** | **Review queue** (badge = uncatalogued count).

### 6.1 New ingest
- **Drop zone** card: drag-drop file (pdf/md/html), or URL field, or paste-text expander; note
  line "Nguồn sẽ được thủ thư phân loại tự động".
- **Job list** below, one **JobCard** per document with a horizontal **pipeline stepper**:
  `Parse → Split → Classify → Generate Questions → File → Update summaries`
  — states per step: pending (muted), running (pulse), done (check), failed (danger + retry link).
- **Classify step is interactive** (must be mocked expanded): shows proposed placement as an
  editable PathChip (`AI ▸ RAG ▸ (new shelf) Evaluation`), a **ConfidenceBar** (0–1 with the 0.7
  gate marked), rationale line, and two buttons: Accept / Change location (opens a mini tree picker).
  Below gate ⇒ amber note "will go to Uncatalogued for review".
- **Completed JobCard** collapses into an **IngestReport** row: location PathChip, `18 pages`,
  `72 questions (vi+en)`, token cost, duration, "Open book" link.

### 6.2 Review queue
Table of uncatalogued books: title, source, proposed path + confidence, age. Row expands to
book preview (TOC excerpt) + tree picker + **Approve shelf** / **Re-classify** buttons.

## 7. Screen 4 — Observatory (health & learning loop)

- **KPI row** (4 stat tiles): Routing accuracy (with trend sparkline), Avg hops/query,
  p95 latency, Not-found rate. Each tile: big number, delta vs last week.
- **Trajectories table**: time, query (truncated), type badge, **mini-trace** (compressed PathChip
  with hop count), backtracks, outcome chip (FOUND/NOT_FOUND/AMBIGUOUS), duration. Row expands to a
  full **trace replay** — same component as the Ask trace panel, read-only.
- **Misroute panel**: "Nơi thủ thư hay lạc" — list of nodes with misroute frequency; each row a
  small heat-badge + sentence "Queries about *reranking* enter *LLM* shelf then backtrack (7×)".
- **Suggested fixes** cards (the learning loop): three kinds, each with Approve/Dismiss —
  `Add see-also` (shows from→to PathChips), `Rewrite description` (old vs new description diff),
  `Split shelf` (proposed sub-shelves with member counts + "eval-gated" note).
- **Eval runs**: line chart of routing accuracy over runs + "Run eval now" button with cost
  hint (`~100 queries · costs tokens`), and last EvalReport summary (per-domain accuracy bars).

## 8. Shared component inventory (design as a mini system)

**PathChip** (breadcrumb chip, 3 sizes; the app's signature element) · **NodeCard** ·
**BookSpine** · **TraceStep** + **TracePanel** · **StatusChip** (FOUND/NOT_FOUND/AMBIGUOUS/
RUNNING) · **QueryTypeBadge** · **ConfidenceBar** (with gate mark) · **PipelineStepper** ·
**StatTile** (with sparkline) · **QuestionChip** (vi/en flag dot) · **SeeAlsoChip** ·
**EmptyState** (library-themed illustrations) · **Toast** (ingest done, eval done, fix applied).

## 9. Sample content for the mockup (use verbatim)

- Lookup: user asks **"Reranking trong RAG là gì?"** → trace: `AI` → `RAG` → book
  `Advanced RAG Techniques` → TOC → `p.12 — Reranking & Cross-encoders` → FOUND → answer with
  1 PathChip citation, confidence High, 4.2s, 7 hops.
- Synthesis: **"So sánh các chiến lược chunking cho tài liệu kỹ thuật"** → coverage 4/5 shelves,
  3 parallel mini-traces, sectioned answer with 3 PathChips.
- Not found: **"Quantum error correction là gì?"** → NOT_FOUND card, closest shelves
  `AI ▸ ML` and `AI ▸ Math for AI`, ingest CTA.
- Library tree: domains `AI`, `Software Engineering`, `Data`; AI shelves: `RAG`, `LLM`, `NLP`,
  `CV`, `ML`; RAG books: `RAG Fundamentals`, `Advanced RAG Techniques`, `RAG Evaluation`.
- Ingest job: `attention-is-all-you-need.pdf` → proposed `AI ▸ LLM ▸ Foundations`, confidence 0.86.
- Review queue item: `notes-on-vector-dbs.md`, proposed `AI ▸ RAG ▸ Infrastructure`, confidence 0.55.

## 10. States, responsiveness, accessibility

- Show light **and** dark for at least the Ask screen; both themes must keep role contrast (WCAG AA).
- Loading: skeleton cards (library), sequential step reveal (trace), stepper pulse (ingest).
- Errors: LLM unreachable banner (top, `danger`, retry); per-step ingest failure with retry.
- Desktop-first 1440; must degrade to 1024 (trace panel becomes a drawer toggled from a floating
  "walk" button; miller columns collapse to two panes + breadcrumb).
- Keyboard: ⌘K quick-ask focus; trace steps and TOC rows focusable; visible focus rings.
- All statuses carry an icon + label, never color alone.
