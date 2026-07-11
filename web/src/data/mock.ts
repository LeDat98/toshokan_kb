// Mock data layer — mirrors the future backend contract (libkb/api). Ported from the design file.
// Swapped for the real SSE client when P1 lands; keep shapes in sync with api/events.py.
import type { StepKind } from "../ui";

export type StepStatus = "done" | "backtracked" | "read";
export type QueryId = "lookup" | "synthesis" | "notfound";

export interface TraceStep {
  kind: StepKind;
  title: string;
  desc: string;
  status: StepStatus;
  snippet?: string;
  why?: string;
}
export interface Counter {
  label: string;
  value: number;
  max: number;
}
export interface Branch {
  label: string;
  steps: TraceStep[];
}
export interface Trace {
  mode: "linear" | "parallel";
  counters: Counter[];
  steps: TraceStep[];
  branches: Branch[];
  terminal: { kind: "found" | "notfound"; pages?: number };
  coverage?: string;
}

const step = (
  kind: StepKind,
  title: string,
  desc: string,
  status: StepStatus,
  extra: Partial<TraceStep> = {},
): TraceStep => ({ kind, title, desc, status, ...extra });

export const TRACES: Record<QueryId, Trace> = {
  lookup: {
    mode: "linear",
    counters: [
      { label: "hops", value: 7, max: 12 },
      { label: "pages", value: 2, max: 6 },
      { label: "calls", value: 1, max: 2 },
    ],
    terminal: { kind: "found", pages: 2 },
    branches: [],
    steps: [
      step("domain", "AI", "Entering the AI hall", "done"),
      step("shelf", "LLM", "Peeked — reranking not shelved here", "backtracked", {
        why: "“Rerank” sits lexically near “LLM ranking”, but this shelf holds model architectures, not retrieval scoring. Returned to the hall.",
      }),
      step("shelf", "RAG", "Retrieval-Augmented Generation", "done"),
      step("book", "Advanced RAG Techniques", "Pulled from the shelf, opened", "done"),
      step("toc", "Table of contents", "Chapter 3 · Retrieval Optimization", "done"),
      step("page", "p.12 — Reranking & Cross-encoders", "Reading the page", "read", {
        snippet:
          "“…a cross-encoder that jointly scores (query, passage) pairs — higher precision at top-k than bi-encoder similarity alone.”",
      }),
    ],
  },
  synthesis: {
    mode: "parallel",
    counters: [
      { label: "hops", value: 11, max: 18 },
      { label: "pages", value: 3, max: 9 },
      { label: "calls", value: 1, max: 3 },
    ],
    terminal: { kind: "found", pages: 3 },
    coverage: "4 / 5 shelves",
    steps: [],
    branches: [
      {
        label: "Fixed-size",
        steps: [
          step("shelf", "RAG", "", "done"),
          step("book", "RAG Fundamentals", "", "done"),
          step("page", "p.4 — Sliding windows", "", "read"),
        ],
      },
      {
        label: "Semantic",
        steps: [
          step("shelf", "RAG", "", "done"),
          step("book", "Advanced RAG Techniques", "", "done"),
          step("page", "p.7 — Recursive splitting", "", "read"),
        ],
      },
      {
        label: "Layout-aware",
        steps: [
          step("shelf", "NLP", "", "done"),
          step("book", "Document Structure", "", "done"),
          step("page", "p.9 — Layout splits", "", "read"),
        ],
      },
    ],
  },
  notfound: {
    mode: "linear",
    counters: [
      { label: "hops", value: 9, max: 12 },
      { label: "pages", value: 0, max: 6 },
      { label: "calls", value: 2, max: 2 },
    ],
    terminal: { kind: "notfound" },
    branches: [],
    steps: [
      step("domain", "AI", "Entering the AI hall", "done"),
      step("shelf", "ML", "Scanned — no quantum error correction", "backtracked", {
        why: "“Error correction” matched ML regularization notes; that content is about model error, not quantum codes. Returned.",
      }),
      step("shelf", "Math for AI", "Scanned — linear algebra & probability only", "backtracked", {
        why: "Closest by topic — linear algebra underpins stabilizer codes — but no catalogued book covers QEC.",
      }),
    ],
  },
};

export const SAMPLES: { tag: "Lookup" | "Synthesis" | "Explore"; label: string; id: QueryId }[] = [
  { tag: "Lookup", label: "What is reranking in RAG?", id: "lookup" },
  { tag: "Synthesis", label: "Compare chunking strategies", id: "synthesis" },
  { tag: "Explore", label: "What is quantum error correction?", id: "notfound" },
];

