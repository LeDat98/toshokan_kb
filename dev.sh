#!/usr/bin/env bash
# LibraryKB launcher (Git Bash / POSIX).
#   ./dev.sh          bootstrap everything, then start the dev environment
#                     (frontend on :5173 now; API on :8000 auto-added when P1 lands)
#   ./dev.sh check    verify everything: backend tests + lint, frontend typecheck + build
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-dev}"

# ---------------------------------------------------------------- venv python
if [[ -x ".venv/Scripts/python.exe" ]]; then
  VPY=".venv/Scripts/python.exe" # Windows
elif [[ -x ".venv/bin/python" ]]; then
  VPY=".venv/bin/python" # POSIX
else
  echo "[setup] creating .venv"
  python -m venv .venv
  if [[ -x ".venv/Scripts/python.exe" ]]; then VPY=".venv/Scripts/python.exe"; else VPY=".venv/bin/python"; fi
fi

# ---------------------------------------------------------------- backend deps
if ! "$VPY" -c "import libkb" >/dev/null 2>&1; then
  echo "[setup] installing backend deps: pip install -e .[dev]"
  "$VPY" -m pip install --quiet --disable-pip-version-check -e ".[dev]"
fi

# ---------------------------------------------------------------- .env sanity
if [[ ! -f ".env" ]]; then
  echo "[warn] .env not found — copy .env.example and set GEMINI_API_KEY before using LLM features."
fi

# ---------------------------------------------------------------- demo library
if [[ ! -f "library/_meta.json" ]]; then
  echo "[setup] seeding demo library"
  "$VPY" -m libkb.cli seed
fi

# ---------------------------------------------------------------- frontend deps
if [[ ! -d "web/node_modules" ]]; then
  echo "[setup] installing frontend deps: npm install"
  (cd web && npm install --no-fund --no-audit)
fi

# ---------------------------------------------------------------- modes
if [[ "$MODE" == "check" ]]; then
  echo "[check] backend: pytest (LLM tests excluded)"
  "$VPY" -m pytest -q
  echo "[check] backend: ruff"
  "$VPY" -m ruff check .
  echo "[check] frontend: typecheck + build"
  (cd web && npm run build)
  echo "[check] ALL GREEN"
  exit 0
fi

if [[ "$MODE" != "dev" ]]; then
  echo "usage: ./dev.sh [dev|check]"
  exit 1
fi

API_PID=""
if "$VPY" -c "import libkb.api.main" >/dev/null 2>&1; then
  echo "[dev] starting API on http://127.0.0.1:8000"
  "$VPY" -m uvicorn libkb.api.main:app --reload --port 8000 &
  API_PID=$!
  trap '[[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null' EXIT
else
  echo "[dev] backend API not built yet (P1) — starting frontend only (mock data)"
fi

echo "[dev] starting frontend on http://localhost:5173"
cd web && npm run dev
