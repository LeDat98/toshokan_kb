// Client for the LibraryKB backend. Contract mirrors libkb/api/events.py.

export interface StepEvent {
  action: "enter" | "open" | "read" | "back" | "found" | "not_found" | "budget";
  title: string;
  kind: "domain" | "shelf" | "book" | "page" | null;
  node_id: string | null;
  status: "done" | "read" | "backtracked" | "found" | "notfound" | "walking";
  detail: string;
  snippet: string;
}

export interface Citation {
  path: string;
  page_id: string;
}

export interface AnswerPayload {
  text: string;
  status: "answered" | "not_found";
  confidence: string;
  citations: Citation[];
  closest: string[];
  hops: number;
  backtracks: number;
}

export interface TreeNode {
  id: string;
  kind: string;
  title: string;
  one_line: string;
  children: TreeNode[];
}

export interface Ref {
  id: string;
  kind: string;
  title: string;
  slug: string;
}

export interface NodeDetail {
  id: string;
  kind: string;
  title: string;
  description: string;
  breadcrumb: Ref[];
  children: CardDetail[];
  see_also: string[];
}

export interface CardDetail {
  id: string;
  kind: string;
  title: string;
  one_line: string;
  stats_line: string;
  see_also: string[];
}

export interface BookDetail {
  id: string;
  title: string;
  description: string;
  breadcrumb: Ref[];
  chapters: { title: string; entries: TocEntry[] }[];
}

export interface TocEntry {
  page_id: string;
  title: string;
  one_line: string;
  keywords: string[];
}

export interface PageDetail {
  page_id: string;
  book_id: string;
  title: string;
  markdown: string;
  source_ref: string | null;
  breadcrumb: Ref[];
}

export interface HealthInfo {
  ok: boolean;
  model: string;
  seeded: boolean;
  library: { shelves: number; books: number; pages: number } | null;
}

interface StreamHandlers {
  onNav?: (ev: StepEvent) => void;
  onAnswer?: (a: AnswerPayload) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

/** POST /api/query and dispatch server-sent events. EventSource can't POST, so we parse manually. */
export async function streamQuery(q: string, handlers: StreamHandlers, signal?: AbortSignal): Promise<void> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q }),
    signal,
  });
  if (!res.ok || !res.body) {
    handlers.onError?.(`HTTP ${res.status}`);
    handlers.onDone?.();
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatch(raw, handlers);
    }
  }
  handlers.onDone?.();
}

function dispatch(raw: string, handlers: StreamHandlers): void {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  const payload = JSON.parse(data);
  if (event === "nav") handlers.onNav?.(payload as StepEvent);
  else if (event === "answer") handlers.onAnswer?.(payload as AnswerPayload);
  else if (event === "error") handlers.onError?.(payload.message ?? "error");
}

const json = async <T>(url: string): Promise<T> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json() as Promise<T>;
};

export const fetchHealth = () => json<HealthInfo>("/api/health");
export const fetchTree = (depth = 3) => json<TreeNode>(`/api/library/tree?depth=${depth}`);
export const fetchNode = (id: string) => json<NodeDetail>(`/api/library/node/${id}`);
export const fetchBook = (id: string) => json<BookDetail>(`/api/library/book/${id}`);
export const fetchPage = (id: string) => json<PageDetail>(`/api/library/page/${id}`);
