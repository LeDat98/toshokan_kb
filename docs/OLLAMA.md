# Running LibraryKB on open-weight models (Ollama)

Why this exists: our default answer model, `gemini-3.5-flash`, is **the most expensive thing in
SCORECARD §4** ($9.00 / 1M output). Ollama gives the same work to open-weight models — locally at $0
marginal cost, or on Ollama Cloud for a flat subscription instead of per-token billing.

What moves: **generation** (triage, answering, question generation). What does **not** move: the
**embedder** — see §5, and D-063 for why that half is deliberate.

---

## 1. Sign up and connect

**Local (free, no account).** Install from [ollama.com/download](https://ollama.com/download), then
`ollama pull <model>`. The daemon listens on `http://localhost:11434`; nothing else to configure —
that is already the default in `Settings`.

**Ollama Cloud (an account, for models too big for this machine).**

1. Create an account at [ollama.com](https://ollama.com) and pick a plan (§3).
2. Create an API key at **ollama.com/settings/keys**.
3. Put it in `.env` — the file this project never edits for you:

   ```
   OLLAMA_API_KEY=<your key>
   LIBKB_OLLAMA_HOST=https://ollama.com
   ```

   (Or `ollama signin` on the CLI and keep the local host — then `-cloud` models are transparently
   offloaded and no key is needed in `.env`. Both work; the explicit host is the one to prefer for a
   server deployment, where there is no interactive login.)

Local and cloud are the **same code path** in `llm/client.py`; only the host and the bearer token
differ.

## 2. Point the project at a model

Routing is by model name, through an explicit `ollama/` prefix (D-063 — without it, `qwen3.5` would
be captured by the DashScope prefix rule, and `gemini-3-flash-preview`, which Ollama also serves,
would go to Google):

```bash
# the answer/triage tier
LIBKB_MODEL=ollama/gpt-oss:120b-cloud
# the bulk tier (question generation, context rewrite, judging, synthesis map)
LIBKB_MODEL_LITE=ollama/qwen3.5:9b
# optional: offer them in the UI picker (the prefix is added for you if you omit it)
LIBKB_OLLAMA_MODELS=gpt-oss:120b-cloud,qwen3.5:9b
```

Smoke-test it without touching the library:

```powershell
.venv\Scripts\libkb.exe ask "what does this library cover?" --trace
```

**One thing does NOT work on Ollama, by design: `LIBKB_RETRIEVAL_MODE=walk`.** Tool calling stays
Gemini-only (D-016/D-017/D-027) and this provider raises rather than degrade silently. The
**cascade** — the default, and the 14× cheaper path — is tool-free and runs on every model here.

### Knobs this provider adds

| env | default | what it does |
|---|---|---|
| `LIBKB_OLLAMA_HOST` | `http://localhost:11434` | local daemon, or `https://ollama.com` |
| `OLLAMA_API_KEY` | *(empty)* | required for cloud, ignored locally |
| `LIBKB_OLLAMA_THINK` | `false` | `false`/`low`/`medium`/`high`/`max`, or empty to leave the model's default. **Most cloud models reason by default and you are billed GPU-time for every reasoning token** — on triage that buys nothing. |
| `LIBKB_OLLAMA_TIMEOUT` | `180` | seconds. A cold local model must load before it answers. |
| `LIBKB_OLLAMA_EMBED_QUERY_PREFIX` | *(empty)* | §5 |
| `LIBKB_OLLAMA_MODELS` | *(empty)* | extra entries for the UI picker |

## 3. What it costs

**Ollama Cloud does not bill per token.** It bills **GPU time**, inside a flat plan:

| plan | price | concurrent models | note |
|---|---|---|---|
| Free | $0 | 1 | light use; hourly/daily caps |
| Pro | $20/mo (or $200/yr) | 3 | "50× more usage than Free" |
| Max | $100/mo | 10 | "5× Pro" — **new subscriptions paused** as of this writing |

Ollama does not publish the caps as numbers, so **you cannot compute the break-even in advance** —
you measure it. What we can compare is the other side, from SCORECARD §4 (measured, n=500 eval):

| | 500 queries | ≈ per 1,000 |
|---|---|---|
| `gemini-3.5-flash` (our default) | **$6.75** | ~$13.50 |
| `qwen-plus` | $1.50 | ~$3.00 |
| Ollama Cloud Pro | — | **$20/month, flat** |

So Pro pays for itself against the *current default* at roughly **1,500 queries/month**, and against
`qwen-plus` at roughly **6,700** — if the plan's caps let you run them. For this project's actual
spending pattern (eval runs of 200–1,000 queries, plus reindexes) that is well inside the win, and
local models make the bulk tier free outright.

⚠️ **Concurrency is the limit that will bite first, not price.** `eval_concurrency` and
`ingest_concurrency` default to **8**, and the Free plan allows **1** concurrent model (Pro: 3). An
8-wide eval against Free will queue or 429. Set `LIBKB_EVAL_CONCURRENCY` / `LIBKB_INGEST_CONCURRENCY`
to match your plan, or run those against Gemini and keep Ollama for interactive use.

⚠️ **Local is free but not fast.** A 2,079-page ingest took ~40 minutes sequentially on a hosted API;
on a laptop GPU the answer tier is the wrong place to economise. Local is genuinely good for the
**embedder** (0.3–0.6B, runs on CPU) and a **small lite tier**; the answer tier realistically wants
the cloud.

## 4. Which model

The shortlist below is what fits *this* workload — the cascade asks a model to (a) pick a basket
from 20–100 candidate cards and (b) answer from 10–20 pages **with citations, in JSON, and to refuse
when the evidence is thin**. Long-ish context, reliable structured output, and Vietnamese-question →
English-page cross-lingual reading. It is a shortlist to A/B, **not a ranking we have measured.**

| tier | candidate | why |
|---|---|---|
| answer/triage | **`gpt-oss:120b-cloud`** | the general workhorse; MoE, so it is cheap for its size, and its instruction-following is the most predictable of the set |
| answer/triage | **`qwen3.5:122b`** (or `:35b`) | Qwen is the strongest open family on Vietnamese, which is exactly our vocabulary-bridge problem — and `qwen-plus` already passed a live cascade smoke test (SCORECARD §4) |
| answer/triage | `deepseek-v4-flash` | 284B total / 13B active — a lot of capability per GPU-second |
| answer/triage | `glm-5.x`, `kimi-k2.x`, `minimax-m3` | bigger and stronger; more GPU-time per answer |
| lite / bulk | **`qwen3.5:9b`**, `gemma4:12b`, `nemotron-3-nano:30b` | question generation and context rewrite are the easy jobs (D-027); these are small enough to run locally |

**The risk of going cheap here is HONESTY, not accuracy** — and we have measured it. On `qwen`, the
confidence gate turned out useless because the model is *overconfident*: 26 of 28 improvised answers
to unanswerable questions were labelled "high" confidence (STATE session 9 / D-046). And basket=10
cost 2.7 points of honesty on qwen while **gemini held 99.3%** at basket=20 (D-052). P6 — no evidence
⇒ an honest NOT_FOUND — is the one rule this project calls non-negotiable, so **the number to watch
when swapping in an open model is the null-set honesty rate, not the answer rate.**

The measurement that settles it (MultiHop's 301 unanswerable questions + its answerable set):

```powershell
$env:LIBKB_MODEL="ollama/gpt-oss:120b-cloud"
.venv\Scripts\libkb.exe eval-multihop --limit 200 --save   # accuracy
.venv\Scripts\libkb.exe eval-multihop --nulls --save       # honesty ← the one that decides it
```

## 5. The embedder does not move (yet)

Two embedders are two coordinate systems; a cosine between them is not a worse number, it is **not a
number**. Pointing `LIBKB_EMBED_MODEL` at an Ollama model therefore invalidates every catalog row and
every retrieval figure in the SCORECARD. The catalog enforces this — it records its embedder and
raises on a mismatch rather than return nonsense.

Also: **Ollama Cloud hosts no embedding model.** Its embedders (`embeddinggemma:300m`, `bge-m3`,
`qwen3-embedding:0.6b/4b/8b`, `mxbai-embed-large`) are local-only — which is fine, they are small and
run on CPU.

The path is implemented, so the head-to-head is a clean experiment rather than a rewrite:

```bash
LIBKB_EMBED_MODEL=ollama/bge-m3
LIBKB_DB_PATH=./library/_catalog/catalog-bge.db   # a SEPARATE db — never mix
# then: libkb reindex --fresh   and compare R@1/R@10 on the held-out set
```

`bge-m3` is the natural first candidate (multilingual, symmetric, needs no prompt prefix).
`qwen3-embedding` and `embeddinggemma` were trained with a **query-side instruction prefix**, which is
how open embedders express the asymmetry gemini spells `RETRIEVAL_QUERY` vs `RETRIEVAL_DOCUMENT`.
That prefix is configuration, not a guess we make for you:

```bash
LIBKB_OLLAMA_EMBED_QUERY_PREFIX="Instruct: Given a web search query, retrieve relevant passages\nQuery: "
```

Our own colloquial-Vietnamese held-out set is the right bed for this comparison, because the
vocabulary bridge (SCORECARD §5.1) is the open question a different embedder could actually move.
