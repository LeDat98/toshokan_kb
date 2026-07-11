import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { Icon, type IconName } from "./icons";
import { ToastProvider } from "./components/Toast";
import { Ask } from "./screens/Ask";
import { Ingest } from "./screens/Ingest";
import { Library } from "./screens/Library";
import { Observatory } from "./screens/Observatory";
import { ghostBtnStyle } from "./ui";

type Screen = "ask" | "library" | "ingest" | "observatory";
type Theme = "light" | "dark";

const NAV: { id: Screen; label: string; icon: IconName }[] = [
  { id: "ask", label: "Ask", icon: "ask" },
  { id: "library", label: "Library", icon: "library" },
  { id: "ingest", label: "Ingest", icon: "ingest" },
  { id: "observatory", label: "Observatory", icon: "observatory" },
];

function loadTheme(): Theme {
  try {
    return (localStorage.getItem("lkb-theme") as Theme) || "light";
  } catch {
    return "light";
  }
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("ask");
  const [sidebar, setSidebar] = useState(true);
  const [theme, setTheme] = useState<Theme>(loadTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("lkb-theme", theme);
    } catch {
      /* private mode */
    }
  }, [theme]);

  const navStyle = (active: boolean): CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 12px",
    borderRadius: 10,
    cursor: "pointer",
    border: 0,
    background: active ? "var(--accent-weak)" : "transparent",
    font: "500 14px/1 var(--sans)",
    width: "100%",
    textAlign: "left",
    transition: "background .12s",
    color: active ? "var(--accent)" : "var(--ink-muted)",
    fontWeight: active ? 600 : 500,
  });

  return (
    <ToastProvider>
      <div style={{ display: "flex", height: "100vh", width: "100%", overflow: "hidden", background: "var(--surface)" }}>
        <aside
          style={{
            flex: "none",
            width: sidebar ? 240 : 72,
            transition: "width .2s ease",
            background: "var(--surface-raised)",
            borderRight: "1px solid var(--border)",
            padding: "18px 14px",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 11, padding: "6px 6px 22px 6px", height: 34 }}>
            <div
              style={{
                flex: "none",
                width: 34,
                height: 34,
                borderRadius: 9,
                background: "var(--accent)",
                color: "var(--accent-ink)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <Icon name="book" size={19} />
            </div>
            {sidebar && (
              <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 18, letterSpacing: -0.2, whiteSpace: "nowrap" }}>
                LibraryKB
              </div>
            )}
          </div>

          <nav style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 6 }}>
            {NAV.map((n) => (
              <button key={n.id} onClick={() => setScreen(n.id)} title={n.label} style={navStyle(screen === n.id)}>
                <Icon name={n.icon} />
                {sidebar && <span style={{ whiteSpace: "nowrap", flex: n.id === "ingest" ? 1 : undefined, textAlign: "left" }}>{n.label}</span>}
                {n.id === "ingest" && sidebar && (
                  <span
                    style={{
                      flex: "none",
                      minWidth: 18,
                      height: 18,
                      padding: "0 5px",
                      borderRadius: 9,
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
                )}
              </button>
            ))}
          </nav>

          <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
            <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Toggle theme" style={ghostBtnStyle}>
              <Icon name={theme === "dark" ? "sun" : "moon"} />
              {sidebar && <span style={{ whiteSpace: "nowrap" }}>{theme === "dark" ? "Light mode" : "Dark mode"}</span>}
            </button>
            <button title="Settings" style={ghostBtnStyle}>
              <Icon name="settings" />
              {sidebar && <span style={{ whiteSpace: "nowrap" }}>Settings</span>}
            </button>
            {sidebar && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                  margin: "8px 4px 2px",
                  padding: "7px 9px",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  background: "var(--surface-sunk)",
                }}
              >
                <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} />
                <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                  gemini-3.5-flash
                </span>
              </div>
            )}
            <button onClick={() => setSidebar(!sidebar)} title="Collapse" style={ghostBtnStyle}>
              <Icon name={sidebar ? "chevL" : "chevR"} />
              {sidebar && <span style={{ whiteSpace: "nowrap" }}>Collapse</span>}
            </button>
          </div>
        </aside>

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--surface)" }}>
          <header
            style={{
              flex: "none",
              height: 60,
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "0 24px",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-raised)",
            }}
          >
            <label
              style={{
                flex: 1,
                maxWidth: 520,
                display: "flex",
                alignItems: "center",
                gap: 10,
                height: 38,
                padding: "0 12px",
                background: "var(--surface-sunk)",
                border: "1px solid var(--border)",
                borderRadius: 10,
                color: "var(--ink-faint)",
              }}
            >
              <Icon name="search" size={16} />
              <input
                placeholder="Ask the library…"
                style={{ flex: 1, border: 0, background: "transparent", outline: "none", fontSize: 14, color: "var(--ink)" }}
                onFocus={() => setScreen("ask")}
              />
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  padding: "2px 6px",
                  border: "1px solid var(--border-strong)",
                  borderRadius: 5,
                  color: "var(--ink-faint)",
                }}
              >
                ⌘K
              </span>
            </label>
            <div style={{ flex: 1 }} />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                height: 34,
                padding: "0 12px",
                background: "var(--surface-sunk)",
                border: "1px solid var(--border)",
                borderRadius: 20,
              }}
            >
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                3 domains · 14 shelves · 128 books
              </span>
            </div>
            <div
              title="Library health: OK"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 7,
                height: 34,
                padding: "0 12px",
                background: "var(--success-weak)",
                border: "1px solid var(--border)",
                borderRadius: 20,
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--success)",
                  boxShadow: "0 0 0 3px color-mix(in srgb, var(--success) 22%, transparent)",
                }}
              />
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--success)" }}>OK</span>
            </div>
          </header>

          <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
            <ScreenPane active={screen === "ask"}>
              <Ask dark={theme === "dark"} goLibrary={() => setScreen("library")} goIngest={() => setScreen("ingest")} />
            </ScreenPane>
            <ScreenPane active={screen === "library"}>
              <Library goIngest={() => setScreen("ingest")} goAsk={() => setScreen("ask")} />
            </ScreenPane>
            <ScreenPane active={screen === "ingest"}>
              <Ingest dark={theme === "dark"} goLibrary={() => setScreen("library")} />
            </ScreenPane>
            <ScreenPane active={screen === "observatory"}>
              <Observatory />
            </ScreenPane>
          </div>
        </div>
      </div>
    </ToastProvider>
  );
}

/** Keeps every screen mounted (walk state survives navigation), shows one. */
function ScreenPane({ active, children }: { active: boolean; children: ReactNode }) {
  return <div style={{ height: "100%", display: active ? "block" : "none" }}>{children}</div>;
}