// ---------------------------------------------------------------- library

export interface DomainCard {
  id: string;
  title: string;
  desc: string;
  stats: string;
  fresh: string;
}
export interface ShelfCard {
  id: string;
  title: string;
  desc: string;
  stats: string;
  seeAlso?: string;
  nest?: string[];
}
export interface BookCard {
  id: string;
  title: string;
  sum: string;
  meta: string;
  asked: string;
  spark: number[];
  low: boolean;
}
export interface TocRow {
  p: string;
  t: string;
  d: string;
  chips: string[];
  q: string[];
  cited?: boolean;
}
export interface TocGroup {
  ch: string;
  rows: TocRow[];
}
export interface PageDetail {
  title: string;
  cited: string;
  last: string;
  body: string[];
  q: string[];
}

export const LIB = {
  domains: [
    {
      id: "AI",
      title: "AI",
      desc: "Retrieval, language models, learning & perception.",
      stats: "5 shelves · 47 books",
      fresh: "var(--success)",
    },
    {
      id: "SE",
      title: "Software Engineering",
      desc: "Systems, patterns, testing and craft.",
      stats: "4 shelves · 38 books",
      fresh: "var(--success)",
    },
    {
      id: "Data",
      title: "Data",
      desc: "Storage, pipelines and analytics.",
      stats: "3 shelves · 29 books",
      fresh: "var(--warning)",
    },
  ] as DomainCard[],
  shelves: {
    AI: [
      { id: "RAG", title: "RAG", desc: "Retrieval-Augmented Generation.", stats: "3 books", seeAlso: "AI ▸ ML ▸ Ranking" },
      { id: "LLM", title: "LLM", desc: "Model architectures & foundations.", stats: "2 books" },
      { id: "NLP", title: "NLP", desc: "Language processing & structure.", stats: "2 books", nest: ["Document Structure", "Tokenization"] },
      { id: "CV", title: "CV", desc: "Vision & perception.", stats: "0 books" },
      { id: "ML", title: "ML", desc: "Classical & statistical learning.", stats: "1 book", seeAlso: "AI ▸ RAG ▸ Reranking" },
    ],
    SE: [
      { id: "ARCH", title: "Architecture", desc: "Systems design.", stats: "11 books" },
      { id: "PAT", title: "Patterns", desc: "Design patterns.", stats: "9 books" },
      { id: "TEST", title: "Testing", desc: "Quality & CI.", stats: "8 books" },
      { id: "OPS", title: "DevOps", desc: "Delivery & infra.", stats: "10 books" },
    ],
    Data: [
      { id: "STORE", title: "Storage", desc: "Databases & vector stores.", stats: "12 books" },
      { id: "PIPE", title: "Pipelines", desc: "ETL & streaming.", stats: "10 books" },
      { id: "ANA", title: "Analytics", desc: "Metrics & BI.", stats: "7 books" },
    ],
  } as Record<string, ShelfCard[]>,
  books: {
    RAG: [
      { id: "fund", title: "RAG Fundamentals", sum: "Chunking, embedding, and vector search basics.", meta: "16 pages · ingested 2026-06-18 · pdf", asked: "asked 8×", spark: [3, 5, 4, 6, 5, 8], low: false },
      { id: "adv", title: "Advanced RAG Techniques", sum: "Reranking, HyDE, query expansion, fusion.", meta: "24 pages · ingested 2026-07-02 · pdf", asked: "asked 12×", spark: [2, 4, 6, 5, 9, 12], low: false },
      { id: "eval", title: "RAG Evaluation", sum: "Faithfulness, context precision, RAGAS.", meta: "19 pages · ingested 2026-05-30 · md", asked: "asked 4×", spark: [5, 3, 4, 2, 3, 4], low: true },
    ],
    LLM: [
      { id: "attn", title: "Attention & Transformers", sum: "Self-attention, positional encoding.", meta: "22 pages · pdf", asked: "asked 6×", spark: [4, 6, 5, 7, 6, 6], low: false },
      { id: "scale", title: "Scaling Laws", sum: "Compute-optimal training.", meta: "14 pages · pdf", asked: "asked 3×", spark: [2, 3, 2, 4, 3, 3], low: false },
    ],
    NLP: [
      { id: "docstruct", title: "Document Structure", sum: "Layout-aware parsing & splits.", meta: "18 pages · html", asked: "asked 5×", spark: [3, 4, 3, 5, 4, 5], low: false },
      { id: "tok", title: "Tokenization", sum: "BPE, subword vocabularies.", meta: "11 pages · md", asked: "asked 2×", spark: [1, 2, 2, 1, 3, 2], low: true },
    ],
    ML: [
      { id: "gbm", title: "Gradient Boosting", sum: "Trees, boosting, regularization.", meta: "20 pages · pdf", asked: "asked 7×", spark: [5, 6, 4, 7, 6, 7], low: false },
    ],
    CV: [],
  } as Record<string, BookCard[]>,
  toc: {
    adv: [
      {
        ch: "Chapter 1 · Foundations",
        rows: [
          { p: "p.3", t: "Query understanding", d: "Intent parsing & rewriting", chips: ["rewrite", "intent"], q: ["How does query rewriting work?", "When to rewrite a query?"] },
        ],
      },
      {
        ch: "Chapter 3 · Retrieval Optimization",
        rows: [
          { p: "p.9", t: "HyDE", d: "Hypothetical document embeddings", chips: ["hyde", "embeddings"], q: ["What is HyDE?", "Does HyDE need a generator?"] },
          { p: "p.12", t: "Reranking & Cross-encoders", d: "Second-stage relevance scoring", chips: ["rerank", "cross-encoder"], q: ["What is reranking in RAG?", "Cross-encoder vs bi-encoder?"], cited: true },
          { p: "p.16", t: "Fusion retrieval", d: "Reciprocal rank fusion (RRF)", chips: ["rrf", "fusion"], q: ["How does RRF combine results?", "Weighting fusion sources?"] },
        ],
      },
    ],
    fund: [
      {
        ch: "Chapter 1 · Basics",
        rows: [
          { p: "p.2", t: "What is RAG", d: "Retrieval + generation loop", chips: ["overview"], q: ["What is RAG?"] },
          { p: "p.4", t: "Chunking", d: "Fixed & sliding windows", chips: ["chunking"], q: ["Optimal chunk size?"] },
        ],
      },
    ],
  } as Record<string, TocGroup[]>,
  pages: {
    "p.12": {
      title: "Reranking & Cross-encoders",
      cited: "cited 12×",
      last: "last cited 2h ago",
      body: [
        "A bi-encoder embeds query and passage independently, so ranking is just vector similarity — fast, but the two never “see” each other.",
        "A cross-encoder instead concatenates the pair and runs a full forward pass, producing a single relevance score. Far more accurate, but too slow to run over the whole corpus.",
        "The practical pattern: retrieve a coarse top-N with the bi-encoder, then rerank that shortlist with the cross-encoder and keep the true top-k.",
      ],
      q: [
        "What is reranking in RAG?",
        "Cross-encoder vs bi-encoder?",
        "When should you use reranking?",
        "Latency cost of reranking?",
      ],
    },
  } as Record<string, PageDetail>,
};

