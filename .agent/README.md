# .agent — cross-session project management

This directory is the project's continuity layer for AI coding sessions. The code and git
history say *what exists*; these files say *where we are, why, and what's next*.

| File | Purpose | Update rule |
|------|---------|-------------|
| `STATE.md` | Snapshot of *now*: phase, what works, next actions, blockers | Rewrite at the **end of every session** (keep it short — it is the first thing read) |
| `ROADMAP.md` | Phases P0–P4 with task checklists | Tick boxes as tasks land; add tasks when scope is discovered |
| `DECISIONS.md` | Append-only decision log (ADR-lite) | Append when any principle/stack/design choice is made or reversed. Never edit old entries; supersede them |
| `JOURNAL.md` | Append-only session log | Append one entry per session: date, what changed, what surprised us, handoff notes |
| `CONVENTIONS.md` | Coding conventions | Change only via a DECISIONS entry |

## Session protocol (for any AI agent or human)

1. **Start**: read `STATE.md`, then skim `ROADMAP.md` current phase. Read `DECISIONS.md` before
   proposing any design change — it may already be settled.
2. **Work**: follow `CONVENTIONS.md`. New design choices → append to `DECISIONS.md` immediately.
3. **End**: rewrite `STATE.md` (phase, done, next 1–3 actions, blockers), append `JOURNAL.md`,
   tick `ROADMAP.md`. Uncommitted WIP must be described in STATE.md.
