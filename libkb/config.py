from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# How many candidates each retrieval depth tier fetches and hands to triage (see `cascade_depth`).
_CASCADE_WINDOW = {"minimum": 20, "default": 50, "deep": 100}
# 'auto' thresholds on CORPUS SIZE in pages (D-058), read off the measured points 113 / 2077 / 57k:
#   < SMALL → 20/basket10   ·   SMALL..LARGE → 50/basket20   ·   >= LARGE → 100/basket20
_AUTO_SMALL_PAGES = 500
_AUTO_LARGE_PAGES = 10_000


class Settings(BaseSettings):
    # case_sensitive=False so the existing `.env` entry `Gemini_API_Key` matches GEMINI_API_KEY
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    gemini_api_key: str = Field(alias="GEMINI_API_KEY")

    # A SECOND provider (Alibaba DashScope / Qwen), reached through its OpenAI-compatible endpoint.
    # Routing is by MODEL NAME, not by role: any model whose id starts with one of
    # `dashscope_prefixes` goes to DashScope, everything else to Gemini. So setting
    # `LIBKB_MODEL_LITE=qwen-flash` is the whole configuration — no second set of role flags.
    #
    # ⚠️ THE EMBEDDER IS NOT A DROP-IN. Two embedders are two coordinate systems; a cosine between a
    # Gemini vector and a Qwen vector is not "less accurate", it is MEANINGLESS. Swapping
    # `embed_model` therefore invalidates every catalog row AND every number we have measured on it
    # (LOI recall, the cascade A/B). It is safe only as a full, separate reindex — which is worth
    # doing as a head-to-head, but never halfway. `catalog_meta` records which embedder built the
    # index so a mixed catalog fails loudly instead of quietly returning nonsense.
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    # the account's endpoint host; `DASHSCOPE_WS_HOST` is the name the user's .env already uses
    dashscope_host: str = Field(default="dashscope-intl.aliyuncs.com", alias="DASHSCOPE_WS_HOST")
    dashscope_prefixes: tuple[str, ...] = ("qwen", "text-embedding-v")

    # A THIRD provider: AWS Bedrock (Anthropic Claude). Same routing-by-model-name rule — any model
    # id starting with a `bedrock_prefixes` entry goes to Bedrock via boto3, which reads the
    # standard ~/.aws credentials/region ITSELF (we never open that file). Region falls back to this
    # if the AWS profile sets none. Answer/triage only — tool-calling stays Gemini (D-016/D-017).
    bedrock_region: str = Field(default="us-east-1", alias="AWS_REGION")
    bedrock_prefixes: tuple[str, ...] = (
        "anthropic.",
        "us.anthropic.",
        "global.anthropic.",
        "eu.anthropic.",
    )

    # Two tiers by MEASURED difficulty (D-027). `model` drives navigation/answering — the eval
    # showed flash-lite collapses there (page 54% vs 86%), so it stays on the strong tier.
    # `model_lite` drives easy, high-volume work (question generation at ingest).
    model: str = Field(default="gemini-3.5-flash", alias="LIBKB_MODEL")
    model_lite: str = Field(default="gemini-3.1-flash-lite", alias="LIBKB_MODEL_LITE")
    embed_model: str = Field(default="gemini-embedding-001", alias="LIBKB_EMBED_MODEL")

    # What the UI's model picker may offer. `model` above is the DEFAULT; this is the menu, and a
    # query carries its choice per request — so switching costs nothing and reloads nothing.
    # The EMBEDDER is deliberately absent from this list: it is not a runtime choice (see the
    # catalog's embedder lock in catalog/store.py), it is a property of the index on disk.
    selectable_models: tuple[str, ...] = (
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "qwen3-max",
        "qwen-plus",
        "qwen-flash",
        "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    )

    library_dir: Path = Field(default=Path("./library"), alias="LIBKB_LIBRARY_DIR")
    db_path: Path = Field(default=Path("./library/_catalog/catalog.db"), alias="LIBKB_DB_PATH")

    # The book is a unit of storage and citation, not of routing (docs/ROUTING_REDESIGN.md).
    # "shelf": the librarian opens the whole shelf's union TOC and picks a page — no book
    # commitment. "book": the legacy walk that made the agent choose a book first. Both work;
    # keep "book" available so the A/B can be re-run.
    # HOW the library is searched (docs/RETRIEVAL_REDESIGN.md). **A/B-CONFIRMED (D-036).**
    #
    #   "cascade" — propose (free ANN) → triage on section headers → open the basket once → expand
    #               only if the answerer says the evidence is thin. **2–3 LLM calls.**
    #               The embedder SIEVES; the LLM JUDGES. That is the right way round, and it is what
    #               our own numbers had been saying all along (embedder: top-10 recall 90.7% but
    #               top-1 39.3%; LLM: superb on a handful, ruinous per call).
    #
    #   "walk"    — the agentic tree-walk. 9–13 LLM calls, each resending the whole conversation, so
    #               cost is O(T²): MEASURED, a walk sees 8,601 tokens of distinct information and we
    #               pay 45,268 for it. And greedy tree descent is provably NOT Bayes-optimal even
    #               with perfect node scorers (Zhuo et al., ICML 2020) — a wrong turn at depth 1 is
    #               unrecoverable. Kept as the control arm; it is not the thing to build on.
    #
    # FAIR A/B, same 30 held-out questions, same corrected judge:
    #                   answer_acc   page   book   shelf   found   tokens/query   LLM calls
    #   walk               93.3%     73.3%  83.3%   93.3%   100%      66,558        9–13
    #   cascade            93.3%     90.0%  93.3%  100.0%   100%       4,711         2–3
    # Identical accuracy. Better routing at every level. **14× cheaper.** Both gates PASS.
    retrieval_mode: Literal["walk", "cascade"] = Field(
        default="cascade", alias="LIBKB_RETRIEVAL_MODE"
    )

    # Front-door routing (D-061): let the orchestrator DECIDE whether a message is social/meta
    # (answer directly, no retrieval) or a knowledge question (the cascade — the default). Default
    # OFF: a measured knob that adds one cheap lite call per query. Enable LIBKB_ENABLE_ROUTER=true.
    enable_router: bool = Field(default=False, alias="LIBKB_ENABLE_ROUTER")
    # Force ONE front-door route, bypassing the lite classifier — a MEASUREMENT knob. An eval can
    # send every query to `decompose` (which still self-selects: it defers a non-compound question
    # to the cascade), so the mechanism is measured without the router's conservative selection
    # muddying it. Empty = normal routing. A non-empty value also turns routing ON (not both).
    force_route: str = Field(default="", alias="LIBKB_FORCE_ROUTE")

    # MULTI-TURN CONTEXT (chat history). A follow-up ("tell me more about it") is rewritten into a
    # STANDALONE query by one lite call BEFORE retrieval, so the cascade stays single-shot and
    # history never enters the expensive calls (the O(T²) trap the retrieval redesign avoids). Only
    # fires when a conversation history is actually present, so it is a no-op — and free — on the
    # first turn and for every stateless (CLI/eval) caller. `context_history_turns` bounds how many
    # recent messages the rewrite sees. Default ON: without it, multi-turn simply does not work, and
    # the cost is one cheap lite call paid only on genuine follow-ups.
    enable_context_rewrite: bool = Field(default=True, alias="LIBKB_ENABLE_CONTEXT_REWRITE")
    context_history_turns: int = Field(default=6, alias="LIBKB_CONTEXT_HISTORY_TURNS")

    # SEMANTIC ANSWER CACHE. A question that MEANS the same as one already answered is served the
    # cached answer — 0 LLM calls, instant. Default ON (the user's call). Trust is preserved by the
    # honesty rules in cache/lookup.py (never cache a NOT_FOUND, only grounded+confident answers)
    # and by a PRECISION-first threshold: a wrong hit serves the wrong question's answer, so it errs
    # toward a miss. MEASURED (2026-07-21, SEMANTIC_SIMILARITY, gemini-embedding-001): reranking
    # paraphrases sit at 0.92–0.93, but a DIFFERENT topic "What is chunking in RAG?" already sits at
    # 0.875 (the shared "in RAG" inflates it, the D-028 crowding). So 0.92 catches near-duplicate
    # rephrasings while clearing the 0.875 cross-topic with margin — recall is modest BY DESIGN
    # (only genuine near-duplicates hit). Watch the cache panel and tune per corpus.
    enable_answer_cache: bool = Field(default=True, alias="LIBKB_ENABLE_ANSWER_CACHE")
    answer_cache_threshold: float = Field(default=0.92, alias="LIBKB_ANSWER_CACHE_THRESHOLD")
    answer_cache_margin: float = Field(default=0.0, alias="LIBKB_ANSWER_CACHE_MARGIN")
    answer_cache_min_confidence: Literal["low", "medium", "high"] = Field(
        default="medium", alias="LIBKB_ANSWER_CACHE_MIN_CONFIDENCE"
    )
    # Q-to-Q matching wants a symmetric task; SEMANTIC_SIMILARITY is the right gemini task type.
    answer_cache_embed_task: str = Field(
        default="SEMANTIC_SIMILARITY", alias="LIBKB_ANSWER_CACHE_EMBED_TASK"
    )
    # RETRIEVAL DEPTH — one dial, three tiers (D-049). The scale curve (D-048, §2.4) showed the
    # sieve is scale-invariant only if the window is WIDE: R@10 collapses as the corpus grows
    # (0.95→0.70 over 2k→57k) but R@50 barely moves 2k→10k and R@100 flatter still. The reranker
    # that would convert a wide window into a sharp top-1 was REFUTED (a strong embedder needs
    # none), so the lever is simply how many candidates TRIAGE sees. The tier is cheap because the
    # cost is asymmetric: width is how many HEADERS triage reads (one call, ~+4k tokens for 50), NOT
    # how many pages the basket OPENS (`cascade_max_pages`, the real cost, a separate knob — D-052).
    #   minimum — 20 candidates. The pre-D-048 behaviour; leanest.
    #   default — 50. R@50 is near scale-flat to 10k; +1.4 answer / flat honesty over minimum.
    #   deep    — 100. For huge corpora where R@100's extra flatness pays (57k: 0.920 vs 0.863).
    #   auto    — pick the tier from CORPUS SIZE at query time (D-058). The scale curve says the
    #             value of a wide window GROWS with the corpus; a 113-page library needs 20, a
    #             57k one needs 100. Only the catalog knows its size, so 'auto' resolves per query.
    cascade_depth: Literal["auto", "minimum", "default", "deep"] = Field(
        default="auto", alias="LIBKB_CASCADE_DEPTH"
    )
    # Fetched-pool and triage-batch sizes. 0 = derive from the depth tier (the normal case); set
    # them explicitly for fine control, or to exercise the batched multi-round widening with a small
    # `cascade_k` (production runs k == fetch_n, i.e. the whole window triaged in one call).
    cascade_fetch_n: int = Field(default=0, alias="LIBKB_CASCADE_FETCH_N")
    cascade_k: int = Field(default=0, alias="LIBKB_CASCADE_K")
    # The basket — how many pages the answerer OPENS — is a TIER too (D-058), two rungs measured:
    #   10 — enough on a small/single-source corpus (retail 113pp: basket 10 ≈ 20, and it halves the
    #        answer tokens the p90 was blowing through).
    #   20 — pays where multiple sources are genuinely required (MultiHop 2077pp: +4.5 answer,
    #        +7–9, honesty held 99.3%; AllGold@20 = 93% vs @10 = 75%).
    #   auto — 10 below the small-corpus threshold, 20 above (resolved per query from corpus size).
    # `cascade_max_pages` > 0 is the explicit numeric override (fine control/tests); 0 = use tier.
    cascade_basket: Literal["auto", "10", "20"] = Field(
        default="auto", alias="LIBKB_CASCADE_BASKET"
    )
    cascade_max_pages: int = Field(default=0, alias="LIBKB_CASCADE_MAX_PAGES")
    cascade_max_rounds: int = Field(default=2, alias="LIBKB_CASCADE_MAX_ROUNDS")
    # `cascade_max_pages` (the basket) was ONE knob doing TWO jobs: how much evidence the answerer
    # sees AND how eager it is to speak (more pages → more looks relevant → more "sufficient": true,
    # right AND wrong). MEASURED (D-043): basket 10 beats basket 3 on multi-hop accuracy (+3.9) but
    # costs 2.7 points of honesty on qwen. Not a real trade — the two were just tied to one dial. On
    # gemini the honesty cost did not even appear: basket 20 held 99.3% null-only (D-052). This is
    # the OTHER dial, split out: a floor on
    # answerer's OWN confidence, deciding whether the library speaks, tuned independently of basket
    # size. An answer below this confidence becomes an honest NOT_FOUND (fail-closed, P6). Ordinal.
    # Default "low" = accept any confidence (today's behaviour, gate effectively off) — raise it in
    # lockstep with a bigger basket so evidence goes UP without honesty coming DOWN with it.
    cascade_min_confidence: Literal["low", "medium", "high"] = Field(
        default="low", alias="LIBKB_CASCADE_MIN_CONFIDENCE"
    )
    # a mis-parsed PDF landed a 12,842-token "page" in the library; one read of it wrecks a query
    cascade_max_page_tokens: int = Field(default=4000, alias="LIBKB_CASCADE_MAX_PAGE_TOKENS")
    # The query-relevant passage shown per candidate on a TEXT index (D-050): the sieve's reason for
    # ranking a page, made visible to triage in place of the empty display text a text row stores.
    # ~200 chars ≈ 50 tokens/candidate — the same order as the section headers already on the card.
    triage_snippet_chars: int = Field(default=200, alias="LIBKB_TRIAGE_SNIPPET_CHARS")
    # SELECTION mechanism (D-053 experiment): "headers" = triage reads section HEADERS on the strong
    # model (the shipped cascade). "read" = a CHEAP subagent reads the top-N candidate BODIES on the
    # lite tier and picks the basket — the diagnostic showed header-triage drops 24 pts of gold, so
    # reading content might select better AND cheaper (it reads few bodies on a cheap model, then
    # the strong answerer opens only the picks). triage_read_n bounds how many bodies it reads;
    # triage_read_chars truncates each so one giant page cannot blow the selector's budget.
    triage_mode: Literal["headers", "read"] = Field(default="headers", alias="LIBKB_TRIAGE_MODE")
    triage_read_n: int = Field(default=10, alias="LIBKB_TRIAGE_READ_N")
    triage_read_chars: int = Field(default=2000, alias="LIBKB_TRIAGE_READ_CHARS")
    # SPEC B — expert consult (D-057). The audit settled what the failure actually is: of the
    # answers the strict grader called improvisation, 62% were legitimate synthesis (applying
    # frameworks that ARE in the evidence), 33% that PLUS invented specifics, 4% fabrication. So
    # the goal is not abstention (which would destroy the 62%) but banning the invented specifics:
    # a prompt that licenses principled reasoning yet forbids undocumented figures/lists, and a CODE
    # check that every number in the answer exists in the evidence — the fabrications were numbers.
    answer_ban_invented_specifics: bool = Field(default=False, alias="LIBKB_ANSWER_BAN_INVENTED")

    # SUFFICIENT-CONTEXT gate (D-056). The literature's answer to the exact failure we measured:
    # relevance is NOT sufficiency — evidence can be on-topic and still lack the answer, and RAG
    # *paradoxically* makes a model MORE confident (and less willing to abstain) when handed such
    # context. So classify sufficiency BEFORE generating: insufficient ⇒ abstain, and we never pay
    # for the answer call. Runs on the LITE tier (a focused classification, not generation).
    # Cite-or-abstain (D-055) checked whether a quote EXISTS; this checks whether the evidence is
    # ENOUGH — which is where the 80% improvisation actually lives.
    answer_sufficiency_gate: bool = Field(default=False, alias="LIBKB_ANSWER_SUFFICIENCY_GATE")

    # Cite-or-abstain grounding gate (D-055): the answerer must return VERBATIM quotes from the
    # evidence; we verify each by fuzzy char-n-gram match against the real page text (CODE, not the
    # model's word), and if none grounds, the answer becomes an honest NOT_FOUND. Attacks the
    # user_indomain failure — improvising on in-domain questions whose answer is not actually in the
    # retrieved (but plausible) pages. Default off; the 257 user_indomain TCs are the A/B bed.
    answer_require_citation: bool = Field(default=False, alias="LIBKB_ANSWER_REQUIRE_CITATION")

    # Coverage-aware SELECTION (D-051): tell triage a multi-part question needs a page per part.
    # MEASURED and REFUTED (2 seeds: ANSWER down, temporal not lifted). The ceiling is not triage's
    # smartness but the BASKET SIZE: AllGold@10 is 75% for multi-source and comparison already sits
    # there. Kept default-OFF (mechanism preserved, like confidence gate D-046) for a later revival.
    triage_coverage: bool = Field(default=False, alias="LIBKB_TRIAGE_COVERAGE")

    # CROSS-DOCUMENT SYNTHESIS (the synthesizer route, D-061). Aggregative questions ("trends across
    # X", "compare all the books on Y", "summarise the whole D domain") need EACH relevant page, not
    # the cascade's best-ten basket — MultiHop measured that the cascade cannot reach past its
    # basket. So this path scans WIDE and map-reduces. The cost is EARNED (it runs only when the
    # router sends an aggregative question here) and BOUNDED by these knobs: the map reads on the
    # LITE tier, TRUNCATED, and in PARALLEL, so a synthesis is a handful of cheap calls and the
    # reducer's bill is independent of the scan width (it sees findings, never full pages).
    #   coverage_n — how many pages the scan ranks (the sieve's width; free, no LLM).
    #   map_n      — how many of those get a MAP call (the real cost cap).
    #   map_chars  — truncate each page body for its map call, so one giant page can't blow the map.
    #   concurrency— parallel map workers (thread pool; the ceiling is the provider's rate limit).
    synth_coverage_n: int = Field(default=40, alias="LIBKB_SYNTH_COVERAGE_N")
    synth_map_n: int = Field(default=12, alias="LIBKB_SYNTH_MAP_N")
    synth_map_chars: int = Field(default=2000, alias="LIBKB_SYNTH_MAP_CHARS")
    synth_concurrency: int = Field(default=6, alias="LIBKB_SYNTH_CONCURRENCY")

    # QUERY DECOMPOSITION (the decompose route). A COMPOUND question ("compare the policy before AND
    # after the change, and which applies to international orders") bundles ≥2 distinct needs; a
    # single BLURRED query vector ranks none of the parts' pages reliably into a small basket — the
    # measured cause of the comparison/temporal gap (SCORECARD §2.3/§3: the sieve has ALL evidence
    # at k=20 for 93.5%, but only 29.6% at k=3). So a lite call splits the question into standalone
    # sub-questions, each retrieved SHARPLY in parallel, and their union combined in ONE answer
    # call — the Step-Functions "decompose → parallel retrieve → combine → generate" pattern, home-
    # grown. Cheaper than synthesize (no per-page LLM map). Bounded by these knobs; the route defers
    # to the cascade whenever the question is not genuinely compound.
    # ⚠️ MEASURED AND REFUTED (SCORECARD §3.2): forced against the cascade on MultiHop it LOST
    # comparison 74.1%→63.0% and temporal 83.3%→66.7%, and not from starvation — fed MORE evidence
    # than the baseline it still lost, give-ups turning into wrong answers. So the route is NOT
    # registered by default: the router can never pick it, and it costs nothing. The engine, prompts
    # and tests stay, and this knob re-registers it so the measurement is reproducible.
    enable_decompose_route: bool = Field(default=False, alias="LIBKB_ENABLE_DECOMPOSE")
    decompose_max_subqs: int = Field(default=4, alias="LIBKB_DECOMPOSE_MAX_SUBQS")
    decompose_per_q: int = Field(default=3, alias="LIBKB_DECOMPOSE_PER_Q")  # pages opened per sub-q
    decompose_max_page_tokens: int = Field(default=3000, alias="LIBKB_DECOMPOSE_MAX_PAGE_TOKENS")
    decompose_concurrency: int = Field(default=4, alias="LIBKB_DECOMPOSE_CONCURRENCY")

    routing_mode: Literal["book", "shelf"] = Field(default="shelf", alias="LIBKB_ROUTING_MODE")

    # A one_line is a SPINE LABEL, not an abstract. The folder import was copying whole frontmatter
    # `description:` fields into it — MEASURED on the live library: median 1013 chars, max 1436.
    # That was ~half of every query's input tokens, and it made every option in a menu sound
    # relevant, which is the documented cause of LLM mis-selection among similar categories
    # (ROUTING_REDESIGN §0a). Enforced at render time — the stored value is never trusted.
    max_one_line_chars: int = Field(default=120, alias="LIBKB_MAX_ONE_LINE_CHARS")

    # Two independent ceilings on a shelf menu; a shelf over EITHER falls back to book-by-book:
    #   entries — the option-count ceiling. An LLM's pick accuracy decays as options grow
    #             (Lu et al., ACL 2024), no matter how short each one is.
    #   tokens  — the cost ceiling. A menu, once emitted, is resent on every later turn, so its
    #             price is paid ~once per remaining hop, not once.
    max_shelf_toc_entries: int = Field(default=60, alias="LIBKB_MAX_SHELF_TOC_ENTRIES")
    max_shelf_menu_tokens: int = Field(default=6000, alias="LIBKB_MAX_SHELF_MENU_TOKENS")
    # Over either ceiling the catalog SHORTLISTS the shelf instead of re-imposing a book gate
    # (§7.5). Earned on measurement: on questions the generator never anticipated, the right page is
    # in the catalog's top-10 90.7% of the time (`libkb probe-recall`) — a bad oracle, a good sieve.
    shelf_shortlist_k: int = Field(default=8, alias="LIBKB_SHELF_SHORTLIST_K")
    # MEASURED and REFUTED (D-032): fusing BM25 into the shortlist makes recall WORSE, on both query
    # distributions we have. Generated questions: LOI page R@10 90.7% → 78.6%. Held-out colloquial
    # paraphrases (the realistic case): R@1 83.3% → 43.3%. Every fusion weight above 0 hurts,
    # monotonically. A reader's paraphrase reuses almost none of the library's exact words, so BM25
    # latches onto common ones and drags noise up. The lexical index is kept — it demonstrably
    # rescues rare terms (GMROI, HNSW, a SKU code) and that mechanism is real — but it stays OFF
    # until real traffic (the trajectory logger) shows queries where those terms actually appear.
    hybrid_shortlist: bool = Field(default=False, alias="LIBKB_HYBRID_SHORTLIST")

    # The demand-side flywheel (§8.4). Ingest-time questions are a guess about what a reader might
    # ask (and MEASURED: they cover an unanticipated intent only 39.3% of the time at top-1). A
    # logged trajectory is a fact about what one DID ask. Only the second kind compounds.
    # Written to the same gitignored db as the catalog — it holds real user questions, so it must
    # never enter the tracked tree.
    log_trajectories: bool = Field(default=True, alias="LIBKB_LOG_TRAJECTORIES")

    # Every LLM turn resends the whole conversation, so a page read on turn 3 of an 8-turn walk is
    # re-billed 5 more times — even after the librarian judged it useless and walked on. MEASURED:
    # navigation is ~2.5k tokens of a ~50k query; the other ~46k is page text, re-sent. The
    # librarian never puts a book back (ROUTING_REDESIGN §6).
    # Safe by construction: `compose_answer` rebuilds its evidence from the PageContent objects in
    # NavState.pages, which live entirely OUTSIDE the LLM context — so compressing the conversation
    # cannot cost the ANSWER anything. What it CAN cost is the navigator's own "have I got enough?"
    # judgement, which is why the most recent page stays in full.
    # …EXCEPT it does not pay for itself, and the eval says so (D-033). Shipped ON, it made queries
    # **17% MORE expensive** (49,120 → 57,667 tokens) at identical answer_acc. The compression works
    # exactly as designed — the conversation plateaus instead of growing — but the librarian, robbed
    # of the full text, COMPENSATES BY READING MORE PAGES (6 vs 5, hitting the page budget) and by
    # taking more turns (13 vs 11). The saving is eaten by the behaviour it induces. §6 named this
    # risk itself: "what it could cost is the navigator's own 'have I got enough?' judgement".
    # So: OFF by default — the measured-safe state. `read_page` now hands a re-read back for free
    # (tools.py), which attacks that exact mechanism, but until an eval SHOWS the digest paying, it
    # stays off. Turns to keep a page in full before digesting it; -1 disables.
    page_digest_after_turns: int = Field(default=-1, alias="LIBKB_PAGE_DIGEST_AFTER_TURNS")

    max_hops: int = Field(default=12, alias="LIBKB_MAX_HOPS")
    max_pages_per_nav: int = Field(default=6, alias="LIBKB_MAX_PAGES_PER_NAV")
    max_ask_librarian: int = Field(default=2, alias="LIBKB_MAX_ASK_LIBRARIAN")
    # Bates (1989): a real search is berrypicking — the query is rewritten at every stop with the
    # vocabulary just learned. Budgeted in code (D-008), and it costs no hop: rewording is not
    # travel. Bounded because a librarian who keeps restating the question is lost, not learning.
    max_reframes: int = Field(default=2, alias="LIBKB_MAX_REFRAMES")
    ingest_confidence_gate: float = Field(default=0.7, alias="LIBKB_INGEST_CONFIDENCE_GATE")

    # LEAF GRANULARITY — the one knob that is genuinely a chunking decision, and the one we had
    # never measured. The old splitter cut a document at ONE heading level and never recursed, so a
    # `3 Methodology` page of 9,992 chars kept its 12 sub-headings unused. These are the budgets the
    # recursive rule spends (ingest/split.py); `libkb probe-granularity` sweeps them against LOI
    # recall so the answer is measured per corpus, not guessed per file format.
    # Defaults are deliberately CONSERVATIVE: the live library's median page is ~1,644 tokens, so a
    # 2,000-token ceiling leaves normal pages alone and only cuts the pathological ones.
    split_max_page_tokens: int = Field(default=2000, alias="LIBKB_SPLIT_MAX_PAGE_TOKENS")
    # The floor absorbs a STRAY HEADING (a title with nothing under it), not a thin section. Set it
    # high and the merge quietly destroys the author's structure — at 300 it collapsed a
    # five-section document into ONE page, and at 120 it still did. A floor is a broom, not a
    # policy: 40 is the historical value, it changes nothing, and `probe-granularity` gets to argue
    # for raising it with numbers rather than us guessing.
    split_min_page_chars: int = Field(default=40, alias="LIBKB_SPLIT_MIN_PAGE_CHARS")

    # WHAT the sieve indexes per leaf (D-039). This was the oldest unexamined assumption in the
    # project — that a handful of GENERATED questions is the right entry point — and every external
    # number we have now refutes it:
    #   bench-multihop (2,255 external queries): text AllGold@20 **93.5%** vs questions 69.5%,
    #     and text costs **0 generation tokens** where the flywheel cost ~3.1M to LOSE.
    #   FiQA (648 human questions, pytrec_eval-verified): nDCG@10 0.621 on pure text.
    #   the economics: a 22,633-article legal code is ~34M generated tokens through the flywheel and
    #     ZERO through a text index — the flywheel simply cannot survive a real corpus.
    #
    #   "text"      the page body, embedded directly (RETRIEVAL_DOCUMENT — the task type gemini's
    #               embedder is actually built for). No LLM call. **The default.**
    #   "questions" the generated flywheel (+ entry terms), one lite call per page. NOT retired: on
    #               our OWN colloquial-VI held-out set it still wins R@1 83.3% vs 60.0% (the
    #               vocabulary bridge, SCORECARD §5.1) — an UNSETTLED asymmetry, not a settled loss.
    #   "both"      question rows AND a text row. MEASURED WORSE than text alone so far (RRF fusion
    #               dragged text down; max-pool at search let question cosines win by construction —
    #               metric bug 6.6). Kept for experiments, like hybrid_shortlist; not recommended.
    #
    # Switching from a warm "questions" catalog to "text" (or back) means `reindex --fresh`: the
    # rows are a different representation, not a superset. A text index also leaves probe-recall /
    # all_questions() (which use catalog rows AS the LOI query set) without questions to probe — use
    # `probe-index`, which builds all four indexes itself, to compare representations.
    index_kind: Literal["questions", "text", "both"] = Field(
        default="text", alias="LIBKB_INDEX_KIND"
    )

    # CONCURRENCY (backlog #1). Ingest and eval are network-bound — nearly all wall-clock is spent
    # waiting on an embed or a generate call, and the GIL is released during that wait, so a thread
    # pool is the right tool (no processes, no serialization). MEASURED pain: 2,079 pages ingested
    # in ~40 min sequentially, and a 451-query eval takes ~3 HOURS one at a time — a 10k-page corpus
    # would be ~5 hours to index. These bound how many cases/pages are in flight at once. Kept
    # modest: the ceiling is the provider's rate limit, not the CPU, and an over-eager pool just
    # trades a slow run for one that 429s. 1 = fully sequential (the old behaviour, safe fallback).
    eval_concurrency: int = Field(default=8, alias="LIBKB_EVAL_CONCURRENCY")
    ingest_concurrency: int = Field(default=8, alias="LIBKB_INGEST_CONCURRENCY")

    questions_per_page: int = Field(default=4, alias="LIBKB_QUESTIONS_PER_PAGE")
    question_langs: tuple[str, ...] = ("vi", "en")
    branching_split_threshold: int = Field(default=50, alias="LIBKB_BRANCHING_SPLIT_THRESHOLD")

    # Card catalog (P2c). MEASURED (D-028): absolute cosine is NOT a confidence signal here —
    # gemini embeddings crowd every top-1 score into 0.87–0.90, so the old 0.82 gate fired on
    # ~100% of queries at only 40–71% precision, i.e. WORSE than not using the catalog at all.
    # The real gate is the MARGIN between the best page and the runner-up page.
    catalog_top_k: int = Field(default=5, alias="LIBKB_CATALOG_TOP_K")
    catalog_shortcut_threshold: float = Field(
        default=0.80, alias="LIBKB_CATALOG_SHORTCUT_THRESHOLD"
    )  # near-inert sanity floor
    catalog_margin: float = Field(default=0.05, alias="LIBKB_CATALOG_MARGIN")

    @model_validator(mode="after")
    def _window_from_depth(self) -> "Settings":
        """Fill fetch/triage width from a FIXED depth tier unless set explicitly. 'auto' cannot be
        filled here — it depends on corpus size, which only the catalog knows — so it is left at 0
        and resolved per query by `resolve_cascade`. Equal by design: the whole window is triaged in
        one call, so the round-based widen loop is redundant at width."""
        if self.cascade_depth != "auto":
            width = _CASCADE_WINDOW[self.cascade_depth]
            if self.cascade_fetch_n <= 0:
                self.cascade_fetch_n = width
            if self.cascade_k <= 0:
                self.cascade_k = width
        return self

    def resolve_cascade(self, n_pages: int) -> tuple[int, int, int]:
        """Resolve (fetch_n, k, basket) for one query, turning any 'auto' dial into a concrete size
        from the corpus page count (D-058). Explicit numeric overrides always win; then the fixed
        tier; then the corpus-size rule. Small corpus ⇒ narrow window + small basket (also the fix
        for the token p90 a big basket blew through on a small library)."""
        if self.cascade_fetch_n > 0:
            fetch = self.cascade_fetch_n
        elif self.cascade_depth == "auto":
            small = n_pages < _AUTO_SMALL_PAGES
            fetch = 20 if small else 50 if n_pages < _AUTO_LARGE_PAGES else 100
        else:
            fetch = _CASCADE_WINDOW[self.cascade_depth]
        k = self.cascade_k if self.cascade_k > 0 else fetch

        if self.cascade_max_pages > 0:
            basket = self.cascade_max_pages
        elif self.cascade_basket == "auto":
            basket = 10 if n_pages < _AUTO_SMALL_PAGES else 20
        else:
            basket = int(self.cascade_basket)
        return fetch, k, basket


@lru_cache
def get_settings() -> Settings:
    return Settings()