export function bookById(id: string): BookCard | null {
  for (const key of Object.keys(LIB.books)) {
    const found = LIB.books[key].find((b) => b.id === id);
    if (found) return found;
  }
  return null;
}

// ---------------------------------------------------------------- ingest

export type IngestStepStatus = "done" | "running" | "failed" | "pending";
export const INGEST_STEP_LABELS = ["Parse", "Split", "Classify", "Questions", "File", "Summaries"];

export interface IngestJob {
  id: string;
  file: string;
  meta: string;
  steps: IngestStepStatus[];
  showClassify?: boolean;
  showRetry?: boolean;
}
export const INGEST_JOBS: IngestJob[] = [
  {
    id: "A",
    file: "attention-is-all-you-need.pdf",
    meta: "2.1 MB · pdf · just now",
    steps: ["done", "done", "running", "pending", "pending", "pending"],
    showClassify: true,
  },
  {
    id: "B",
    file: "notes-on-rlhf.md",
    meta: "88 KB · markdown · 1 min ago",
    steps: ["done", "failed", "pending", "pending", "pending", "pending"],
    showRetry: true,
  },
];

export interface ReviewRow {
  id: string;
  title: string;
  source: string;
  conf: number;
  age: string;
  path: [string, string, string];
  toc: string[];
}
export const REVIEW_ROWS: ReviewRow[] = [
  { id: "r1", title: "notes-on-vector-dbs.md", source: "markdown", conf: 0.55, age: "2 days", path: ["AI", "RAG", "Infrastructure"], toc: ["p.1 Vector index types", "p.3 HNSW vs IVF", "p.5 Filtering & metadata"] },
  { id: "r2", title: "prompt-injection-survey.pdf", source: "pdf", conf: 0.61, age: "4 days", path: ["AI", "LLM", "Security"], toc: ["p.2 Attack taxonomy", "p.6 Defenses", "p.9 Benchmarks"] },
  { id: "r3", title: "kafka-exactly-once.html", source: "html", conf: 0.48, age: "6 days", path: ["Data", "Pipelines", "Streaming"], toc: ["p.1 Delivery semantics", "p.4 Transactions"] },
];

