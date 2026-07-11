import { useState } from "react";
import { Icon } from "../icons";
import { PathChip, Seg } from "../components/PathChip";
import { Sparkline } from "../components/Sparkline";
import { useToast } from "../components/Toast";
import { LIB, bookById } from "../data/mock";
import {
  actionBtnStyle,
  badge,
  iconBtnStyle,
  nodeCardStyle,
  primaryBtnStyle,
  sectionLabelStyle,
  sepStyle,
} from "../ui";

interface LibState {
  domain: string;
  shelf: string | null;
  book: string | null;
  page: string | null;
}

export function Library({ goIngest, goAsk }: { goIngest: () => void; goAsk: () => void }) {
  const toast = useToast();
  const [lib, setLib] = useState<LibState>({ domain: "AI", shelf: "RAG", book: "adv", page: null });
  const [treeView, setTreeView] = useState(false);
  const [nestOpen, setNestOpen] = useState<Record<string, boolean>>({});

  const shelves = LIB.shelves[lib.domain] ?? [];
  const books = lib.shelf ? (LIB.books[lib.shelf] ?? []) : [];
  const curBook = lib.book ? bookById(lib.book) : null;
  const toc =
    curBook && lib.book && LIB.toc[lib.book]
      ? LIB.toc[lib.book]
      : curBook
        ? [{ ch: "Contents", rows: [{ p: "p.1", t: curBook.title, d: "Overview", chips: ["summary"], q: ["What is this book about?"] }] }]
        : [];
  const page = lib.page
    ? (LIB.pages[lib.page] ?? {
        title: lib.page,
        cited: "cited 1×",
        last: "—",
        body: [`Content for ${lib.page} of ${curBook?.title ?? ""}.`],
        q: ["Sample question?"],
      })
    : null;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div
        style={{
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "13px 24px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-raised)",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            padding: "6px 12px",
            background: "var(--surface-sunk)",
            border: "1px solid var(--border)",
            borderRadius: 9,
            fontSize: 12.5,
          }}
        >
          <Seg s={{ kind: "domain", label: lib.domain, dot: true }} />
          <span style={sepStyle}>▸</span>
          <Seg s={{ kind: "shelf", label: lib.shelf ?? "—", dot: true }} />
          {curBook && (
            <>
              <span style={sepStyle}>▸</span>
              <Seg s={{ kind: "book", label: curBook.title }} />
            </>
          )}
        </div>
        <label
          style={{
            flex: 1,
            maxWidth: 340,
            display: "flex",
            alignItems: "center",
            gap: 9,
            height: 34,
            padding: "0 12px",
            background: "var(--surface-sunk)",
            border: "1px solid var(--border)",
            borderRadius: 9,
            color: "var(--ink-faint)",
          }}
        >
          <Icon name="search" size={15} />
          <input
            placeholder="Search in library…"
            style={{ flex: 1, border: 0, background: "transparent", outline: "none", fontSize: 13, color: "var(--ink)" }}
          />
        </label>
        <span style={{ flex: 1 }} />
        <div style={{ display: "flex", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 9, padding: 3 }}>
          {(["Columns", "Tree"] as const).map((mode) => {
            const active = mode === "Tree" ? treeView : !treeView;
            return (
              <button
                key={mode}
                onClick={() => setTreeView(mode === "Tree")}
                style={{
                  padding: "5px 12px",
                  border: 0,
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  background: active ? "var(--surface-raised)" : "transparent",
                  color: active ? "var(--ink)" : "var(--ink-muted)",
                  boxShadow: active ? "var(--shadow-sm)" : "none",
                }}
              >
                {mode}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "flex", position: "relative" }}>
        <div
          style={{
            flex: "none",
            width: 266,
            borderRight: "1px solid var(--border)",
            overflowY: "auto",
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ ...sectionLabelStyle, padding: "0 2px 2px" }}>Domains</div>
          {LIB.domains.map((d) => (
            <button
              key={d.id}
              onClick={() => {
                const first = LIB.shelves[d.id]?.[0];
                setLib({ domain: d.id, shelf: first ? first.id : null, book: null, page: null });
              }}
              className="h-border-accent"
              style={nodeCardStyle(lib.domain === d.id)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15 }}>{d.title}</span>
                <span style={{ flex: 1 }} />
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: d.fresh, flex: "none" }} />
              </div>
              <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.45, margin: "5px 0 8px" }}>{d.desc}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>{d.stats}</div>
            </button>
          ))}
          <div style={{ marginTop: "auto", paddingTop: 8 }}>
            <div
              style={{
                ...nodeCardStyle(false),
                borderColor: "var(--warning)",
                borderLeftColor: "var(--warning)",
                background: "var(--warning-weak)",
                cursor: "default",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14, color: "var(--warning)" }}>
                  Uncatalogued
                </span>
                <span style={{ flex: 1 }} />
                <span
                  style={{
                    minWidth: 20,
                    height: 20,
                    padding: "0 6px",
                    borderRadius: 10,
                    background: "var(--warning)",
                    color: "#fff",
                    fontSize: 11,
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  3
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.4, marginTop: 4 }}>
                Below the confidence gate — awaiting review.
              </div>
            </div>
          </div>
        </div>

        <div
          style={{
            flex: "none",
            width: 288,
            borderRight: "1px solid var(--border)",
            overflowY: "auto",
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ ...sectionLabelStyle, padding: "0 2px 2px" }}>Shelves in {lib.domain}</div>
          {shelves.map((sh) => (
            <button
              key={sh.id}
              onClick={() => {
                const first = LIB.books[sh.id]?.[0];
                setLib((s) => ({ ...s, shelf: sh.id, book: first ? first.id : null, page: null }));
              }}
              className="h-border-accent"
              style={nodeCardStyle(lib.shelf === sh.id)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14.5 }}>{sh.title}</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)" }}>{sh.stats}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.4, marginTop: 4 }}>{sh.desc}</div>
              {sh.seeAlso && (
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    marginTop: 9,
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    fontStyle: "italic",
                  }}
                >
                  ↗ see-also · {sh.seeAlso}
                </div>
              )}
              {sh.nest && (
                <>
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      setNestOpen((n) => ({ ...n, [sh.id]: !n[sh.id] }));
                    }}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      marginTop: 9,
                      fontSize: 11.5,
                      color: "var(--shelf)",
                      fontWeight: 600,
                    }}
                  >
                    <Icon name={nestOpen[sh.id] ? "chevDown" : "chevR"} size={13} />
                    <span>2 nested shelves</span>
                  </div>
                  {nestOpen[sh.id] && (
                    <div
                      style={{
                        marginTop: 6,
                        paddingLeft: 12,
                        borderLeft: "2px solid var(--border)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 5,
                      }}
                    >
                      {sh.nest.map((n) => (
                        <div key={n} style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                          {n}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, minWidth: 0, overflowX: "hidden", overflowY: "auto", padding: "18px 20px" }}>
          <div style={{ ...sectionLabelStyle, marginBottom: 14 }}>Books in {lib.shelf ?? "—"}</div>
          {books.length === 0 ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
                padding: "60px 20px",
                color: "var(--ink-faint)",
              }}
            >
              <span style={{ color: "var(--border-strong)", marginBottom: 14 }}>
                <Icon name="foot" size={34} sw={1.4} />
              </span>
              <div style={{ fontFamily: "var(--serif)", fontSize: 17, color: "var(--ink-muted)" }}>Empty shelf</div>
              <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13, margin: "2px 0 14px" }}>
                Nothing shelved here yet
              </div>
              <button onClick={goIngest} style={primaryBtnStyle}>
                <Icon name="inboxplus" size={15} />
                Ingest a document
              </button>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(238px, 1fr))", gap: 15 }}>
              {books.map((b) => (
                <button
                  key={b.id}
                  onClick={() => setLib((s) => ({ ...s, book: b.id, page: null }))}
                  className="h-border-accent"
                  style={{
                    position: "relative",
                    textAlign: "left",
                    background: "var(--surface-raised)",
                    border: `1px solid ${lib.book === b.id ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: 12,
                    padding: "0 15px 14px 17px",
                    cursor: "pointer",
                    overflow: "hidden",
                    boxShadow: lib.book === b.id ? "var(--shadow-md)" : "var(--shadow-sm)",
                    transition: "transform .12s, border-color .12s",
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: 5,
                      background: b.low ? "var(--warning)" : "var(--book)",
                    }}
                  />
                  {b.low && (
                    <span
                      style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        padding: "3px 8px",
                        background: "var(--warning-weak)",
                        color: "var(--warning)",
                        fontSize: 10,
                        fontWeight: 700,
                        borderRadius: "0 12px 0 9px",
                      }}
                    >
                      LOW
                    </span>
                  )}
                  <div style={{ paddingTop: 15 }}>
                    <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15, lineHeight: 1.25, marginBottom: 6 }}>
                      {b.title}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.45, minHeight: 36 }}>{b.sum}</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 10, lineHeight: 1.5 }}>
                      {b.meta}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 9 }}>
                      <span style={{ fontSize: 11, color: "var(--ink-muted)", fontWeight: 600 }}>{b.asked} this month</span>
                      <span style={{ flex: 1 }} />
                      <Sparkline values={b.spark} width={52} height={16} color="var(--book)" scale="max" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {curBook && (
          <aside
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              bottom: 0,
              width: 452,
              maxWidth: "60%",
              borderLeft: "1px solid var(--border)",
              background: "var(--surface-raised)",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
              boxShadow: "-12px 0 40px rgba(40,34,20,.14)",
              zIndex: 5,
            }}
          >
            {!page ? (
              <>
                <div style={{ flex: "none", display: "flex", alignItems: "flex-start", gap: 12, padding: "18px 20px", borderBottom: "1px solid var(--border)" }}>
                  <span
                    style={{
                      flex: "none",
                      width: 38,
                      height: 38,
                      borderRadius: 9,
                      background: "var(--book)",
                      color: "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      opacity: 0.9,
                    }}
                  >
                    <Icon name="book" size={22} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 17, lineHeight: 1.2 }}>{curBook.title}</div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 3, lineHeight: 1.45 }}>{curBook.sum}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)" }}>{curBook.meta}</span>
                    </div>
                  </div>
                  <button onClick={() => setLib((s) => ({ ...s, book: null, page: null }))} style={iconBtnStyle}>
                    <Icon name="chevR" size={16} />
                  </button>
                </div>
                <div style={{ flex: "none", display: "flex", gap: 8, padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
                  <a
                    href="#source"
                    onClick={(e) => {
                      e.preventDefault();
                      toast("Source link copied", "copy");
                    }}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--accent)" }}
                  >
                    source ↗
                  </a>
                  <span style={{ flex: 1 }} />
                  <button onClick={() => toast("Re-shelve queued for review", "shelf")} style={actionBtnStyle}>
                    Re-shelve
                  </button>
                </div>
                <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 20px 24px" }}>
                  <div style={{ ...sectionLabelStyle, marginBottom: 12 }}>Table of contents</div>
                  {toc.map((g) => (
                    <div key={g.ch} style={{ marginBottom: 16 }}>
                      <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13, color: "var(--ink-muted)", marginBottom: 6 }}>
                        {g.ch}
                      </div>
                      {g.rows.map((r) => (
                        <div
                          key={r.p}
                          onClick={() => setLib((s) => ({ ...s, page: r.p }))}
                          className="h-bg-sunk"
                          style={{
                            display: "flex",
                            gap: 12,
                            padding: "11px 12px",
                            borderRadius: 9,
                            cursor: "pointer",
                            border: `1px solid ${r.cited ? "var(--accent-weak)" : "transparent"}`,
                            background: r.cited ? "var(--accent-weak)" : "transparent",
                          }}
                        >
                          <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, fontWeight: 600, color: "var(--page)", flex: "none", paddingTop: 2 }}>
                            {r.p}
                          </span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                              <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 13.5 }}>{r.t}</span>
                              {r.cited && <span style={{ ...badge("var(--success)", "var(--success-weak)"), marginLeft: 4 }}>cited</span>}
                            </div>
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{r.d}</div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 7 }}>
                              {r.chips.map((c) => (
                                <span
                                  key={c}
                                  style={{
                                    fontFamily: "var(--mono)",
                                    fontSize: 10,
                                    padding: "2px 7px",
                                    background: "var(--surface-sunk)",
                                    border: "1px solid var(--border)",
                                    borderRadius: 5,
                                    color: "var(--ink-muted)",
                                  }}
                                >
                                  {c}
                                </span>
                              ))}
                            </div>
                            <div style={{ marginTop: 7, fontSize: 11, fontStyle: "italic", color: "var(--ink-faint)", lineHeight: 1.4 }}>
                              <span style={{ fontStyle: "normal", fontWeight: 600 }}>Asked here: </span>
                              {r.q.join("   ·   ")}
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
                  <button onClick={() => setLib((s) => ({ ...s, page: null }))} title="Back to contents" style={iconBtnStyle}>
                    <Icon name="chevL" size={15} />
                  </button>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <PathChip
                      small
                      segs={[
                        { kind: "shelf", label: lib.shelf ?? "" },
                        { kind: "book", label: curBook.title },
                        { kind: "page", label: page.title },
                      ]}
                      style={{ fontSize: 11 }}
                    />
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 6 }}>
                      {page.cited} · {page.last}
                    </div>
                  </div>
                  <button onClick={() => setLib((s) => ({ ...s, book: null, page: null }))} style={iconBtnStyle}>
                    <Icon name="chevR" size={16} />
                  </button>
                </div>
                <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "20px 22px 24px" }}>
                  <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 20, letterSpacing: -0.3, marginBottom: 14 }}>
                    {page.title}
                  </div>
                  <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--ink)", display: "flex", flexDirection: "column", gap: 12 }}>
                    {page.body.map((para, i) => (
                      <p key={i} style={{ margin: 0 }}>
                        {para}
                      </p>
                    ))}
                  </div>
                  <div style={{ marginTop: 22, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
                    <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", marginBottom: 10 }}>Generated questions</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                      {page.q.map((q) => (
                        <div
                          key={q}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 9,
                            padding: "8px 11px",
                            background: "var(--surface-sunk)",
                            border: "1px solid var(--border)",
                            borderRadius: 8,
                          }}
                        >
                          <span style={{ width: 6, height: 6, borderRadius: "50%", flex: "none", background: "var(--accent)" }} />
                          <span style={{ flex: 1, fontSize: 12.5 }}>{q}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div style={{ flex: "none", display: "flex", gap: 8, padding: "13px 20px", borderTop: "1px solid var(--border)" }}>
                  <button
                    onClick={() => {
                      goAsk();
                      toast("Question sent to the librarian", "ask");
                    }}
                    style={{ ...primaryBtnStyle, flex: 1, justifyContent: "center", padding: 10 }}
                  >
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
