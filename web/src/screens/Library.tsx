import { useEffect, useState } from "react";
import { Icon } from "../icons";
import { PathChip, Seg, type PathSeg } from "../components/PathChip";
import { Markdown } from "../components/Markdown";
import { useToast } from "../components/Toast";
import {
  fetchBook,
  fetchNode,
  fetchPage,
  type BookDetail,
  type NodeDetail,
  type PageDetail,
} from "../api";
import { actionBtnStyle, iconBtnStyle, nodeCardStyle, primaryBtnStyle, sectionLabelStyle, sepStyle } from "../ui";

const ROOT_ID = "nd_root";

function useNode(id: string | null): NodeDetail | null {
  const [node, setNode] = useState<NodeDetail | null>(null);
  useEffect(() => {
    if (!id) return setNode(null);
    let ok = true;
    fetchNode(id).then((n) => ok && setNode(n)).catch(() => ok && setNode(null));
    return () => {
      ok = false;
    };
  }, [id]);
  return node;
}

export function Library({ goIngest, goAsk }: { goIngest: () => void; goAsk: () => void }) {
  const toast = useToast();
  const [domainId, setDomainId] = useState<string | null>(null);
  const [shelfId, setShelfId] = useState<string | null>(null);
  const [bookId, setBookId] = useState<string | null>(null);
  const [pageId, setPageId] = useState<string | null>(null);
  const [book, setBook] = useState<BookDetail | null>(null);
  const [page, setPage] = useState<PageDetail | null>(null);

  const root = useNode(ROOT_ID);
  const domain = useNode(domainId);
  const shelf = useNode(shelfId);

  useEffect(() => {
    if (root && !domainId) {
      const firstDomain = root.children.find((c) => c.kind === "domain");
      if (firstDomain) setDomainId(firstDomain.id);
    }
  }, [root, domainId]);

  useEffect(() => {
    if (domain) {
      const first = domain.children[0];
      setShelfId(first ? first.id : null);
      setBookId(null);
      setPageId(null);
    }
  }, [domain?.id]);

  useEffect(() => {
    if (!bookId) return setBook(null);
    let ok = true;
    fetchBook(bookId).then((b) => ok && setBook(b)).catch(() => ok && setBook(null));
    return () => {
      ok = false;
    };
  }, [bookId]);

  useEffect(() => {
    if (!pageId) return setPage(null);
    let ok = true;
    fetchPage(pageId).then((p) => ok && setPage(p)).catch(() => ok && setPage(null));
    return () => {
      ok = false;
    };
  }, [pageId]);

  const domains = root?.children ?? [];
  const shelves = domain?.children ?? [];
  const books = shelf?.children ?? [];

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "13px 24px", borderBottom: "1px solid var(--border)", background: "var(--surface-raised)" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "6px 12px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 9, fontSize: 12.5 }}>
          <Seg s={{ kind: "domain", label: domain?.title ?? "—", dot: true }} />
          <span style={sepStyle}>▸</span>
          <Seg s={{ kind: "shelf", label: shelf?.title ?? "—", dot: true }} />
          {book && (
            <>
              <span style={sepStyle}>▸</span>
              <Seg s={{ kind: "book", label: book.title }} />
            </>
          )}
        </div>
        <label style={{ flex: 1, maxWidth: 340, display: "flex", alignItems: "center", gap: 9, height: 34, padding: "0 12px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 9, color: "var(--ink-faint)" }}>
          <Icon name="search" size={15} />
          <input placeholder="Search in library…" style={{ flex: 1, border: 0, background: "transparent", outline: "none", fontSize: 13, color: "var(--ink)" }} />
        </label>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "flex", position: "relative" }}>
        <Column title="Domains" width={266}>
          {domains.map((d) => {
            const uncat = d.title === "Uncatalogued";
            return (
              <button
                key={d.id}
                onClick={() => (uncat ? setShelfIdDirect(d.id, setDomainId, setShelfId, setBookId, setPageId) : setDomainId(d.id))}
                className="h-border-accent"
                style={{ ...nodeCardStyle(domainId === d.id), ...(uncat ? { borderColor: "var(--warning)", borderLeftColor: "var(--warning)", background: "var(--warning-weak)" } : {}) }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15, color: uncat ? "var(--warning)" : "var(--ink)" }}>{d.title}</span>
                  <span style={{ flex: 1 }} />
                </div>
                {d.one_line && <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.45, margin: "5px 0 8px" }}>{d.one_line}</div>}
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>{d.stats_line}</div>
              </button>
            );
          })}
        </Column>

        <Column title={`Shelves in ${domain?.title ?? "—"}`} width={288}>
          {shelves.map((sh) => (
            <button key={sh.id} onClick={() => { setShelfId(sh.id); setBookId(null); setPageId(null); }} className="h-border-accent" style={nodeCardStyle(shelfId === sh.id)}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14.5 }}>{sh.title}</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)" }}>{sh.stats_line}</span>
              </div>
              {sh.one_line && <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.4, marginTop: 4 }}>{sh.one_line}</div>}
              {sh.see_also.map((sa) => (
                <div key={sa} style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 9, fontSize: 11, color: "var(--ink-faint)", fontStyle: "italic" }}>↗ {sa}</div>
              ))}
            </button>
          ))}
        </Column>

        <div style={{ flex: 1, minWidth: 0, overflowX: "hidden", overflowY: "auto", padding: "18px 20px" }}>
          <div style={{ ...sectionLabelStyle, marginBottom: 14 }}>Books in {shelf?.title ?? "—"}</div>
          {books.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "60px 20px", color: "var(--ink-faint)" }}>
              <span style={{ color: "var(--border-strong)", marginBottom: 14 }}>
                <Icon name="foot" size={34} sw={1.4} />
              </span>
              <div style={{ fontFamily: "var(--serif)", fontSize: 17, color: "var(--ink-muted)" }}>Empty shelf</div>
              <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13, margin: "2px 0 14px" }}>Nothing shelved here yet</div>
              <button onClick={goIngest} style={primaryBtnStyle}>
                <Icon name="inboxplus" size={15} />
                Ingest a document
              </button>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(238px, 1fr))", gap: 15 }}>
              {books.map((b) => (
                <button key={b.id} onClick={() => { setBookId(b.id); setPageId(null); }} className="h-border-accent" style={{ position: "relative", textAlign: "left", background: "var(--surface-raised)", border: `1px solid ${bookId === b.id ? "var(--accent)" : "var(--border)"}`, borderRadius: 12, padding: "0 15px 14px 17px", cursor: "pointer", overflow: "hidden", boxShadow: bookId === b.id ? "var(--shadow-md)" : "var(--shadow-sm)", transition: "transform .12s, border-color .12s" }}>
                  <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 5, background: "var(--book)" }} />
                  <div style={{ paddingTop: 15 }}>
                    <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15, lineHeight: 1.25, marginBottom: 6 }}>{b.title}</div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.45, minHeight: 36 }}>{b.one_line}</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 10 }}>{b.stats_line}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {book && (
          <aside style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 452, maxWidth: "60%", borderLeft: "1px solid var(--border)", background: "var(--surface-raised)", display: "flex", flexDirection: "column", minHeight: 0, boxShadow: "-12px 0 40px rgba(40,34,20,.14)", zIndex: 5 }}>
            {!page ? (
              <>
                <div style={{ flex: "none", display: "flex", alignItems: "flex-start", gap: 12, padding: "18px 20px", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ flex: "none", width: 38, height: 38, borderRadius: 9, background: "var(--book)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.9 }}>
                    <Icon name="book" size={22} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 17, lineHeight: 1.2 }}>{book.title}</div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 3, lineHeight: 1.45 }}>{book.description}</div>
                  </div>
                  <button onClick={() => setBookId(null)} style={iconBtnStyle}>
                    <Icon name="chevR" size={16} />
                  </button>
                </div>
                <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 20px 24px" }}>
                  <div style={{ ...sectionLabelStyle, marginBottom: 12 }}>Table of contents</div>
                  {book.chapters.map((ch) => (
                    <div key={ch.title} style={{ marginBottom: 16 }}>
                      <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13, color: "var(--ink-muted)", marginBottom: 6 }}>{ch.title}</div>
                      {ch.entries.map((e) => (
                        <div key={e.page_id} onClick={() => setPageId(e.page_id)} className="h-bg-sunk" style={{ display: "flex", gap: 12, padding: "11px 12px", borderRadius: 9, cursor: "pointer" }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 13.5 }}>{e.title}</div>
                            {e.one_line && <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{e.one_line}</div>}
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 7 }}>
                              {e.keywords.map((k) => (
                                <span key={k} style={{ fontFamily: "var(--mono)", fontSize: 10, padding: "2px 7px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--ink-muted)" }}>{k}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 12, padding: "18px 20px", borderBottom: "1px solid var(--border)" }}>
                  <button onClick={() => setPageId(null)} title="Back to contents" style={iconBtnStyle}>
                    <Icon name="chevL" size={15} />
                  </button>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <PathChip
                      small
                      segs={page.breadcrumb
                        .filter((r) => r.kind !== "root")
                        .map((r, i, arr) => ({
                          kind: r.kind as PathSeg["kind"],
                          label: r.title,
                          pageIcon: i === arr.length - 1,
                        }))}
                      style={{ fontSize: 11 }}
                    />
                  </div>
                  <button onClick={() => setBookId(null)} style={iconBtnStyle}>
                    <Icon name="chevR" size={16} />
                  </button>
                </div>
                <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "20px 22px 24px" }}>
                  <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 20, letterSpacing: -0.3, marginBottom: 14 }}>{page.title}</div>
                  <Markdown>{page.markdown}</Markdown>
                </div>
                <div style={{ flex: "none", display: "flex", gap: 8, padding: "13px 20px", borderTop: "1px solid var(--border)" }}>
                  <button onClick={() => { goAsk(); toast("Ask the librarian about this topic", "ask"); }} style={{ ...primaryBtnStyle, flex: 1, justifyContent: "center", padding: 10 }}>
                    <Icon name="ask" size={15} />
                    Ask about this page
                  </button>
                  <button onClick={() => toast("Link copied", "copy")} style={{ ...actionBtnStyle, padding: "10px 13px" }}>
                    <Icon name="copy" size={14} />
                    Copy link
                  </button>
                </div>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

function Column({ title, width, children }: { title: string; width: number; children: React.ReactNode }) {
  return (
    <div style={{ flex: "none", width, borderRight: "1px solid var(--border)", overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ ...sectionLabelStyle, padding: "0 2px 2px" }}>{title}</div>
      {children}
    </div>
  );
}

// Uncatalogued is a shelf directly under root; select it as the "shelf" column source.
function setShelfIdDirect(
  id: string,
  setDomainId: (v: string | null) => void,
  setShelfId: (v: string | null) => void,
  setBookId: (v: string | null) => void,
  setPageId: (v: string | null) => void,
) {
  setDomainId(id);
  setShelfId(null);
  setBookId(null);
  setPageId(null);
}