// ------------------------------------------------------------ observatory

export interface Kpi {
  label: string;
  value: string;
  delta: string;
  good: boolean;
  spark: number[];
}
export const KPIS: Kpi[] = [
  { label: "Routing accuracy", value: "91.4%", delta: "▲ 2.1 pts", good: true, spark: [86, 88, 87, 90, 89, 91.4] },
  { label: "Avg hops / query", value: "6.8", delta: "▼ 0.9", good: true, spark: [8.1, 7.9, 7.4, 7.2, 7.0, 6.8] },
  { label: "p95 latency", value: "5.3s", delta: "▼ 0.4s", good: true, spark: [6.2, 6.0, 5.9, 5.6, 5.5, 5.3] },
  { label: "Not-found rate", value: "7.2%", delta: "▲ 1.3 pts", good: false, spark: [5.1, 5.4, 6.0, 6.3, 6.9, 7.2] },
];

export type Outcome = "FOUND" | "NOT_FOUND" | "AMBIGUOUS";
export type QueryType = "Lookup" | "Synthesis" | "Explore";
export interface ReplayStep {
  kind: StepKind;
  title: string;
  state: "done" | "back" | "read";
}
export interface Trajectory {
  id: string;
  time: string;
  query: string;
  type: QueryType;
  hops: number;
  back: number;
  outcome: Outcome;
  dur: string;
  replay: ReplayStep[];
}
export const TRAJECTORIES: Trajectory[] = [
  {
    id: "t1", time: "14:02", query: "What is reranking in RAG?", type: "Lookup", hops: 7, back: 1, outcome: "FOUND", dur: "4.2s",
    replay: [
      { kind: "domain", title: "AI", state: "done" },
      { kind: "shelf", title: "LLM", state: "back" },
      { kind: "shelf", title: "RAG", state: "done" },
      { kind: "book", title: "Advanced RAG Techniques", state: "done" },
      { kind: "page", title: "p.12 Reranking", state: "read" },
    ],
  },
  {
    id: "t2", time: "13:47", query: "Compare chunking strategies for technical docs", type: "Synthesis", hops: 11, back: 0, outcome: "FOUND", dur: "9.4s",
    replay: [
      { kind: "shelf", title: "RAG", state: "done" },
      { kind: "book", title: "RAG Fundamentals", state: "done" },
      { kind: "shelf", title: "NLP", state: "done" },
      { kind: "book", title: "Document Structure", state: "done" },
    ],
  },
  {
    id: "t3", time: "13:30", query: "What is quantum error correction?", type: "Explore", hops: 9, back: 2, outcome: "NOT_FOUND", dur: "3.1s",
    replay: [
      { kind: "domain", title: "AI", state: "done" },
      { kind: "shelf", title: "ML", state: "back" },
      { kind: "shelf", title: "Math for AI", state: "back" },
    ],
  },
  {
    id: "t4", time: "12:58", query: "Best vector db for hybrid search", type: "Lookup", hops: 5, back: 1, outcome: "AMBIGUOUS", dur: "6.0s",
    replay: [
      { kind: "domain", title: "Data", state: "done" },
      { kind: "shelf", title: "Storage", state: "done" },
      { kind: "book", title: "Vector Stores", state: "read" },
    ],
  },
];

export interface Misroute {
  node: string;
  heat: "high" | "med" | "low";
  count: string;
  text: string;
}
export const MISROUTES: Misroute[] = [
  { node: "LLM shelf", heat: "high", count: "7×", text: "Queries about reranking enter LLM shelf then backtrack to RAG." },
  { node: "Math for AI", heat: "med", count: "4×", text: "QEC queries land here with no catalogued book, then fail." },
  { node: "Storage shelf", heat: "low", count: "3×", text: "Hybrid-search queries split between Storage and RAG." },
];

export const EVAL_RUNS = [84, 86, 85, 88, 90, 89, 91, 91.4];
export const EVAL_DOMAINS = [
  { n: "AI", v: 93, w: "93%" },
  { n: "Software Eng.", v: 89, w: "89%" },
  { n: "Data", v: 86, w: "86%" },
];
