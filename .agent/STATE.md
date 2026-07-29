# STATE — as of 2026-07-29 (session 13)

## 🎯 READ `docs/SELECTION_TARGET.md` FIRST — the mission and the ONLY scoring contract
Set by the user 2026-07-29 and it **supersedes every earlier framing in this file.**

**Mission:** the sieve hands 50–100 candidates; only **TP ≈ 2.75** of them hold the answer. Get the
agent's chosen set as close to TP as possible — **containing all of it**, carrying little else.

**Score `superset` (selection ⊇ TP). Nothing else.** Overhead of 1–2 documents is a fine trade;
missing ONE true page is not. Never compare selectors at different `taken`. The basket is not free —
always report `ctx_tokens`. `retention` gives partial credit and rewards taking more: diagnostic
only (that confusion is metric bug 6.8 and it inverted the project's conclusion for sessions).

Where it stands (n=150, qwen-plus): `rich` **64.7%** superset / 7.0 taken / 10.5k ctx · `headers`
58.7% / 6.5 · `set` 42.7% / **3.0 taken, 71% precision** · `agent` 36.7% / 3.2. Pool ceiling 92.7%.
**Two families, each half-right:** loose ones cover by carrying 4+ extra; tight ones land at TP+1
with the right shape and miss a true page 6 times in 10. **Goal: superset ≥ 90% at taken ≈ 4.**

**Next, and it is the only open direction:** the tight selectors do not fail at judging (71%
precision vs the embedder's 23%) — they fail at **knowing they are not finished**. `set` already
emits `missing`, the agent already has `coverage_map`, and neither self-checks before committing.
Build a **completeness check before `select`**. Instruction does not work — measured (`triage_fill`
moved 4.5 → 4.7). It needs a mechanism.

---

## ⚡ SESSION 13: the SELECTION layer — three things shipped, ZERO numbers yet (D-064)
The thesis under test: **the agent choosing pages loses to the embedder's top-k** (probe 2c,
MultiHop n=150 — triage keeps 69% AllGold, embedder top-10 keeps 75%). A reranker is not the answer;
that was measured and refuted (D-048). Read DECISIONS **D-064** and, for the literature behind it,
`.agent/private/RESEARCH_agentic_selection.md` (gitignored) + the artifact linked there.

**Shipped this session — all default-OFF, all zero new LLM calls:**
1. `triage_card=rich` (**Tier 0**) — several query-relevant passages instead of one, the passage
   AND the matched catalog row (lean makes them mutually exclusive for no reason), section titles
   whose *body* overlaps the query MARKED `▸`. Model-free (`query_passages`, `relevant_sections`).
2. `triage_mode=set` (**Tier 2**) — one call over the same cards asking *"which pages TOGETHER cover
   this?"*; each pick states what it ADDS; `missing` names the hole. Prompt `select_set.md`.
   Sections still named (the refuted `read` selector lost by picking whole pages, D-053).
3. `libkb probe-selection` — the deciding experiment. Arms `embedder | headers | rich | set |
   set+rich | read` over ONE shared candidate pool. Headline metric **retention** (of the gold the
   sieve already found, how much did the selector keep). Prices itself on 3 pools and stops
   without `--yes`.

`query_snippet` deliberately left BIT-IDENTICAL to the D-050-measured version; the improvement lives
only in the new `query_passages`, so the baseline stays comparable. 25 new LLM-free tests.

### ✅ MEASURED (D-068) — and the premise of this whole thread was CONFOUNDED
`probe-selection --limit 150` on MultiHop, gemini-3.5-flash, one shared pool per query.

The thread was built on probe 2c: *"triage keeps 69% AllGold, embedder top-10 keeps 75%"* — the
agent loses to the sieve. **That comparison gave the embedder 10 pages and the selector ~4.**
Retention rewards taking more. The first pass of this run repeated the error at basket 20.

The control (free, 0 LLM) — embedder retention by basket: **53.6 / 59.7 / 63.7 / 77.7 / 89.0%** at
3 / 4 / 5 / 10 / 20. At an **equal budget** the result inverts:

| arm | pages | retention | AllGold |
|---|---|---|---|
| embedder | 4.0 | 59.7% | 21.3% |
| **rich** | **4.1** | **88.1%** | **58.7%** |
| headers (shipped) | 4.4 | 86.6% | 57.3% |
| set | 3.6 | 82.6% | 50.0% |
| trace | 3.4 | 79.7% | 42.7% |

**`rich` = +28.4 retention over the embedder on the same pages, and within 0.9 points of what the
embedder needs 20 pages for.** The agent is ~5× more page-efficient, not worse at picking.

- **`triage_card=rich` is the best selector measured** — promote it after an answer-level A/B.
- **`trace` (coverage map) REFUTED as a mode** — worst LLM arm, fewest pages. Telling the agent
  which candidate covers which part appears to convince it that it is DONE (same shape as D-051).
  The tool stays for the agent loop; the mode does not become a default.
- **The real defect is UNDER-FILLING**: every arm may take 20 and takes 3–4, and retention tracks
  pages-taken almost perfectly.

### ✅ ANSWER-LEVEL A/B DONE (D-069) — `rich` NOT promoted, and the ceiling moved
`eval-multihop --limit 100`, identical cases, **cache forced off**: ANSWER 70.5% → **71.6%**,
honesty 100% both, coward 14.8% both, **+22% tokens**. +1.1 points is ONE flipped case — below the
project's noise floor. **`triage_card` stays `lean`.**

`rich` wins decisively on RETENTION (matches a 20-page embedder using 4.5 pages) and that does not
reach the answer. So the honest claim for it is **efficiency, not accuracy** — valuable when the
basket must be small, worth nothing at basket 20 on this corpus.

**The ceiling has moved to the ANSWERER.** temporal 47.8% with the gold in the basket; comparison
69.7%. Selection is no longer the binding constraint on this corpus — that is the finding.

Also settled: the three ReAct fixes work mechanically (voluntary `select` 35%→98%, step-exhaustion
147/150→0) but cost the agent its adaptive tool routing and still lose to one call. `triage_fill` is
a null result — under-filling is real and not reachable by instruction; it needs code, not words.

⚠️ **METRIC BUG 6.9, and it cost a paid run.** The semantic answer cache replayed arm A's answers to
arm B; both arms came back bit-identical and the score was **inflated +6.8 points**.
`evals/multihop_answer.run()` now forces the cache off itself, with a regression test. If you ever
see two arms agree to the decimal, suspect the measurement before believing it.

### (superseded) NEXT — the highest-value experiment in the project right now
**Make the selector FILL its basket.** One prompt change + one arm (~$1.6). If ~5× page-efficiency
survives at 10–20 pages, it beats embedder@20 outright and the thesis is not just rescued, it wins.
Then: an answer-level A/B (`eval-multihop`) to confirm retention carries through to accuracy — it is
a proxy, not the product. The `agent` (ReAct) arm is still unrun: 1,050 calls / 5.3M input tokens.

### (superseded) NEXT — run the arms. Nothing here is a claim until then.
```
.venv\Scripts\libkb.exe probe-selection --limit 150            # preflight, spends nothing
.venv\Scripts\libkb.exe probe-selection --limit 150 --yes --save benchmarks/selection.json
# arms: embedder | headers | rich | set | set+rich | trace | trace+rich | agent | read
# and the cheap-tier question, now that qwen tool-calling works:
#   LIBKB_MODEL=qwen-plus .venv\Scripts\libkb.exe probe-selection --arms embedder,headers,agent --yes
```
Read `retention` first, then the by-kind table — `comparison`/`temporal` are the kinds that
genuinely need >1 document and where a pointwise selector should fail. Then:
- an arm that beats `embedder` on retention → flip its default and re-run `eval-multihop` to
  confirm the answer follows the selection (retention is a proxy, not the product);
- an arm that does not → say so in the SCORECARD and move to **Tier 3** (IRCoT loop + note
  compression, gated by a CRAG-style evaluator), which is the next untried mechanism, not a retry.
- FiQA selection (qrels, no gold answer needed) is the genuinely-new external datapoint — see
  SCORECARD §5.5; needs a `load_fiqa` loader in `evals/selection.py` (the probe is dataset-agnostic
  by design: a dataset is a loader returning `SelQuery` + a page→key map).

### THE SCOPE RULE, and the first build under it (D-066 / D-067)
**Every method from here is a TOOL/SKILL the agent uses on the 50–100 candidates the cascade already
proposed — not a change to the sieve.** The sieve is not the bottleneck (FiQA R@100 0.920, MultiHop
AllGold@20 93.5%); selection is (triage keeps 69%, embedder top-10 keeps 75%). Test before building
*anything*: does this run over the whole corpus, or over the pool? Whole corpus ⇒ wrong frame.

Shipped, all default-OFF, all measurable as `probe-selection` arms:
- **`agent/pooltools.py`** (0 LLM) — `coverage_map` (question → parts → which candidate covers
  which, + the parts nothing covers, + a greedy covering set) and `find_in_candidates` (literal/
  regex across candidate bodies, returning the SECTION of each hit).
- **`triage_mode=trace`** — `set` selection with the coverage map handed to it. Same call count.
- **`triage_mode=agent`** — a ReAct loop (`agent/poolagent.py`): the librarian gets the tools plus
  `ask_page` (one lite call, "does this page answer it? quote the line") and ends at `select`.
  **Not the walk**: the candidate set is fixed before the loop starts, so nothing can get lost.
  **Budgets in CODE** (`pool_max_steps` 6 / `pool_max_lite_calls` 3 / `pool_max_reads` 6); running
  out closes out with one forced `select`, and selecting nothing falls back to the shipped triage.
- **Tool calling now works on DashScope too** — the Gemini-only refusal is gone (it was an argument
  about the walk, and it made the 6×-cheaper tier untestable here). **Verified live on qwen-plus,
  4/4**: parseable args + call id, result round-trips into the answer, real pool-agent schemas
  accepted. Bedrock/Ollama still raise. `tests/llm/test_tool_calling.py -m llm`.

### Also this session: hybrid BM25 re-tried properly, and it is now closed (D-065)
The user pushed back on D-032 — *one run does not mean it does not work; it may have been applied
wrongly.* Correct challenge: both of D-032's query sets were adversarial to BM25 by construction
(an LLM-generated tautology, and a CROSS-LINGUAL set where BM25 has no tokens to match). So it was
re-run on FiQA — same language, human qrels, 57,638 docs, cached vectors, **0 generation calls**.

**D-032 replicated** (fusion −0.18 nDCG@10) and **both rescue hypotheses failed**: stopword
filtering +0.001, rare-term gating −0.004. Then the question fusion cannot answer: of 1,706 gold
documents BM25 finds **10 (0.6%)** that dense misses at k=100 — so 0.6% is the ceiling on what a
*perfect* trigger could add, which closes the agent-tool/escalation design too. Harness verified
against two external numbers (dense 0.621 = §2.2; our BM25 0.235 vs BEIR's published 0.236).
`libkb probe-lexical` · SCORECARD §2.5 · 25 LLM-free tests.
**Scope kept honest:** this settles PROSE corpora with a strong embedder. An identifier-dense corpus
(article numbers, SKUs, error strings) is a different population — re-open it then, in one free run.

---

### ⚠️ THE TEST-SUITE HANG IS DIAGNOSED — and it is NOT a code regression
Both causes are environmental. Sessions 11 and 12 both lost time to this; do not re-derive it.
1. **Orphan pytest processes.** A killed/timed-out run leaves `python.exe` alive holding file locks,
   and one stale process silently stalls *every* later run — including a run of tests that pass in
   1.8s on their own. **Before believing any hang:**
   `Get-Process python*,timeout | Stop-Process -Force`, and also kill leftover `bash.exe` loops
   (`Get-CimInstance Win32_Process -Filter "Name='bash.exe'"` → check `CommandLine` for `pytest`).
2. **The venv is built on the Microsoft Store Python** (`WindowsApps\PythonSoftwareFoundation.Python
   .3.12_...`), whose app-container filesystem makes the seed/store writes pathologically slow.
   Rebuilding the venv on a python.org install is the real fix, and is the user's call.

**Proved, not assumed:** with every change stashed (tree == HEAD), `test_orchestrator.py` and
`test_store.py` hang identically. Small sets run fast — `test_selection` 25/25, `test_cascade` 9,
`test_agent_roles` 6, `test_config` 4, `test_conventions` 2. Run the suite in small batches, one
process each, and kill stragglers between batches.
⚠️ **Never `git stash` to run a baseline check without popping in the SAME command** — a stash plus
a timed-out shell once left this whole session's work sitting in `stash@{0}` with a clean tree.

---

## ⚡ SESSION 12: OLLAMA is the fourth provider (D-063) — open weights, generation only
Goal: a cheaper generation tier. Built, unit-tested, **UNMEASURED** — no quality claim yet.
Read `docs/OLLAMA.md` (setup + model shortlist + cost) and DECISIONS **D-063**.

- `LIBKB_MODEL=ollama/gpt-oss:120b-cloud` is the whole configuration. The `ollama/` prefix is
  **explicit on purpose**: Ollama serves `qwen3.5`/`gemma4`/`gemini-3-flash-preview`, so a bare-name
  rule would route them to DashScope or Google.
- LOCAL and CLOUD are one code path (`LIBKB_OLLAMA_HOST` + `OLLAMA_API_KEY`). Native `/api/chat`,
  not the OpenAI shim, for **server-enforced JSON schema** (the D-040 fix) and `think` (off by
  default — cloud models reason by default and that is billed GPU-time). **No new dependency.**
- `retrieval_mode=walk` still refuses on Ollama (tool calling is Gemini-only, D-016/D-017/D-027).
  The cascade — the default — is tool-free and runs on any model.
- **The embedder deliberately did NOT move** (Ollama Cloud has no embedder; switching invalidates
  every catalog row + every SCORECARD retrieval number). `_embed_ollama` exists so the head-to-head
  is one `reindex --fresh` into a SEPARATE db.
- Side-fix: `GET /api/models` labelled every non-Gemini model "dashscope" and gated availability on
  the DashScope key (a Bedrock model already read as unavailable). Now `LLM.provider_of()`.

### NEXT — the measurement that decides whether to adopt it
**Honesty, not accuracy, is the gating number.** qwen labelled 26/28 improvised nulls "high"
confidence (D-046) and cost 2.7 points of honesty where gemini held 99.3% (D-052).
`eval-multihop --nulls --save` on the candidate model FIRST, then the answerable set.
⚠️ Set `LIBKB_EVAL_CONCURRENCY` to your plan's concurrent-model limit (Free = 1, Pro = 3) — the
default is 8 and will queue or 429.

---

## ⚡ SESSION 11: PRODUCT features · PUBLISHED public (D-062)
Two arcs since the multi-agent work: product-level capabilities and a public release. **Product
features (D-062) are committed** (`bb53628`). Unit suite ran **clean at 284 earlier this session**
(a full re-run currently stalls on a Windows `os.replace` seed-write flake — environmental, not a
regression; see watch-outs). Read SCORECARD **§3.2** and DECISIONS **D-062**.
(A cost-accounting feature was also built this session and then REMOVED at the user's request — see
"Removed / relocated" below.)

1. **Product features (D-062, committed `bb53628`) — every one shaped to keep the answer call
   single-shot (no O(T²)):**
   - **Multi-turn chat** — `conversation/store.py` (transcripts, same gitignored db) +
     `agent/contextualize.py` (a lite call rewrites a follow-up into a STANDALONE query BEFORE
     retrieval; history never enters the cascade). Sidebar: title = first question,
     editable/deletable, pin ≤5. `enable_context_rewrite` default-on, free with no history.
   - **Semantic answer cache** (`cache/`) default-ON — a grounded, confident answer returns for a
     paraphrase with **0 LLM calls**. Honesty rules: never cache NOT_FOUND / uncited / low-confidence;
     precision-first threshold **0.92** (a cross-topic near-neighbour already sits at 0.875). Curatable
     + global toggle in the Observatory; a hit is transparent ("from cache" + citations).
   - **Synthesis route** (`agent/synthesizer.py`) for aggregative questions — wide scan → parallel
     lite MAP → strong REDUCE, cited; empty = NOT_FOUND. **UNMEASURED on purpose** (SCORECARD §5.6).
   - **Query decomposition — MEASURED & REFUTED** (SCORECARD §3.2). Unregistered by default; engine +
     prompts + tests kept so it reproduces. Added `force_route` (measurement knob).
   - **Observatory wired to REAL traffic** — KPIs + trajectories + trace replay from `GET
     /api/observatory`. REMAINING: analyzer-driven misroute heatmap + fixes (labelled PREVIEW only).
2. **PUBLISHED (committed through `e4c0194`).** Repo public at `github.com/LeDat98/toshokan_kb`,
   **PolyForm Noncommercial 1.0.0** (source-available; MIT intended later), measured-numbers README
   (NexusRAG-style). **The private-client, retail, ai-news, benchmark and eval data + the proposal
   deck are gitignored and were verified ABSENT from the remote** (multi-layer audit; D-020). Do NOT
   relax those ignores.
### Removed / relocated this session (housekeeping, at the user's request)
- **A cost-accounting feature built this session was fully REVERTED/DELETED** so no billing material
  can reach the public repo; the incident that prompted it is recorded only in the gitignored
  `.agent/private/COST_LEDGER.md`. ⚠️ The revert also removed an **eval-integrity fix** — so the
  default-ON answer cache can again corrupt an eval *re-run* (it replays its own prior answers to the
  judge, inflating the score). Real bug, zero billing content; re-apply as a standalone fix if wanted.
- **The private client's `library/domains/<client>/` directory was MOVED out of the repo** to a
  sibling folder outside the project (33 files, data intact; exact path given to the user), and the
  `.gitignore` comment + path that named the client were removed. The repo no longer contains the
  client name in any tracked file. (Unrelated, still local & gitignored: `docs/my_eval/` and the
  catalog db carry client-derived data — never in the repo.)

### NOT done / next session
- **Private eval-set hygiene (local only):** the 1000-case set's `raw_predefined` type is **~16%
  document fragments** (a line-wise split of hand-authored seed files turned body lines into
  "questions"). It drags that type's score for all models equally (no rank change) but the absolute
  number is wrong — filter or rewrite the 9 fragment cases before quoting per-type `raw_predefined`.
  (Eval data is private/gitignored; do not describe its contents in tracked docs.)

### Watch-outs specific to this session
- `.agent/private/` is gitignored and holds `COST_LEDGER.md` (real billing figures + the Gemini
  project id). It MUST stay untracked. The cost *implementation* was removed from the repo (above);
  this private note is the only surviving record and can be deleted on request.
- ⚠️ **`.gitignore` history:** an EARLIER commit's `.gitignore` named a client in a comment. That
  comment and its path are removed from the working tree, and `main` was rewritten locally to drop
  them — but **the rewrite has not been force-pushed**, so the old commits are still on the public
  remote. Local `main` is therefore 4 ahead / 4 behind `origin/main`; a plain `git push` cannot
  resolve it. Finishing this is `git push --force-with-lease origin main`, and it is the user's
  call to run (a force-push is destructive and outward-facing).
- The two dev servers from earlier sessions (backend :8000, vite :5173) are **stopped** (terminated,
  no crash). Restart with `./dev.sh` if needed.
- **Windows file-I/O flake in the unit suite (environmental, NOT a code bug).** `seed.apply` writes
  page files via `store._write_page_file` → `os.replace(tmp, path)` (atomic rename); on Windows that
  call intermittently STALLS at 0% CPU when Defender/the search-indexer holds a handle on the just-
  written `.tmp` (faulthandler pinned it to `store.py:516`). It surfaced mid-session after heavy file
  churn: `test_orchestrator_serves_a_cached_answer` and every seed-using test hang, though each passes
  in isolation and the suite ran clean at 284 earlier the same session. If the suite hangs, it is this,
  not a regression — run affected files singly, or add a repo/temp Defender exclusion. Worth a real fix
  later (retry-on-`PermissionError` around the `os.replace`), but do not "fix" the tests.

---

## ⚡ SESSION 10: the multi-agent architecture (D-061) — narration · roles · MCP/A2A seam · routing
Read `docs/AGENT_ARCHITECTURE.md` (the plan of record) and DECISIONS **D-061**. Built + tested
(**203 tests, ruff clean on touched files**); all default-safe. **COMMITTED** at `0da0915` (119 files)
— the "NOT committed" note that was here is stale; the whole session shipped.

1. **Design settled with the user, then built in phases.** Home-grown runtime, conform to the open
   protocols (MCP/A2A/AG-UI) as wire contracts — **no agent framework in deps** (Pydantic AI
   reference-only). `client.py` stays the single model gateway (D-016). Cost-aware: agentic only when
   it earns it. Honesty preserved: answers are NOT backend-token-streamed (the anti-fab gate must see
   the whole answer); the UI reveals the verified answer client-side.
2. **Narration (Phase A).** The cascade now emits the MIDDLE of the process (read/compose) + a
   first-person `thought` PIGGYBACKED on the triage & answer calls (near-free, the model's real voice).
   New `web/src/components/ThinkingTimeline.tsx`: a CoT timeline (live timer, auto-collapse on answer,
   NOT_FOUND terminal), narration built from the REAL event stream so it varies per query. The
   escalation "hmm" beats show only when the cascade truly escalates — live-verified: a supplier-penalty
   query the library can't answer produced two hmm beats then an honest NOT_FOUND (no fabrication).
3. **Agent roles + registry (Phase B).** `libkb/agent/roles/`: `AgentCard` (A2A-shaped) + `AgentRegistry`
   + Librarian/Answerer/Verifier wrapping the existing functions. The cascade RESOLVES librarian +
   answerer from the registry (load-bearing, behaviour-preserving). `/api/agents` lists the cards.
   Falsifiable test: a 5th agent registers + dispatches with no orchestrator edit.
4. **MCP/A2A seam (Phase C).** `libkb/tools/mcp.py`: MCP tool → `CapabilityAgent` + `to_tool_spec()`.
   `mcp` is an OPTIONAL extra; the seam is tested with a local tool. `/api/a2a/agent-card` exposes us as
   an A2A agent. **C.2:** `libkb/tools/calculator.py` — deterministic `safe_eval` (AST, never `eval()`)
   as a dispatchable tool AND a compute ROUTE.
5. **Front-door ROUTING — the orchestrator's own decision (not a separate agent).** `answer_query`
   decides the route per message BEFORE opening the catalog: registry-driven (any `route_when` card is a
   choice), biased to `search_library` (the cascade, default), fails safe. Concierge answers
   greetings/meta from persona + a TRUE library overview (read from the store, not invented).
   `LIBKB_ENABLE_ROUTER` default-OFF (the 190 pre-existing tests are untouched); enabled on the live
   backend and live-verified: a meta query answered directly with 0 cascade actions.

### NOT done / next session
- **Commit** — the whole session (D-061 + narration + A/B/C + routing) is in the working tree, unstaged.
- **Phase C.2 real MCP round-trip** needs `pip install -e ".[mcp]"` (client written, not unit-tested).
- **LLM tool-calling INSIDE the answerer** (mid-compose tool use) is deliberately deferred — cost +
  provider risk (native tool-calling is Gemini-only, D-027).
- **`client.py` has ~12 pre-existing ruff E501s** (from the earlier Bedrock/qwen work) — untouched, not
  this session's scope.

---

## ⚡ SESSION 9: text-index ADOPTED · the scale question answered · a reranker REFUTED
Read `docs/SCORECARD.md` §1.1, §2.4 and DECISIONS D-045..D-048 — that is the measured truth. Arc:

1. **`index_kind=text` shipped AND adopted on the live library** (D-045). 250 pages reindexed, 0
   generation, held-out cascade **96.7%** (SCORECARD §1.1). Flywheel code kept for the vocabulary
   bridge. Two eval-infra traps fixed (stale-target fail-soft, holdout remap).
2. **The basket is two knobs** (D-046): `cascade_min_confidence` split out from `cascade_max_pages`.
   MEASURED: basket=10 = **+8.7 answer** but the confidence gate is **USELESS on qwen** — qwen is
   overconfident (26/28 improvised nulls labelled "high"), so the gate can't buy back honesty. The
   gate is model-dependent → the user's product critique ("depend on the model less") retired it as
   the honesty lever. Mechanism kept (default off), harmless.
3. **Concurrency for eval** (D-047): `libkb/concurrency.py::parallel_map`, thread-safe token counter,
   `busy_timeout`. eval-multihop is now 8-wide (verified, no 429). Cut the tuning run from ~3h to
   ~15min. REMAINING: `runner.run_eval` + INGEST (needs a catalog write-lock).
4. **THE reframe (user):** target is not "95%" but "95% that HOLDS 2k→10k". Answered by the FiQA
   scale curve (D-048, §2.4, free): **R@50/R@100 are nearly scale-flat (−2.7pt 2k→10k); R@1/R@10
   collapse.** The scale problem is the NARROW window, not the sieve. Retrieval IS scale-invariant if
   you read wide.
5. **The obvious fix — a cross-encoder reranker — was REFUTED** (D-048). qwen3-rerank HURT FiQA R@1 by
   5–9 pts at every scale (strong embedder → reranker adds nothing). Joins NMS/BM25/digest/auto on the
   refuted list. **The de-facto reranker is the LLM triage; the lever is widening its window.**
6. **SHIPPED (D-049): retrieval DEPTH as one dial, three tiers.** `cascade_depth` ∈ {minimum=20,
   default=50, deep=100}; new defaults **basket=10, fetch=50**. MEASURED clean on MultiHop:
   73.9%→**84.0%** answer, honesty 92.7%→**91.0%**, 2.4× tokens. basket 3→10 is the big win (+8.7);
   fetch 20→50 adds +1.4 at flat honesty — scale insurance (its value grows with corpus size). The
   50 candidates are NEVER loaded into context: triage reads headers (~+4k tok, one call), only the
   basket (10 pages) opens. `fetch_n`/`k` derive from the tier (validator), still settable.
   Bottleneck has moved RETRIEVAL → SELECTION (triage picking from a 50-menu — the next lever).
7. **Robustness the wide window exposed:** `{"basket": null}` (Qwen "nothing relevant") no longer
   slices None; `answer_query_safe` now fails CLOSED on ANY exception + logs the full traceback (a
   bare TypeError would else 500 a real request). A rare (~0.5%) concurrency-only NoneType survives,
   is caught by that net, and will log its traceback (`answer_query_crashed`) next time it fires —
   NOT reproducible single-threaded (checked cascade 0/40, lookup 0/320); pinpoint from that log.
8. **A results dashboard Artifact** (scale curve + refuted reranker + tradeoffs) is published for the
   user. 176 tests green.
9. **SELECTION lever #1 — richer triage card — SHIPPED (D-050), small win.** Text-indexing had
   silently thinned the triage card (a text row stores an empty display text, so the `Answers
   questions like:` line never fired). `sections.py::query_snippet` restores the sieve's "why THIS
   page" as a model-free `Relevant passage:` line. MEASURED on a fresh TEXT-indexed MultiHop catalog
   (`benchmarks/multihop/catalog-text.db`, 2,077 pages, gemini-3.5-flash, 2 seeds × n=200):
   ANSWER 72.7%→**74.4%** (+1.7, both seeds up), coward 16.5%→**15.1%**, **honesty flat 47/48**,
   +7% tokens. Per-kind deltas were NOISE (swung oppositely seed0↔seed1, 4–6 cases). Shipped
   default-on (`triage_snippet_chars`, **0=off** is the A/B switch). 180 tests green.
   **What it proved by NOT moving:** comparison ~71%, temporal ~50% (the 2+-source questions) are
   untouched → the multi-hop ceiling is NOT card richness. A/B harness: `scratchpad/ab_snippet.py`.
10. **SELECTION lever #2 — coverage-aware triage prompt — REFUTED (D-051).** Told triage a multi-part
   question needs a page for EACH part (`prompts/triage_coverage.md`, gated by `triage_coverage`,
   now default-OFF). 2 seeds × n=200, snippet on both arms: ANSWER −1.7/−0.6, temporal flat then
   −2.2. Did not lift multi-hop. `scratchpad/ab_coverage.py`.
   **The diagnostic that reframes the thread** (`scratchpad/diag_multihop.py`, model-free, live text
   catalog, AllGold@k over n=1439 comparison+temporal): retrieval is NOT the wall (@50 = 97.9%); the
   **BASKET is** — the answerer opens `cascade_max_pages=10`, and even a perfect triage caps
   multi-source at AllGold@10 = **75%** (@20 = 93%). **comparison (~73%) already sits at its
   basket-10 ceiling** → selection can't help it, only a bigger basket (token-priced, measure vs
   lost-in-the-middle). temporal (~50%) is 25pts under its 75% ceiling → a real selection/synthesis
   gap; localise with a probe of the ACTUAL triage basket's article coverage before spending.
   NEXT real lever: `cascade_max_pages` sweep for multi-source, then temporal's residual. The
   "improve SELECTION" frame was half-wrong: for comparison the lever is basket SIZE, not smarts.
11. **The basket lever — SHIPPED (D-052): `cascade_max_pages` 10 → 20 — the session's real win.**
   Cashing in the D-051 diagnostic. Sweep 10/15/20 × 2 seeds (`scratchpad/sweep_basket.py`):
   ANSWER +4.5 (both seeds), **temporal +7–9** (58% both seeds — the multi-source kind finally
   moved), comparison +3, coward −3–4 (answerer commits instead of drowning), **honesty HELD 99.3%**
   null-only n=301 (the qwen honesty cost of D-043 was a qwen artefact; gemini does not pay it),
   +22% tokens. basket=15 was a dead spot; 20 is the jump. It is a CEILING not a floor (opens only
   what triage picks) so single-hop corpora barely pay. Default reverts with `LIBKB_CASCADE_MAX_PAGES=10`.
   Two threads left open (backlog 2c): answer 77–79% still trails the AllGold@20=93% ceiling (sweep
   basket>20, DON'T extrapolate); temporal 58% floor = its own selection/synthesis gap (probe the
   actual basket's article coverage). 180 tests green, ruff clean. All in working tree, NOT committed.
12. **Selection precision MEASURED, and it reframes everything (probe 2c, `scratchpad/probe_selection.py`).**
   Ran the ACTUAL triage (no answer stage), n=150 multi-source: triage keeps only **69% AllGold** (vs
   sieve ceiling 93% — it DROPS 24 pts of gold) AND under-fills the basket to **~4.4 pages** (cap=20
   irrelevant). It is WORSE than a blind sieve top-10 (75%). So header-triage is a poor *selector* —
   yet the end-to-end system still answers 77–79%, because the **LAST-RESORT net** (open top-20 in
   full when triage is insufficient) does the real work. Triage is nearly vestigial for coverage.
13. **Cheap-reader selector (D-053) — the user's "subagent reads bodies to pick" idea — REFUTED.**
   `triage_mode="read"` (`_triage_read`, lite tier reads 10 bodies). MEASURED n=80: ANSWER −7.0 (every
   kind fell, inference −11.5), coward +5.6, and only ~7% cheaper ($3.94→$3.68/1000q). Bad trade. A
   lite model selects worse than strong-header-triage, AND picking whole pages short-circuits the
   last-resort net that was carrying accuracy. Kept default-off. `scratchpad/ab_reader.py`; per-model
   token accounting added to the client (`input_by_model`) to price it — that stays.
14. **BONUS — pinpointed + fixed the ~0.5% concurrency NoneType (D-054, backlog #1).** The A/B logged
   its traceback: `catalog.count()` on a sqlite connection SHARED across the thread pool; sqlite3 does
   not serialise concurrent execute() → torn `fetchone()`. Added a reentrant `RLock` to `Catalog`
   guarding every connection touch. 0 crashes across the D-053 runs (smoke n=8 had hit one).
   180 tests green, ruff clean on touched files. Everything still in working tree, NOT committed.

### Reranker access note (for later): the user's DashScope key works on `dashscope-intl.aliyuncs.com`
for `qwen3-rerank` (native rerank API, NOT compatible-mode) — their MaaS host does not serve it.
gte-rerank-v2 is EOL. But it's refuted, so this is only for reference.

## ⚡ SESSION 8: a 2,000-page corpus + a second provider (Qwen) + the first EXTERNAL numbers
Read `docs/SCORECARD.md` first — it is the measured truth, kept current. This block is the narrative
of *how we got the session-8 numbers and what is still open*.

**Why this session existed:** the user wanted a corpus big enough to trust (231 pages / 30 questions
was too small — the flagship A/B's ±3.4-point spread was the size of its own lead). We imported
**MultiHop-RAG** (609 news articles → 2,079 pages, its own library at `benchmarks/multihop/`, tree =
category▸publisher▸article) and wired **Alibaba Qwen** (DashScope) as a second provider to run the
evals cheaply. **The big corpus did not give prettier numbers — it exposed eight real defects that
231 pages never could.** That was the point.

### The numbers that now exist (all in SCORECARD; the ones that changed a belief)
- **FiQA — the first externally-valid number in the whole project** (648 human questions, human
  qrels, 57,638 docs). nDCG@10 **0.621**, R@1 **0.316**, R@10 **0.701**, R@100 **0.920**.
  **VERIFIED bit-for-bit by `pytrec_eval` (the official TREC scorer) — the first metric check this
  session that CONFIRMED instead of refuting.** And still mediocre: **30% of real questions miss the
  top-10**, which for a cascade that only opens ~10 is a hard fail. The R@10→R@100 gap (0.70→0.92) is
  the recurring story: the sieve FINDS the evidence, the window is too NARROW. Pure text-index, **0
  generation tokens** — the flywheel did not participate and the sieve still reached this.
- **bench-multihop (2,255 external ground-truth queries): text-index ≥ question-index on EVERY
  metric, and costs 0 generation** (AllGold@20 text **93.5%** vs questions 69.5%). `both`(RRF) is
  WORSE than text alone. The question flywheel cost ~3.1M generated tokens to LOSE.
- **P6 (honest NOT_FOUND), 301 unanswerable questions, fail-closed code:** basket=3 **92.7%** honest
  (22 improvised), basket=10 **90.0%** (30 improvised). The one rule the project calls
  non-negotiable, measured at scale for the first time, and it HOLDS.
- **Answer accuracy (n=200): basket=3 73.9%, basket=10 77.8%.** The bigger basket wins exactly where
  multiple documents are genuinely needed (comparison +9.1, temporal +4.4) and is flat on inference.

### THE architecture finding of the session (this is the load-bearing one)
**The cascade uses ONE knob — `cascade_max_pages` — to control TWO different things:** *how much
evidence* the answerer sees AND *how eager* it is to answer at all. MEASURED: basket 10 beats basket 3
on multi-hop accuracy (+3.9) but costs 2.7 points of honesty (30 vs 22 improvisations). That is not a
forced trade — the two are just tied to one dial. **The fix is to split them:** raise the basket (the
sieve has the evidence — R@100 0.92, AllGold@20 0.935) AND add a SEPARATE confidence gate in
`compose_answer`, tuned independently. This is a small architecture change, and only the n=301 run
revealed it — at n=24 the 2-case honesty gap was noise. **This is the top design item now.**

### Eight defects the big corpus exposed — none appeared at 231 pages (SCORECARD §7)
1. title pasted twice → 250-char filename → crash. 2. no slug length cap → Windows 260-char crash.
3. **DashScope doesn't enforce JSON schema → Qwen returns `["…"]` not `[{vi,en}]` → parser crash →
   `index_page_safe` swallowed it → 439/2,079 pages (21%) silently never entered the catalog, import
   printed SUCCESS.** 4. **Qwen silently REFUSES some content** (`choices: null` on an Epoch Times
   article; Gemini handles it). 5. **`generate_json` "repaired" a truncated response into an INVENTED
   answer + `sufficient:true` — a P6 violation, 40/301 one-char answers.** 6. `embed()` had no retry
   and leaked raw httpx errors past `answer_query_safe`, killing a paid 301-run. 7. **DashScope client
   had NO timeout → a hung socket froze a run for 30 min at 0% CPU.** 8. FiQA has empty documents →
   Gemini rejects an empty Part → whole batch dies.
   ALL FIXED, all with the same principle now in the code:
   **a broken call must fail CLOSED (silence), never OPEN (an invented answer); and `compose_answer`
   must not take the model's `sufficient` on trust** (2-char floor).

### Provider wiring (Qwen / DashScope) — shipped, `client.py` is still the only genai gateway
- Route by MODEL NAME (`settings.dashscope_prefixes`): `LIBKB_MODEL_LITE=qwen-flash` is the whole
  config. `qwen-plus/flash/max` selectable. Endpoint is the user's dedicated MaaS host
  (`DASHSCOPE_WS_HOST`), reached OpenAI-compatibly at `/compatible-mode/v1`, `timeout=60`, our own
  retry loop.
- **Tool-calling is Gemini-ONLY and DashScope RAISES rather than degrade** (D-027: cheap models
  collapse at navigation). The cascade is tool-free, so every model runs it; the walk is not.
- **The catalog is LOCKED to one embedder** (`catalog_meta.embed_model`) — mixing two vector spaces
  is meaningless, and the lock raises rather than return nonsense. Changing embedder = `reindex
  --fresh`, wholesale.
- **UI model picker** shipped: a button + `/model` in the Ask composer, `GET /api/models`, model
  rides per-request (`with_model`, no global, no reload, greys out Qwen when routing_mode=walk).

### Cost this session ≈ $3.5 (mostly Qwen eval + FiQA embed). Verified prices in SCORECARD §4.
Our DEFAULT answer model `gemini-3.5-flash` ($9/1M output) is the most expensive thing available;
`qwen-plus` is 4.5× cheaper and passed a live smoke test — but **quality is NOT A/B'd yet** (§5).

### What is DECIDED by evidence but NOT YET SET as a default (do this next session)
- ✅ **`index_kind` → text — SHIPPED AND ADOPTED ON THE LIVE LIBRARY (D-045).** `LIBKB_INDEX_KIND`
  config, default `text`; `index_page` branches (text = 0 generation, embeds the body; questions =
  the flywheel; both). Catalog LOCKED to one representation (mirrors the embedder lock) so a partial
  reindex can't silently re-create metric bug 6.6. `reindex --index-kind {questions,text,both}`.
  **The live library was reindexed to text** (user's call): **250 pages, 250 rows, kind=text, 0
  generation**. Held-out cascade **96.7% (29/30), Gate PASS, 3,960 tok/query** — see SCORECARD §1.1.
  NOT a clean A/B (corpus changed since the 93.3% questions run); it is the honest number for what
  ships today. The one miss is the ANSWERER (sycophancy to a loaded question — the sieve reached the
  exact page). 168 tests green. The `questions` flywheel is kept (not deleted) for the still-unsettled
  vocabulary bridge (§5.1, questions wins R@1 on our colloquial-VI set); switch back = reindex --fresh.
- ⚠️ **Two eval-infra traps a re-ingest sprang, both fixed:** (a) `runner.py::_deepest_reached` now
  counts a stale `target_page_id` a miss instead of crashing a paid 30-query run (fail-soft, like
  ingest); (b) `evals/holdout.json` had its 3 PDF-book targets remapped to the re-ingested pages
  (frozen at old ULIDs). Regression test in `test_evals.py`. A held-out set is frozen data; a book
  re-ingest silently invalidates any target that pointed into it — watch for this on the next reingest.
- ✅ **The confidence gate MECHANISM shipped (D-046).** `cascade_min_confidence` (ordinal
  low<medium<high) is now a knob SEPARATE from `cascade_max_pages`: a `sufficient` answer below the
  floor becomes an honest NOT_FOUND. Default `low` = gate OFF (behaviour unchanged). 169 tests green.
  **The VALUES are unmeasured** — raising the basket + choosing the floor is a MEASURED decision, not
  yet run. Confound to design around: eval-multihop is on `qwen-plus`, DashScope doesn't enforce the
  schema (D-040), so Qwen may omit `confidence` (→ read as `medium`); a fully clean signal needs
  Gemini, which is ~$7 on 500 queries (over budget). Tuning grid = basket {3,10} × floor
  {low,medium,high} on the MultiHop null set (honesty) AND answerable set (accuracy). **← the top
  remaining item is now the TUNING RUN, a spend+model call for the user.**

### Still the user's call (untouched, do NOT do unprompted)
- Commit the **138 AI-News files** to git? (Retail is gitignored by D-020; this domain is not.)
- Delete + re-ingest the **mis-parsed PDF book** — its 13k-char `References` page is STILL indexed
  and retrievable as "evidence". Destructive; needs explicit go-ahead.

### Open evaluation gaps (SCORECARD §5) — the honest limits
- **The vocabulary bridge is UNSETTLED and it matters.** MultiHop (formal, entity-rich English) says
  text-index wins; our n=30 held-out (colloquial VI → English jargon) says question-index wins R@1
  83.3% vs 60.0%. **Neither corpus settles the other.** Do NOT retire the flywheel on MultiHop alone
  — measure a colloquial/cross-lingual set at n≫30 first.
- MultiHop's own queries are artificial (they name their sources: "as reported by The Verge and
  TechCrunch") — good for the sieve/AllGold, weaker as a P6 or naturalness test.
- **BSARD** (1,108 real citizen legal questions, 6-lawyer labels, 22,633 hierarchical statute
  articles, FRENCH) is the accepted benchmark for LATER phases: legal domain + the real near-dup
  stress test. On the backlog, not started. CC BY-NC-SA (research/internal only).
- Not measured: cross-encoder rerank (attacks R@1, the weakest number), Qwen-vs-Gemini answer
  quality, whether the 93.3% cascade A/B survives the AI-News import, synthesis, recency.

### The other big lever, still not built: CONCURRENCY
Ingest and eval are fully sequential. 2,079 pages ≈ 40 min; a 10k-page legal corpus would take ~5
hours. This is what actually blocks the user's stated goal. Backlog #1.

---

## ⚡ SESSION 7: ingest is now a RULE, not a pile of cases (D-037) · AI-News corpus is in (D-038)
The user's objection, verbatim and correct: *"if every new document type needs a code change, that is
not a product."* It came up because the AI-news corpus writes its summary under `summary:` and retail
under `description:` — and the tempting fix (an alias list) is exactly the pile of cases he meant.

**Three rules replaced the cases. None of them is per-format.**
1. **The ingest CONTRACT** — every leaf ends with title + one_line + keywords + questions, whatever it
   came from. Missing fields are **generated in the lite call that was already generating the
   questions** (0 extra tokens). Frontmatter is a SHORTCUT, never a dependency. **A new source format
   costs zero lines of code.**
2. **The recursive splitter** — cut at structure → a piece still over budget is cut at ITS OWN
   structure → only when structure runs out does size get a vote → merge strays forward. Budgets in
   `Settings` (`split_max_page_tokens=2000`, `split_min_page_chars=40`), not hardcoded.
3. **`libkb probe-granularity <folder>`** — the loop from Ekimetrics' `adaptive-chunking`, NOT its
   metric. Theirs scores whether a chunk *looks* well-formed; ours scores whether the librarian *finds*
   it. Prints its bill first, spends only on `--yes`, caches leaves shared between strategies.

**What the splitter fixed, measured on the real PDF in the library:**

| before | after |
|---|---|
| `3 Methodology` — **9,992 chars, 12 unused sub-headings inside it** | **9 sub-pages**, all ≤1,687, each citable |
| `References` — **13,136 chars, INDEXED** (our largest page; not knowledge) | on the shelf, `indexable: false`, never in the sieve |
| every page prefixed with the 70-char paper title | the document's own title is not one of its chapters |

**What the probe said (118 files, 674 lite calls):** `default` came out **byte-identical to
`as-authored`** — the rule looked at 118 authored files and **cut nothing**. That is the proof the rule
is generic: it acts on the broken PDF and stays silent where the author was already right. `tight`
(500t) is a real trade — reading 4.5× cheaper, R@1 −6.3 — and we did **not** take it: LOO regime, the
100%s are inflated, held-out first.

**AI-News is imported** as its own domain (NOT under `AI`, which is a textbook on the same subjects):
116 pages · 9 books · 3 shelves. Library is now **231 pages / 3 domains**. Whole-library LOI page R@1
reads **56.1%** (was 39.3%) — **do not quote it.** Per domain:

    domain      rows   LOI R@1   LOI R@10   top-1 stolen by ANOTHER domain
    AI           240     50.0%      91.7%             11.7%   ← the textbook pays for the news
    AI News    1,266     68.6%      94.5%              1.3%
    Retail       680     34.9%      89.0%              0.4%

**Retail never moved.** The average rose because news is an EASY population (one named entity per
page). Two real findings: the predicted **AI-textbook ⇄ AI-news collision is real and costs 11.7%**;
and the **near-duplicate flood did NOT arrive** (R@10 held everywhere) — because this corpus is *many
documents, one entity each*, not *many documents, one entity*. It is coming; we did not earn its absence.

**A FOURTH metric bug, caught before it was reported.** The probe's `near-dup` column (cosine ≥ 0.90)
said 65% and looked like the flood. Checked against the LIVE library, which routes at 93.3% and has no
duplication problem: **95.7% of its pages clear the same bar** (nearest-other-page cosine min 0.878,
median 0.942). D-028 already knew this. Replaced by `margin = score@1 − score@10` — a difference
between two numbers from one run, so there is no threshold to set wrong.

## ⚡ THE BIG ONE: the LLM was the SIEVE; it should be the ORACLE (D-034 · docs/RETRIEVAL_REDESIGN.md)
The user's challenge — *"the corpus is 200k tokens and one answer burns 50k. This librarian is not
professional."* — is right, and no patch fixes it. **The agentic tree-walk is the wrong shape of
machine.**

- **80% of the bill is rent.** A walk sees **8,601 tokens** of distinct information; we pay
  **45,268**. Every turn resends the whole conversation → **O(T²)**. That is why the spine cap won
  (−62%) and the digest lost (+17%). **You cannot patch your way out of a quadratic.**
- **Greedy tree descent is provably not Bayes-optimal**, even with perfect node scorers (Zhuo et
  al., ICML 2020) — a wrong turn at depth 1 is unrecoverable. D-029's finding, as a theorem.
- **The hierarchy does NOT accelerate search** (I claimed it did — wrong). To score a container by
  max you must score every page inside it. And a sound cheap bound degrades exponentially in
  dimension (Ram & Gray, KDD 2012) — which is why ANN uses HNSW, not trees. **The tree is for
  citation, curation and people. Not for search.**
- **PageIndex does not walk either.** Their OSS retrieval is **2 LLM calls** (whole tree in one
  prompt → node list → answer). No embeddings, no agent, no rollback. And **98.7% is soft: their own
  judge says 90.7%**; the rest came from humans re-labelling misses. **Our 96.7% already beats their
  honest number.** We lost on architecture, not quality.

**Shipped behind `LIBKB_RETRIEVAL_MODE=cascade` (default still `walk` until the A/B lands):**
```
① PROPOSE 0 LLM  embed + rank every page (the sieve)
② TRIAGE  1 LLM  librarian sees PATHS + SECTION HEADERS (59 tok/page, not 1,571) → fills a BASKET
③ ANSWER  1 LLM  the basket opens ONCE: the chosen SECTIONS → cited answer + sufficiency
④ EXPAND  only if insufficient — pop the next candidates (free) and answer once more
```
**Live smoke: 2 calls, 2,462 tokens (walk: 49,120 / 9–13 calls) — 20× cheaper**, correct answer,
citing two *different shelves* — which the walk could only reach by backtracking.

- **The basket is the user's idea and it is the structural point:** text in the navigator's
  conversation is re-billed every turn; text in the answerer's call is billed **once**. So the full
  page must never enter the conversation. Not read-then-shrink (that was the digest). **Don't read.**
  Page 1,571 tok · headers **59** · two biggest sections **516** → **13.5×**. 78% of pages already
  have headings. Also defuses the mis-parsed **12,842-token** page.
- **No diversification.** MEASURED: NMS costs **10 points of recall** (96.7% → 86.7%) — it suppresses
  the right page for being *similar to* a good one, and that similarity was corroboration. The
  redundancy worry is real; the fix is dedupe at INGEST + **K=3** (where the recall curve flattens).

### The cascade's first eval was decided by 3 bugs — and 2 were in the METRIC (D-035)
First run: **83.3% vs the walk's 96.7%**, at **2,010 vs 49,120 tokens**. The prediction was
falsified — until I asked the one question that mattered: **did the sieve fail, or the oracle?**
**In all FOUR losses the sieve had ranked the target page #1.** The embedder was never the problem.

1. *(mine)* The librarian **threw away the right page for being opened at the wrong chapter**: on
   "insufficient" the code went looking for *other* pages instead of re-opening the one it held.
   → Now: **re-open in full before widening.** One call, no search.
2. *(mine)* The triage prompt **taught him to give up** — and his card was thin. He returned an empty
   basket on a page the sieve ranked #1 at cosine 0.845. → The bar is *"could this help?"*, and the
   card now carries **the catalog question that MATCHED** (it was sitting in `Hit.text`, unused).
3. **THE JUDGE PENALISED A BETTER ANSWER.** The cascade hands the answerer pages from *across the
   library* — that is its advantage. The judge saw only the target page, found "external concepts",
   and marked it wrong. Case 13 gave the reference's own point **plus** a correct second point from
   another page, and was failed **for being richer**. → *"The reference is a floor, not a fence."*
   **Re-judged: 2 of 4 flip → 90.0%, not 83.3%.**

**Third time this session the METRIC was the broken thing, not the system** (page_acc/ancestors →
page_acc/shelf-bias → the judge). Each time it cost a full re-run of the arm. **Fixed for good:
`libkb eval --save` persists every answer; `libkb rejudge` re-grades a saved run for almost nothing.
The answers are the expensive artifact; grading them is not.**

**Both remaining losses are non-architectural**: pages of one **mis-parsed PDF book** (`**2 Related
Work**` — a converter emitting bold headings, now cleaned at ingest by `clean_title`), and **case 7
is a broken eval case** (the paraphrase "how is *this new setup* better…" lost its referent).


**Phase:** P1 ✅ + P2a ✅ + P2b ✅ + **P2c (flywheel + catalog) ✅** + **P3 eval + routing redesign ✅
(A/B-confirmed)**. Remaining P3: `routing_mode=auto`, shelf hygiene, classifier, synthesizer,
trajectory logger, Observatory. Then P4 (maintenance).

## THE NUMBERS THAT COUNT — A/B on the HELD-OUT set (D-031)
n=30, same 30 paraphrased questions both arms (`evals/holdout.json`), `--mode walk` (no catalog),
strong model. **This is the honest measurement; everything above 86% you may remember was leaked.**

| | A: `book` (old) | B: `shelf` (shipped) | Δ |
|---|---|---|---|
| **answer_acc** ← the gate | 90.0% | **96.7%** | **+6.7** |
| page_acc (diagnostic only) | 66.7% | **80.0%** | +13.3 |
| avg hops | 5.2 | **4.3** | −0.9 |
| avg backtracks | 2.1 | **0.9** | **−57%** |
| input tokens/query | 53,941 | 49,120 | −9% |

- **Paired: 6 rescues, 0 losses** (2 on answer, 4 on page). Not one regression. Route B *dominates*.
- ⚠️ **Be honest about the strength**: the accuracy delta is **2 flipped cases** (McNemar p≈0.5). At
  n=30 it is NOT significant on its own. The conclusion rests on **convergence**: the free 904-question
  centroid proxy (+8.2%), the **backtrack collapse** (the direct fingerprint of the premature-commitment
  mechanism), and 0 losses. Don't quote +6.7 as if it were precise.
- **Gate armed:** `min_answer_acc=0.90` (shelf baseline − 1.6 se). `min_page_acc` stays None on
  purpose — gating it punishes the system for answering correctly from a sibling page.

## PART II shipped (D-032) — and 3 of its recommendations were refuted by measurement
`docs/ROUTING_REDESIGN.md` §6–§10. Everything reproduced first, then built. **138 tests green.**

**Consolidated eval (D-033), same 30 held-out questions, everything on:**
`answer_acc` **96.7% — unchanged, Gate PASS.** But **tokens 49,120 → 57,667 (+17%)**, hops 4.3 → 4.5.
Accuracy held; **cost regressed.** The page digest is therefore **OFF by default** (see below).

| § | what | status |
|---|---|---|
| 8.1 | cross-references (`probe-misshelved` → `build-crosslinks`) | ✅ shipped; reproduced 49% exactly |
| 6 | page digest — shelve a page once the librarian walks on | ❌ **OFF: it made queries 17% DEARER** |
| 7 | catalog shortlists a too-wide shelf, with an escape hatch | ✅ shipped; **fixed a gate-bug of my own** |
| 7.3 | hybrid BM25 fusion | ❌ **MEASURED AND REFUTED** — off by default |
| 8.2 | entry vocabulary (term ring, `kind='term'`) | ✅ built, **deliberately unmeasured** — needs a reindex |
| 8.3 | `reframe` — the query evolves as the walk teaches it words | ✅ shipped |
| 8.4 | **trajectory logger + `libkb harvest`** | ✅ shipped — *the answer to the founding worry* |
| 2.2#5 | `routing_mode="auto"` | ❌ **DROPPED on the doc's own test** (below) |

- **`auto` is dead.** §9 said: check how many A/B cases landed on a *well-separated* shelf. Answer:
  **9 of 30** — and shelf mode lost **0 of the 9**. On `Merchandising` (92.7% separable, where the
  book hop should matter most) flattening *improved* things. No cow, no fence.
- **§7.3 refuted on BOTH query distributions**, at every fusion weight, monotonically:
  generated-question LOI page R@10 **90.7% → 78.6%**; held-out colloquial R@1 **83.3% → 43.3%**.
  A reader's paraphrase reuses almost none of the library's exact words, so BM25 grabs the common
  ones and drags noise up. Index kept (`hybrid_shortlist` flag) — the rare-term mechanism is real,
  it just is not what these queries are made of. Revisit with real traffic.
- **§6 was wrong TWICE — about where the cost is, and about whether the digest pays.**
  (a) It read the 49k bill as "2.5k menu + 46k pages", forgetting a menu is resent every turn too.
  MEASURED: menu 2,707 × 5 = **13,535 (49%)**; pages ≈30%. §0a's spine cap was worth −62%; the big
  lever was already pulled. (b) Shipped ON, the digest made queries **17% DEARER at identical
  accuracy**. The compression works — per-turn input *plateaus* (8,009→8,525→8,531→8,426) instead of
  climbing (4,999→7,018→8,644→10,941→**13,660**) — but the librarian, robbed of the full text,
  **compensates**: 6 pages instead of 5 (hitting the page budget), 13 turns instead of 11. §6 named
  this risk in its own falsifier. **Now OFF by default; code, tests and knob all kept.**
- **Bug found by reading the eval log:** `read_page` had no re-read guard — a page read twice was
  handed to `compose_answer` twice (one source counted as two) *and* charged twice against the page
  budget. Harmless before, a live trap with the digest on. A re-read is now **free**: full text back,
  no budget slot, no duplicate evidence. It attacks the compensation mechanism directly and is the
  one change that could make the digest pay — **unmeasured, so the digest stays off.**
- ⚠️ **The +17% is not yet attributed.** The bundle was evaluated as a bundle; the digest is the
  prime suspect on *mechanism*, but cross-refs (which add readable pages to a menu) and the larger
  prompt are also in it. An isolation run would settle it. 30 walks.
- **The §7.4 bug I shipped and the test caught:** in shelf mode `open_book` was an alias for
  `open_shelf`, so on a too-wide shelf the "escape hatch" **looped back into the shortlist**. The
  text promised an exit that did not exist — i.e. the shortlist was a gate, the exact sin §7.4 names.
- **A privacy bug caught in `build-crosslinks --dry-run`:** it would have written a link from a
  *tracked* AI book to a *private, gitignored* Retail page (D-020). Cross-domain links now refused.

### The two things the A/B taught us that were NOT in the plan
1. **The cost model was wrong in magnitude.** §2.4 predicted −63% tokens; reality is **−9%**. After the
   D-030 cap the menu is ~2.5k of a **~50k** bill. **The real cost driver is the PAGES read** (2.1–2.3
   per walk, full markdown, resent every subsequent turn). *That is the biggest remaining lever in the
   system* and nobody had noticed it. The case for route B rests on accuracy + thrash, not on price.
2. **The leak was worth ~20 points.** Held-out book-mode `page_acc` is **66.7%**, not 86%. Strip the
   generator's jargon and routing gets much harder. But `answer_acc` is 90% — the system was serving
   readers far better than `page_acc` ever admitted.

## Older numbers, kept for context (n=50, LEAKED case set — do not quote these)

| run | mode | model | page | note |
|---|---|---|---|---|
| old baseline | walk | 3.5-flash | 86% | leaked: questions came from the catalog rows the system indexes |
| production | shortcut | 3.5-flash | 100% | 0 hops, but LEAKY squared (D-024) |
| cheap-model | walk | 3.1-flash-lite | 54% | **32-pt collapse → reverted** (D-027) |

- **flash-lite cannot navigate** (D-027): backtracks collapsed 2.1 → 0.4 while found-rate ROSE to 96% —
  it commits early and is confidently wrong. Two tiers now: strong to navigate, lite for bulk
  generation (question flywheel, paraphrasing, the answer judge).

## ROUTING REDESIGN shipped, NOT yet A/B-validated (D-029 · docs/ROUTING_REDESIGN.md)
**The book is storage, not routing.** Conditional per-hop accuracy of the 86% baseline:
domain 100% → shelf 96% → **book 89.6%** → page **100%**. Page-picking inside a book is already
perfect; the whole 14-pt loss is the book hop. And it is **not fixable with better descriptions** —
sibling books are only **82.3%** separable by their own content (`libkb probe-separability`, free),
so the LLM is already beating the tree's intrinsic ceiling. `Root Cause Analysis` ⇄ `KPI
Interpretation` confuse each other in BOTH directions (19x/14x) = one book split in two.

`open_book` was an **irreversible commitment** — wrong book ⇒ the right page vanishes from every menu
the agent can see, and the only escape is the 12-hop thrash we kept observing. Now `routing_mode=shelf`
(default): `open_shelf()` lays out the shelf's whole union TOC grouped by book; the agent picks a page
directly. Books stay intact on disk, in ingest, and in citations. `max_shelf_toc_entries=60` guards
scale; `routing_mode=book` still works so the A/B can run.
- Free proxy says +8.2% (route B 76.4% vs A 68.3%; 91 rescues / 17 losses). **It is a centroid proxy,
  not an LLM walk — trust the sign and the mechanism, not the magnitude.**
- Live smoke: a vi question that used to misroute now answers in **3 hops / 0 backtracks**.
- ✅ **The A/B was run and route B WON on every axis** — see the table at the top (D-031).
- ⚠️ **Eval metric caveat found:** ground truth is the page a question was GENERATED from, but another
  page can answer it perfectly well (the smoke did exactly that). The metric understates real quality.
  → **Fixed by D-030**: the primary metric is now the ANSWER, not the page.

## Then the user reviewed that code and found 2 blockers + a bad metric — all fixed (D-030)
The A/B above was about to be run under conditions rigged **against** the design being tested. Four
fixes, all landed, all free:

1. **`one_line` was 8x its budget.** MEASURED over the 125 live TOC entries: **median 1013 chars,
   max 1436**. `ingest/survey.py` was copying each source file's whole frontmatter `description:`
   (an abstract) into `TOCEntry.one_line` (a spine label). Retail only — the seed is fine (max 160).
   A menu is **resent on every later turn**, so this was taxing every hop; and when every option is
   a 1000-char paragraph, *everything sounds relevant* (the documented cause of LLM mis-selection).
   Capped at **render** (all 3 renderers — the stored value is never trusted, so the live library is
   fixed with **no migration**) **and** at ingest. `max_one_line_chars=120`.
   **MEASURED: union-TOC menus 28,032 → 6,319 tokens (−77%);** worst shelf 14,221 → 2,584 (−82%).
2. **The scale guard counted rows, not tokens.** The KPIs shelf (50 pages) passed a 60-row guard
   while emitting a **14,221-token** menu. Both ceilings are real and both are now enforced: rows
   bound the *option count*, tokens bound the *cost* (`max_shelf_menu_tokens=6000`). With the cap in
   place **no live shelf trips either guard** — which is the point: had the token guard landed
   *without* the cap, the KPIs shelf would have fallen back to book mode and route B would never
   have been tested on the one shelf it exists to fix.
3. **`page_acc` is biased against route B — it is now a diagnostic, not the metric.** Route A picks
   among ~8 pages inside a book; route B sees ~42 at once, so it far more often lands on a *sibling
   page that answers perfectly* — which `page_acc` scores a MISS. The property that makes route B
   good was being counted as a defect. **Primary metric is now `answer_acc`**: an LLM judge over the
   final answer (`evals/judge.py`, on `model_lite`), told to judge the answer and not its
   provenance. The eval also reports **`mean_input_tokens`**, so §2.4's cost model became a
   measurement. Every mode now runs through `answer_query` — what is graded is what a reader gets.
4. **The gates are DISARMED.** Every threshold was calibrated in book mode, on the leaked set,
   against `page_acc`. All three premises are false now. A stale gate is worse than none: it fails
   honest work and waves through real regressions. Re-arm `min_answer_acc` from the A/B minus ~1.6
   se (≈0.09 at n=30).

Also built, **not yet run** (it costs tokens): `libkb make-holdout` — restates each eval question the
way a reader who has NOT read the page would ask it, and **saves it to disk** (both A/B arms must
score byte-identical questions). The default eval set is leaked: its questions ARE the catalog rows.

## The catalog gate was HARMFUL — fixed (D-028). Run `libkb probe-catalog` (FREE, no LLM calls)
The user challenged whether ingest-time questions help at all, given an unbounded question space.
The free held-out probe says the challenge was RIGHT about the gate:

| gate | LOO ("user paraphrases") | LOI ("a question we never thought of") |
|---|---|---|
| cosine ≥ 0.82 (as shipped) | fires 99.9% · 70.9% right · **est 71%** | fires 92.6% · 40.1% right · **est 43%** |
| **margin ≥ 0.05 (now)** | fires 34% · **95.5%** right · **est 89.3%** | fires **12.6%** · 71.6% right · est 84.2% |
| no catalog (walk only) | 86% | 86% |

- Top-1 cosine **crowds at ~0.88–0.90**, so an absolute gate fires on *everything* — it is not a
  confidence signal. The **margin over the runner-up page** is. With it, the catalog **goes quiet on
  questions it doesn't recognise** and the walk takes over — which is exactly the property that was missing.
- vi↔en: a VI question finds its page from EN-only rows 98.3% — but ⚠️ that was measured on vi/en rows
  that are TRANSLATIONS OF THE SAME question, so it only shows the embedder matches translations.
  It does NOT justify dropping the Vietnamese rows. **Keep both languages** (corrected in D-028).
- **The flywheel's durable value is NOT the shortcut.** Ingest-time questions are supply-side guesses
  (a cold start) and can't cover an unbounded space. Their real payoff so far: they ARE the routing eval
  set (gave us 86% and exposed the book-description bug) and a vocabulary bridge. The missing half is
  **demand-side** — log real queries + their resolved pages and index those (P3 trajectory logger).

## New this session — P2c question flywheel + card catalog (D-022, D-023)
- **`libkb/ingest/questions.py`** — `generate_questions` (prompt `gen_questions.md`, bilingual: 4
  intents × vi+en = 8 rows/page) + `index_page` (generate → embed → write catalog rows; idempotent:
  removes a page's old rows first).
- **`libkb/catalog/`** — `db.py` (SQLite schema, WAL, `check_same_thread=False`), `store.py`
  (`Catalog`: add_page/remove_page/clear/count/page_ids + brute-force cosine `search` returning best
  DISTINCT pages, matrix cached & rebuilt on write; `Hit`), `search.py` (`lookup`: embed query as
  RETRIEVAL_QUERY, rank, optional threshold).
- **Flywheel hooks** — `importer.commit` + `pipeline.ingest_document` index each filed page when a
  `catalog` (and llm) is passed; `approve_placement` indexes on approval. All best-effort (per-page
  errors are logged, never abort). `index_page_safe` is the shared guard.
- **`agent/tools.ask_librarian`** — 7th tool, offered by `navigator` ONLY when a catalog is present
  (`ASK_LIBRARIAN_SPEC` appended to TOOL_SPECS). Returns suggested paths, budgeted `max_ask_librarian=2`.
- **`agent/orchestrator`** — catalog fast path in front of the walk (answerer-gated, falls back to a
  walk if insufficient); auto-opens the on-disk catalog if the db file exists and closes what it opened.
- **CLI** — `libkb reindex [--domain X] [--fresh]` (batch-build the catalog), `import --index`,
  `ingest --no-index`. New trace glyphs `⚡` (lookup) and `?` (ask).
- **API** — `/query` gets the shortcut + ask_librarian for free (auto-open); `/ingest` always indexes
  filed pages; `/import` indexes when `ImportBody.index=true`; approve indexes moved pages. StepEvent
  now documents `ask|lookup` actions.
- Config: `catalog_top_k=5`, `catalog_shortcut_threshold=0.82` (eval-tunable). `db_path` unchanged
  (`library/_catalog/catalog.db`, gitignored).

## Verified live (gemini-3.5-flash, this session)
- `libkb reindex --domain AI --fresh` → 240 questions across 30 pages (8/page).
- `ask "How does reranking with cross-encoders improve RAG retrieval quality?"` → **catalog shortcut,
  0 hops / 0 backtracks**, correct citation `AI ▸ RAG ▸ Advanced RAG Techniques ▸ Reranking & Cross-encoders`.
- `ask "How do I tune a diesel engine turbocharger?"` → shortcut DECLINED → walk used `ask_librarian`
  twice (budget held) → honest NOT_FOUND (10 hops / 9 backtracks). Both P2c paths proven.
- `reindex --domain Retail` → catalog now **920 questions across 115 pages** (AI 30 + Retail 85).
- Eval numbers: see the table at the top. (Those gate verdicts are now void — gates disarmed, D-030.)
- `rebuild-views --domain Retail` → **17 discriminative descriptions regenerated** (D-025): each book
  now states what it covers AND points to the sibling that covers the rest ("for EOQ/safety stock, see
  *Inventory Management*"). Books are materialized views now, like every other non-leaf.
- **104 unit tests green** (all LLM-free); ruff clean; all 10 API routes up.

## What exists and works (cumulative)
- P0 backend + P1 navigator: config, Gemini client (neutral tool-calling D-016 + thought-signature
  D-017), fs LibraryStore, seed (AI: 30 pages now incl. an ingested PDF), `agent/` (tools/navigator/
  answerer/orchestrator), `library/views.py`. CLI `ask --trace`, `seed`, `init`, `rebuild-views`.
- P2a import (folder → tree, shelf strategies) + P2b document ingest (parse/split/classify/pipeline,
  confidence gate → `_uncatalogued`, review/approve). P2c flywheel + catalog (this session).
- **API** (`libkb/api/`): query SSE + library GETs + import/ingest SSE + review/approve. App =
  `libkb.api.main:app`. Frontend wired for Ask/Library/Ingest (Observatory still on mock.ts).

## How to run
- `./dev.sh` (Git Bash) — API :8000 + vite :5173. `./dev.sh check` = tests+lint+build.
- Build the catalog once so lookup works: `.venv\Scripts\libkb.exe reindex` (whole library, costs
  tokens) or `... reindex --domain AI`. Without a catalog the system just walks (P1 behavior).

## Next actions — the queue in docs/ROUTING_REDESIGN.md §2.5, in order
1. ✅ §0a `one_line` cap · 2. ✅ token-budgeted scale guard · 3. ✅ `answer_acc` judge + token report
   (all D-030, all free, all landed).
4. ✅ **THE A/B — DONE, route B won** (D-031). Gate armed at `min_answer_acc=0.90`. Re-run any time:
   ```
   LIBKB_ROUTING_MODE=book  libkb eval --cases evals/holdout.json --mode walk   # control  90.0%
   LIBKB_ROUTING_MODE=shelf libkb eval --cases evals/holdout.json --mode walk   # shipped  96.7%
   ```
   `evals/` is gitignored — the questions are generated FROM the private retail corpus (D-020).
5. **NEW, and now the biggest lever: page-read cost.** The A/B showed the menu is ~2.5k tokens of a
   ~50k bill; the rest is **pages, resent every turn**. Ideas, unvalidated: read fewer pages
   (`max_pages_per_nav=6` — the walk averages only 2.1, but the tail reads 6); drop a page's full text
   from the conversation once it has been judged irrelevant; summarise instead of re-sending.
   **Measure before believing** — the same cost model already misled us once by 7x.
6. `routing_mode="auto"` — per-shelf flattening driven by `probe-separability` (blanket level-removal
   loses to selective flattening in every study that compared them). Today only library-wide
   `book`/`shelf` exist. `AI ▸ LLM` is 100% separable and should keep its book hop.
7. §5 shelf hygiene, landed **separately** so credit is attributable: merge `Root Cause Analysis` +
   `KPI Interpretation` (19x/14x mutual confusion = one book); split `Retail ▸ KPIs` (5 books, 42
   pages, 74.4% separability — worst on every metric).
8. Then: `agent/classifier.py` (front door), `agent/synthesizer.py` (cross-book), trajectory logger
   (**the demand-side flywheel — the real answer to the unbounded question space**), Observatory UI.

## Cost (the user flagged ~$10–15/day during these runs — read this before spending)
- The spend was **one-off experiments, not usage**: reindex (115 pages × [1 generate + 1 embed]) and
  3 × 50-case walk evals (~1.5k calls). Reindex is DONE — don't repeat it.
- **`--mode walk` eval is the worst-case cost by construction** — it deliberately disables the shortcut
  to measure raw routing. Never read eval cost as production cost.
- The big saver is the **shortcut**, not the model tier: a known question = ~2 calls (a cheap embed +
  one compose) vs a 5–10 generate walk. Warming the catalog lowers per-query cost more than any model swap.
- Model tiers are now split by measured difficulty (D-027) — bulk question generation runs on flash-lite.

## Watch out
- **The mis-parsed PDF book is STILL in the library**, with its 13k-char `References` page indexed and
  retrievable as "evidence". `libkb/ingest/split.py` fixes it *at ingest*; existing data is untouched.
  Re-ingesting means deleting `library/domains/ai/shelves/rag/books/pdf-retrieval-augmented-question-answering/`
  and its catalog rows first — **do not do this without the user asking**; it is destructive.
- **`survey_folder` silently ignores `.md` files at the ROOT of an imported folder** (only child
  directories become books). On the AI-news import it dropped `README.md` and `_TEMPLATE.md` — right by
  luck, not by design. A flat folder of loose pages would vanish without a word.
- **116 AI-news pages are untracked in git** (`library/domains/ai-news/`, 138 files). Unlike Retail
  (private, gitignored by D-020) nothing has been decided here. Ask before committing them.
- `AI News ▸ Platforms & Productivity` holds **63 pages** — over `max_shelf_toc_entries=60`, so it
  routes through the shortlist path by design. Worth watching, not fixing.
- **PowerShell background quirk (cost me 3 failed launches):** a *background* PowerShell command that
  STARTS with `.venv\Scripts\python.exe` intermittently dies with "The module '.venv' could not be
  loaded". Use the **Bash tool** for background runs: `cd "/c/Users/.../LibaryKnowledgeBase" &&
  .venv/Scripts/python.exe -m libkb.cli ...`. And do NOT "fix" it by calling python via an ABSOLUTE
  path — `Settings` reads `.env` relative to the CWD, so that breaks key loading instead.
- `web/src/api.ts` ↔ `libkb/api/events.py` are one contract (D-018) — new StepEvent actions
  `ask|lookup` render generically in the current frontend; give them icons when wiring Observatory (P3).
- The shortcut gate is now the **margin** (`catalog_margin=0.05`), not absolute cosine — the old 0.82
  cosine gate is a near-inert sanity floor only. Re-tune from `libkb probe-catalog` (free), never by
  intuition: absolute cosine looks like confidence and is not (D-028).
- **`one_line` in the live TOCs is still 1000+ chars on disk.** The render cap makes that harmless for
  the agent, the API and the description prompts, but a re-ingest of Retail is what actually cleans
  the data. Do not "fix" it by hand-editing `toc.json` (leaf pages are the source of truth, D-004).
- The catalog is opened per query/ingest (fresh connection, loads all vectors). Fine now; cache it on
  `app.state` if query latency or catalog size grows.
- `reindex`/`import --index`/`ingest` spend real tokens (a generate + embed PER page). Deliberate only.
- `library/_catalog/*.db` is gitignored; `index_page` writes ONLY to the db (no `_meta.json` churn), so
  reindex doesn't dirty `library/`. Retail catalog rows would embed private content → keep the db local.
- Everything Windows: `.venv\Scripts\...`, cp932 console (CLI + API force UTF-8), no uv.
- Only non-gated pages are indexed at ingest; parked (uncatalogued) books are indexed at approve time.
