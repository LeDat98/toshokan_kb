"""LibraryKB CLI: init, seed, ask (P1), ingest (P2), eval (P3), rebuild-views (P1)."""

from __future__ import annotations

import argparse
import shutil
import sys

from libkb import seed as seed_module
from libkb.config import get_settings
from libkb.library.models import ROOT_ID, slugify
from libkb.library.store import LibraryStore


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to a legacy codepage (e.g. cp932) that cannot
    # print "▸"/"·" used in citations and menus
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        prog="libkb", description="LibraryKB — a knowledge library the AI walks like a human"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty library skeleton")

    seed_parser = sub.add_parser("seed", help="Build the demo mini-library (no LLM calls)")
    seed_parser.add_argument("--force", action="store_true", help="Wipe the existing library first")

    ask_parser = sub.add_parser("ask", help="Ask the library [P1]")
    ask_parser.add_argument("query")
    ask_parser.add_argument("--trace", action="store_true", help="Print the librarian's walk")

    import_parser = sub.add_parser("import", help="Import a structured folder [P2a]")
    import_parser.add_argument("folder")
    import_parser.add_argument("--domain", required=True, help="Target domain, e.g. Retail")
    import_parser.add_argument(
        "--shelves",
        default="single",
        choices=["single", "priority", "auto"],
        help="How to fill the shelf level (auto = LLM groups by theme)",
    )
    import_parser.add_argument(
        "--shelf-name", default="General", help="Name for the 'single' shelf"
    )
    import_parser.add_argument("--replace", action="store_true", help="Overwrite existing pages")
    import_parser.add_argument(
        "--index", action="store_true", help="Also build catalog entries (spends tokens) [P2c]"
    )

    ingest_parser = sub.add_parser("ingest", help="Ingest a document (pdf/md/html/url) [P2b]")
    ingest_parser.add_argument("source", help="A file path or a URL")
    ingest_parser.add_argument("--replace", action="store_true", help="Overwrite existing pages")
    ingest_parser.add_argument(
        "--gate", type=float, default=None, help="Confidence gate override (default from .env)"
    )
    ingest_parser.add_argument(
        "--no-index", action="store_true", help="Skip building catalog entries for new pages"
    )

    reindex_parser = sub.add_parser(
        "reindex", help="(Re)build the card catalog from the library — costs tokens [P2c]"
    )
    reindex_parser.add_argument("--domain", default=None, help="Limit to one domain title")
    reindex_parser.add_argument("--fresh", action="store_true", help="Clear the catalog first")
    reindex_parser.add_argument(
        "--index-kind",
        choices=("questions", "text", "both"),
        default=None,
        help="What the sieve holds (default: config index_kind='text'). "
        "text = 0 generation tokens (D-039). Changing kind needs --fresh.",
    )

    eval_parser = sub.add_parser("eval", help="Run the eval — costs tokens [P3]")
    eval_parser.add_argument("--limit", type=int, default=20, help="Number of cases to sample")
    eval_parser.add_argument(
        "--mode",
        default="walk",
        choices=["walk", "assisted", "shortcut", "cascade"],
        help="walk = tree-walk, no catalog · cascade = propose→triage→answer (needs "
        "LIBKB_RETRIEVAL_MODE=cascade) · assisted = walk + ask_librarian · shortcut = full system",
    )
    eval_parser.add_argument("--domain", default=None, help="Limit cases to one domain title")
    eval_parser.add_argument("--seed", type=int, default=13, help="Sampling seed (reproducible)")
    eval_parser.add_argument(
        "--cases",
        default=None,
        help="Run a saved case file (e.g. a held-out set from `make-holdout`) instead of sampling",
    )
    eval_parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip the answer judge — leaves answer_acc at 0 and only routing is reported",
    )
    eval_parser.add_argument(
        "--save",
        default=None,
        help="Write every answer to a JSON file so it can be RE-JUDGED for free later. "
        "Do this: the answers are the expensive artifact; grading them is not.",
    )

    holdout_parser = sub.add_parser(
        "make-holdout",
        help="Build a held-out paraphrase eval set — cheap, runs on the lite model [P3]",
    )
    holdout_parser.add_argument("--limit", type=int, default=30, help="Number of cases")
    holdout_parser.add_argument("--domain", default=None, help="Limit to one domain title")
    holdout_parser.add_argument("--seed", type=int, default=7, help="Sampling seed")
    holdout_parser.add_argument(
        "--out", default="evals/holdout.json", help="Where to write the case file"
    )

    rejudge_parser = sub.add_parser(
        "rejudge",
        help="Re-grade saved eval answers with the current rubric — cheap, no walks [P3]",
    )
    rejudge_parser.add_argument("results", help="A JSON file written by `libkb eval --save`")

    sub.add_parser(
        "probe-catalog",
        help="Held-out probe of the catalog gate — FREE, makes no LLM calls [P3]",
    )
    sub.add_parser(
        "probe-separability",
        help="Are sibling books separable? Is the book hop worth it? — FREE, no LLM calls [P3]",
    )
    sub.add_parser(
        "probe-recall",
        help="Is the catalog a good SIEVE (recall@k)? mean vs max vs hybrid — FREE, no LLM [P3]",
    )
    misshelved_parser = sub.add_parser(
        "probe-misshelved",
        help="Which pages fit another book better than their own? — FREE, no LLM calls [P3]",
    )
    misshelved_parser.add_argument(
        "--min-delta", type=float, default=0.0, help="Only report pulls at least this strong"
    )

    bench_parser = sub.add_parser(
        "bench",
        help="Score the sieve on a BEIR dataset with HUMAN relevance labels — embeddings only, "
        "ZERO generation calls. Prints the bill and stops unless --yes [P3]",
    )
    bench_parser.add_argument("dataset", help="A BEIR folder, e.g. benchmarks/fiqa")
    bench_parser.add_argument("--split", default="test")
    bench_parser.add_argument(
        "--yes", action="store_true", help="Spend the embedding tokens (vectors are cached after)"
    )

    mha_parser = sub.add_parser(
        "eval-multihop",
        help="Does the cascade ANSWER a multi-hop question, and does it stay honest on the 301 "
        "unanswerable ones? COSTS TOKENS [P3]",
    )
    mha_parser.add_argument("--root", default="benchmarks/multihop")
    mha_parser.add_argument("--limit", type=int, default=200)
    mha_parser.add_argument("--seed", type=int, default=11)
    mha_parser.add_argument("--save", default=None, help="Persist answers so re-judging is free")
    mha_parser.add_argument(
        "--null-only",
        action="store_true",
        help="Run ONLY the 301 unanswerable questions — the full test of the honest-NOT_FOUND rule",
    )
    mha_parser.add_argument("--yes", action="store_true")

    mh_parser = sub.add_parser(
        "bench-multihop",
        help="MultiHop-RAG: 2,255 ground-truth queries, evidence spanning 2-3 articles. "
        "Settles question-index vs text-index at scale. Embeddings only [P3]",
    )
    mh_parser.add_argument("--root", default="benchmarks/multihop")
    mh_parser.add_argument("--limit", type=int, default=None, help="Only the first N queries")

    index_parser = sub.add_parser(
        "probe-index",
        help="Index the page's QUESTIONS or its TEXT? — embeddings only, no generation [P3]",
    )
    index_parser.add_argument(
        "--holdout",
        default="evals/holdout.json",
        help="Colloquial paraphrases with known targets — the honest regime",
    )

    gran_parser = sub.add_parser(
        "probe-granularity",
        help="What leaf size does THIS corpus want? recall vs read-cost vs near-dup — "
        "COSTS TOKENS (lite tier) [P3]",
    )
    gran_parser.add_argument("folder", help="A source folder of .md files (not the library)")
    gran_parser.add_argument("--limit", type=int, default=None, help="Only the first N files")
    gran_parser.add_argument(
        "--yes", action="store_true", help="Skip the cost estimate and spend the tokens"
    )

    cross_parser = sub.add_parser(
        "build-crosslinks",
        help="Write see_also cross-refs from the misshelved probe — FREE, no LLM calls [P3]",
    )
    cross_parser.add_argument("--min-delta", type=float, default=0.03)
    cross_parser.add_argument("--max-per-book", type=int, default=3)
    cross_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be written, change nothing"
    )

    harvest_parser = sub.add_parser(
        "harvest",
        help="Index REAL user questions from the trajectory log — 1 embed each [P3]",
    )
    harvest_parser.add_argument("--limit", type=int, default=100)
    harvest_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be indexed, change nothing"
    )

    rebuild_parser = sub.add_parser(
        "rebuild-views", help="Regenerate descriptions bottom-up, incl. books [P1]"
    )
    rebuild_parser.add_argument("--domain", default=None, help="Limit to one domain subtree")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "init":
        store = LibraryStore(settings.library_dir)
        store.init_library()
        print(f"Library initialized at {settings.library_dir.resolve()}")
        return 0

    if args.command == "seed":
        library_dir = settings.library_dir
        if (library_dir / "_meta.json").exists():
            if not args.force:
                print(f"Library already exists at {library_dir.resolve()} — use --force.")
                return 1
            shutil.rmtree(library_dir)
        store = LibraryStore(library_dir)
        store.init_library()
        stats = seed_module.apply(store)
        print(
            f"Seeded demo library: {stats.n_shelves} shelves · "
            f"{stats.n_books} books · {stats.n_pages} pages"
        )
        for card in store.children(ROOT_ID):
            line = f"  {card.title:<14} {card.stats_line}"
            print(line.rstrip())
            for child in store.children(card.id):
                print(f"    {child.title:<28} {child.stats_line}".rstrip())
        return 0

    if args.command == "import":
        return _cmd_import(args, settings)

    if args.command == "ingest":
        return _cmd_ingest(args, settings)

    if args.command == "reindex":
        return _cmd_reindex(args, settings)

    if args.command == "eval":
        return _cmd_eval(args, settings)

    if args.command == "make-holdout":
        return _cmd_make_holdout(args, settings)

    if args.command == "rejudge":
        return _cmd_rejudge(args, settings)

    if args.command == "probe-catalog":
        return _cmd_probe_catalog(args, settings)

    if args.command == "probe-separability":
        return _cmd_probe_separability(args, settings)

    if args.command == "probe-recall":
        return _cmd_probe_recall(args, settings)

    if args.command == "bench":
        return _cmd_bench(args, settings)

    if args.command == "eval-multihop":
        return _cmd_eval_multihop(args, settings)

    if args.command == "bench-multihop":
        return _cmd_bench_multihop(args, settings)

    if args.command == "probe-index":
        return _cmd_probe_index(args, settings)

    if args.command == "probe-granularity":
        return _cmd_probe_granularity(args, settings)

    if args.command == "probe-misshelved":
        return _cmd_probe_misshelved(args, settings)

    if args.command == "build-crosslinks":
        return _cmd_build_crosslinks(args, settings)

    if args.command == "harvest":
        return _cmd_harvest(args, settings)

    if args.command == "ask":
        return _cmd_ask(args, settings)

    if args.command == "rebuild-views":
        from libkb.library.views import rebuild_all

        store = LibraryStore(settings.library_dir)
        root = ROOT_ID
        scope = "the whole tree"
        if args.domain:
            match = next(
                (
                    c
                    for c in store.children(ROOT_ID)
                    if c.kind == "domain" and slugify(c.title) == slugify(args.domain)
                ),
                None,
            )
            if match is None:
                print(f"No domain '{args.domain}'.")
                return 1
            root, scope = match.id, match.title
        report = rebuild_all(store, root)
        print(f"Rebuilt {report.rebuilt} descriptions across {scope}.")
        return 0

    print(f"'{args.command}' arrives in a later phase — see .agent/ROADMAP.md")
    return 1


_TRACE_GLYPH = {
    "enter": "→",
    "open": "↳",
    "shelf": "▤",
    "read": "▸",
    "back": "↩",
    "found": "✓",
    "not_found": "✗",
    "budget": "⏱",
    "ask": "?",
    "lookup": "⚡",
}


def _cmd_import(args, settings) -> int:
    from pathlib import Path

    from libkb.ingest.importer import import_folder

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Not a folder: {folder.resolve()}")
        return 1
    library_dir = settings.library_dir
    store = LibraryStore(library_dir)
    if not (library_dir / "_meta.json").exists():
        store.init_library()

    llm = None
    if args.shelves == "auto" or args.index:
        from libkb.llm.client import get_llm

        llm = get_llm()

    catalog = None
    if args.index:
        from libkb.catalog.store import Catalog

        catalog = Catalog(settings.db_path)

    report = import_folder(
        folder,
        args.domain,
        store,
        strategy=args.shelves,
        shelf_name=args.shelf_name,
        replace=args.replace,
        llm=llm,
        catalog=catalog,
        progress=print,
    )
    catalog_note = f" · catalog now {catalog.count()} questions" if catalog else ""
    if catalog:
        catalog.close()
    print(
        f"\nImported into '{report.domain}': {report.shelves} shelves · "
        f"{report.books} books · {report.pages} pages"
        + (f" ({report.skipped_pages} pages skipped)" if report.skipped_pages else "")
        + catalog_note
    )
    print(f"  provided by source: {', '.join(report.provided)}")
    print(f"  filled by import:   {', '.join(report.missing) or '(nothing missing)'}")
    if report.index_failures:
        # A page in the library but not in the catalog is invisible to the sieve. Never let that
        # hide inside a success line again (D-040).
        n = len(report.index_failures)
        print(f"\n  !! {n} of {report.pages} pages FAILED to index — the sieve cannot see them.")
        for path in report.index_failures[:5]:
            print(f"     - {path}")
        if n > 5:
            print(f"     … and {n - 5} more")
        print("     Re-run `libkb reindex` to retry them.")
    tip = "Tip: run `libkb rebuild-views` to regenerate shelf/domain descriptions with the model."
    if not args.index:
        tip += "\nTip: run `libkb reindex` to build the card catalog (enables fast lookup)."
    print("\n" + tip)
    return 0


def _cmd_ingest(args, settings) -> int:
    from libkb.ingest.pipeline import IngestEvent, ingest_document

    library_dir = settings.library_dir
    store = LibraryStore(library_dir)
    if not (library_dir / "_meta.json").exists():
        store.init_library()

    print(f"Ingesting: {args.source}\n")

    def on_event(ev: IngestEvent) -> None:
        mark = {"running": "…", "done": "✓", "gated": "⚑", "failed": "✗"}.get(ev.status, "·")
        detail = f"  {ev.detail}" if ev.detail else ""
        print(f"  {mark} {ev.stage}{detail}")

    catalog = None
    if not args.no_index:
        from libkb.catalog.store import Catalog

        catalog = Catalog(settings.db_path)

    outcome = ingest_document(
        args.source, store, gate=args.gate, replace=args.replace, catalog=catalog, event_cb=on_event
    )
    if catalog:
        catalog.close()
    place = outcome.placement
    print("\n" + "─" * 60)
    if outcome.gated:
        print(f"Low confidence ({place.confidence:.2f}) → parked in Uncatalogued for review.")
        print(f"  Proposed: {place.path}")
        print(f"  Why: {place.rationale}")
        print("  Review it in the Ingest queue, or re-run after adjusting.")
    else:
        print(f"Filed under: {outcome.book_path}  ({outcome.n_pages} pages)")
        print(f"  Confidence {place.confidence:.2f} — {place.rationale}")
    return 0


def _cmd_reindex(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.ingest.questions import index_page
    from libkb.llm.client import get_llm

    library_dir = settings.library_dir
    if not (library_dir / "_meta.json").exists():
        print(f"No library at {library_dir.resolve()} — run `libkb seed` first.")
        return 1
    store = LibraryStore(library_dir)
    catalog = Catalog(settings.db_path)
    if args.fresh:
        catalog.clear()
    kind = args.index_kind or settings.index_kind
    llm = get_llm()

    page_ids: list[str] = []
    for domain in store.children(ROOT_ID):
        if domain.kind != "domain":  # skip the Uncatalogued review shelf
            continue
        if args.domain and slugify(domain.title) != slugify(args.domain):
            continue
        page_ids += [m.id for m in store.iter_subtree(domain.id) if m.kind == "page"]

    gen = " (no generation — embeddings only)" if kind == "text" else ""
    print(f"Indexing {len(page_ids)} pages as '{kind}'{gen}…\n")
    indexed = skipped = 0
    for i, page_id in enumerate(page_ids, 1):
        pc = store.page(page_id)
        if not pc.indexable:  # back matter: on the shelf, never in the sieve
            catalog.remove_page(page_id)
            skipped += 1
            print(f"  [{i}/{len(page_ids)}] – skip (back matter)  {store.path_str(page_id)}")
            continue
        book_title = store.get(pc.book_id).title if pc.book_id else ""
        try:
            card = index_page(
                catalog,
                page_id=page_id,
                book_id=pc.book_id,
                path=store.path_str(page_id),
                title=pc.title,
                markdown=pc.markdown,
                book_title=book_title,
                llm=llm,
                index_kind=kind,
            )
            indexed += 1
            # the contract (ingest/questions.py): a page with no spine label gets the one this call
            # already generated — a reindex is where old pages catch up with it. A text index
            # generates none, so this fills nothing and the splitter's one_line stands.
            entry = store.toc_entry(page_id)
            if not entry.one_line and card.one_line:
                store.set_toc_entry(page_id, one_line=card.one_line, keywords=card.keywords or None)
            print(f"  [{i}/{len(page_ids)}] +{card.indexed_rows} rows  {store.path_str(page_id)}")
        except Exception as exc:  # keep going; one bad page shouldn't abort a reindex
            print(f"  [{i}/{len(page_ids)}] ✗ {store.path_str(page_id)} — {exc}")
    total = catalog.count()
    catalog.close()
    tail = f" · {skipped} skipped as back matter" if skipped else ""
    print(f"\nCatalog now holds {total} rows across {indexed} pages{tail}.")
    return 0


def _cmd_eval(args, settings) -> int:
    from pathlib import Path

    from libkb.catalog.store import Catalog
    from libkb.evals.dataset import build_cases
    from libkb.evals.gates import EvalGates, check_gates
    from libkb.evals.holdout import load_cases
    from libkb.evals.runner import run_eval

    library_dir = settings.library_dir
    if not (library_dir / "_meta.json").exists():
        print(f"No library at {library_dir.resolve()} — run `libkb seed` first.")
        return 1
    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first (the eval set comes from it).")
        return 1

    store = LibraryStore(library_dir)
    catalog = Catalog(settings.db_path)
    if args.cases:
        path = Path(args.cases)
        if not path.exists():
            catalog.close()
            print(f"No case file at {path} — build one with `libkb make-holdout`.")
            return 1
        cases = load_cases(path)
        source = f"{path} (held out)"
    else:
        cases = build_cases(catalog, limit=args.limit, domain=args.domain, seed=args.seed)
        source = f"sampled from the catalog, seed={args.seed} (LEAKED — see `make-holdout`)"
    if not cases:
        catalog.close()
        print("No eval cases (empty catalog or the domain filter matched nothing).")
        return 1

    print(f"Eval · mode={args.mode} · routing={settings.routing_mode} · {len(cases)} cases")
    print(f"Cases: {source}\n")

    def on_case(i, total, res) -> None:
        verdict = "✓" if res.answer_ok else ("✗" if not args.no_judge else "·")
        mark = {"page": "◎", "book": "○", "shelf": "·", "domain": "·", "miss": "✗"}.get(
            res.level, "·"
        )
        head = f"  [{i}/{total}] {verdict} answer · {mark} {res.level:<6}"
        print(f"{head} ({res.hops}h/{res.backtracks}b, {res.input_tokens:,}tok)")
        print(f"            q: {res.case.question}")
        print(f"            → {res.case.target_path}")
        if res.judge_reason and not res.answer_ok:
            print(f"            ! {res.judge_reason}")

    report = run_eval(
        store,
        cases,
        mode=args.mode,
        catalog=catalog,
        judge=not args.no_judge,
        progress=on_case,
    )
    catalog.close()

    if args.save:
        from libkb.evals.holdout import save_answers

        save_answers(Path(args.save), args.mode, report.results)
        print(f"\nAnswers written to {args.save} — re-judge them for free with `libkb rejudge`.")

    print("\n" + "─" * 60)
    print(f"n={report.n} · mode={report.mode} · routing_mode={settings.routing_mode}")
    if report.judged:
        print(f"\n  ANSWER {report.answer_acc:6.1%}   ← the metric that decides (§3.0)")
    else:
        print("\n  ANSWER    n/a   (--no-judge)")
    print("\n  routing diagnostics — WHERE it went, not whether the reader was served:")
    print(f"    page   {report.page_acc:6.1%}   exact target page reached")
    print(f"    book   {report.book_acc:6.1%}   right book reached")
    print(f"    shelf  {report.shelf_acc:6.1%}")
    print(f"    domain {report.domain_acc:6.1%}")
    print(
        f"    found  {report.found_rate:6.1%} · "
        f"avg {report.avg_hops:.1f} hops / {report.avg_backtracks:.1f} backtracks"
    )
    print(
        f"\n  cost   {report.mean_input_tokens:,.0f} input tokens/query (mean) · "
        f"{report.mean_output_tokens:,.0f} output"
    )

    gates = EvalGates()
    passed, failures = check_gates(report, gates)
    if not gates.armed:
        print("\nGate: not armed — no trustworthy baseline yet (evals/gates.py explains why).")
        return 0
    print("\nGate: PASS" if passed else "\nGate: FAIL — " + "; ".join(failures))
    return 0 if passed else 2


def _cmd_make_holdout(args, settings) -> int:
    from pathlib import Path

    from libkb.catalog.store import Catalog
    from libkb.evals.dataset import build_cases
    from libkb.evals.holdout import paraphrase_cases, save_cases

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    catalog = Catalog(settings.db_path)
    cases = build_cases(catalog, limit=args.limit, domain=args.domain, seed=args.seed)
    catalog.close()
    if not cases:
        print("No cases to paraphrase.")
        return 1

    print(f"Paraphrasing {len(cases)} questions on {settings.model_lite} …\n")

    def on_case(i, total, before, after) -> None:
        print(f"  [{i}/{total}] {before.question}")
        print(f"          → {after.question}\n")

    fresh = paraphrase_cases(cases, progress=on_case)
    out = Path(args.out)
    save_cases(out, fresh)
    print(f"Wrote {len(fresh)} held-out cases to {out}.")
    print(f"Run both A/B arms against it: libkb eval --cases {out} --mode walk")
    return 0


def _cmd_probe_catalog(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.evals.catalog_probe import probe

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    catalog = Catalog(settings.db_path)
    results = probe(catalog)
    n_pages = len(catalog.page_ids())
    catalog.close()
    if not results:
        print("Catalog is too small to probe.")
        return 1

    print(
        f"Catalog probe — no LLM calls, free to re-run. {results[0].n} questions / {n_pages} pages"
    )
    print(
        f"Live gate: margin >= {settings.catalog_margin} "
        f"(cosine floor {settings.catalog_shortcut_threshold})\n"
    )
    for r in results:
        print(f"=== {r.label} ===")
        print(
            f"  top-1 lands on the right page: {r.top1_page_acc:6.1%}  "
            f"(median cosine {r.median_score:.3f} · median margin {r.median_margin:.4f})"
        )
        print(f"  {'MARGIN':>7} {'fires':>7} {'right|fires':>12} {'est e2e':>9}")
        for g in r.by_margin:
            print(f"  {g.value:7.3f} {g.fires:7.1%} {g.precision:12.1%} {g.est_e2e:9.1%}")
        print(f"  {'cosine':>7} {'fires':>7} {'right|fires':>12} {'est e2e':>9}")
        for g in r.by_threshold:
            print(f"  {g.value:7.2f} {g.fires:7.1%} {g.precision:12.1%} {g.est_e2e:9.1%}")
        print()
    print("An absolute cosine gate fires on ~everything (scores crowd near 0.9) — it is not a")
    print("confidence signal. The margin gate goes quiet on questions it doesn't recognise,")
    print("and the walk handles those. Tune LIBKB_CATALOG_MARGIN from the tables above.")
    return 0


def _cmd_probe_separability(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.evals.separability import probe_separability

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    catalog = Catalog(settings.db_path)
    sep, routes = probe_separability(catalog)
    catalog.close()
    if sep.n_decisions == 0:
        print("Not enough multi-book shelves to probe.")
        return 1

    print("SIBLING-BOOK SEPARABILITY (content-only, leave-one-out — descriptions not involved)")
    print(f"  decisions evaluated : {sep.n_decisions}")
    print(f"  true book wins      : {sep.book_accuracy:.1%}")
    print(f"  median top1-top2 gap: {sep.median_margin:.4f}\n")
    print(f"  {'acc':>7} {'n':>5}  {'books':>5} {'pages':>5}  shelf")
    for r in sep.per_shelf:
        print(f"  {r.accuracy:7.1%} {r.n_questions:5d}  {r.n_books:5d} {r.n_pages:5d}  {r.shelf}")
    if sep.confusions:
        print("\n  top content confusions (true book → book that stole it):")
        for true_b, thief, count in sep.confusions:
            print(f"    {count:3d}x  {true_b[:32]:<32} → {thief}")

    print("\n\nDOES THE BOOK LEVEL HELP OR HURT ROUTING?  (content-only, leave-one-out)")
    print(f"  questions on multi-book shelves : {routes.n}\n")
    print(f"    A) shelf → book → page        : {routes.route_a_acc:7.1%}   (page correct e2e)")
    print(f"         of which, book hop right : {routes.book_hop_acc:7.1%}")
    print(
        f"    B) shelf → page  (union TOC)  : {routes.route_b_acc:7.1%}   <-- book level DELETED\n"
    )
    print(f"    B rescues cases A lost        : {routes.rescues}")
    print(f"    B loses cases A won           : {routes.losses}")
    print(f"    net change from deleting book : {routes.delta:+.1%}\n")
    print(f"    median margin, book choice    : {routes.median_book_margin:.4f}")
    print(f"    median margin, page-on-shelf  : {routes.median_page_margin:.4f}")
    print("\nA level whose siblings cannot be told apart by their own content should not be a")
    print("decision point in the walk. Measure this BEFORE cutting or adding a level.")
    return 0


def _cmd_rejudge(args, settings) -> int:
    """Re-grade answers already produced. The answers cost real money; grading them does not."""
    import json
    from pathlib import Path

    from libkb.evals.judge import judge_answer
    from libkb.exceptions import NodeNotFound

    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    rows = data["results"]
    store = LibraryStore(settings.library_dir)

    print(f"Re-judging {len(rows)} saved answers from mode={data['mode']} with the CURRENT rubric.")
    print("No walks, no retrieval — just the grader.\n")

    was = sum(1 for r in rows if r["answer_ok"])
    now = 0
    flipped: list[tuple[str, str]] = []
    for row in rows:
        # Judge every answer we have. A not-found IS an answer ("the library doesn't hold this") and
        # the grader must be allowed to call it wrong — it is a failure to serve. Filtering on
        # `status` here would be a bug: it records the WALK's outcome (FOUND/NOT_FOUND), not the
        # answerer's.
        if not row["answer"].strip():
            continue
        try:
            reference = store.page(row["target_page_id"]).markdown
        except NodeNotFound:
            continue
        verdict = judge_answer(row["question"], row["answer"], reference)
        now += verdict.correct
        if verdict.correct != row["answer_ok"]:
            flipped.append((row["question"], verdict.reason))

    n = len(rows)
    print(f"  answer_acc, as recorded : {was / n:6.1%}")
    print(f"  answer_acc, re-judged   : {now / n:6.1%}   ({now - was:+d} cases)\n")
    for question, reason in flipped:
        print(f'  ↻ "{question[:66]}"')
        print(f"     {reason[:88]}")
    return 0


_BEIR_BASELINES = {  # published BM25 nDCG@10 (BEIR paper) — a bar, not just a number
    "fiqa": 0.236,
    "scifact": 0.665,
    "nfcorpus": 0.325,
    "trec-covid": 0.656,
}


def _cmd_bench(args, settings) -> int:
    from pathlib import Path

    from libkb.evals.beir import KS, load, run

    root = Path(args.dataset)
    if not (root / "corpus.jsonl").exists():
        print(f"No BEIR dataset at {root} (expected corpus.jsonl, queries.jsonl, qrels/).")
        return 1

    data = load(root, args.split)
    cache = root / f"vectors-{settings.embed_model}.npy"
    print(
        f"{data.name}: {len(data.doc_ids):,} documents · {len(data.queries):,} {args.split} "
        f"questions · human relevance labels"
    )
    if cache.exists():
        print(f"Vectors are already cached ({cache.name}) — scoring costs NOTHING.")
    else:
        print(f"\n  embed  ~{data.embed_tokens:,} tokens  ({settings.embed_model})")
        print("  generate      0 tokens  ← the whole point: no question flywheel, no LLM calls")
        print(f"\nCached to {cache.name} afterwards, so every later re-score is free.")
        if not args.yes:
            print("\nNothing spent. Re-run with --yes to measure.")
            return 0

    rows, n = run(data, cache, progress=lambda m: print(f"  {m}"))
    ks = "".join(f"{'@' + str(k):>9}" for k in KS)
    print(f"\n{data.name} · {n} real user questions · human qrels")
    print(f"  {'metric':<9}{ks}")
    for row in rows:
        at = "".join(f"{row.at_k.get(k, 0):>9.3f}" for k in KS)
        print(f"  {row.metric:<9}{at}")

    bm25 = _BEIR_BASELINES.get(data.name)
    if bm25:
        ours = next(r.at_k.get(10, 0.0) for r in rows if r.metric == "nDCG")
        verdict = "ABOVE" if ours > bm25 else "BELOW"
        print(f"\n  BM25 baseline (BEIR paper) nDCG@10 = {bm25:.3f} → we are {verdict} it.")
    print(
        "\nThis is the first number in this project that our own LLM did not author. Everything\n"
        "else (LOI 56.1%, R@10 90.7%, the cascade A/B) was scored on questions we generated FROM\n"
        "the pages we then had to find. Read Recall@10 hardest: the cascade's entire design rests\n"
        "on the answer being INSIDE the shortlist it hands the LLM."
    )
    return 0


def _cmd_eval_multihop(args, settings) -> int:
    import json
    from pathlib import Path

    from libkb.catalog.store import Catalog
    from libkb.evals.multihop_answer import NULL, load_cases, run

    root = Path(args.root)
    store = LibraryStore(settings.library_dir)
    catalog = Catalog(settings.db_path)
    cases = load_cases(
        root / "MultiHopRAG.json", limit=args.limit, seed=args.seed, null_only=args.null_only
    )
    nulls = sum(1 for c in cases if c.kind == NULL)

    # resolve 'auto' against THIS catalog so the header shows what will actually run (D-058)
    fetch_n, k, max_pages = settings.resolve_cascade(len(catalog.page_ids()))
    print(
        f"{len(cases)} cases ({nulls} of them UNANSWERABLE) · basket={max_pages} "
        f"pages · triage sees {k}×{settings.cascade_max_rounds} of "
        f"{fetch_n} candidates ({settings.cascade_depth}/{settings.cascade_basket}) · "
        f"model={settings.model} · {settings.eval_concurrency} in parallel"
    )
    if not args.yes:
        print(f"\n~{len(cases)} cascade runs. Nothing spent. Re-run with --yes.")
        return 0

    report = run(cases, store=store, catalog=catalog, progress=lambda m: print(f"  {m}"))
    catalog.close()

    answerable, null_rows = report.answerable, report.nulls
    acc = sum(o.correct for o in answerable) / max(len(answerable), 1)
    honesty = sum(o.correct for o in null_rows) / max(len(null_rows), 1)
    coward = sum(o.said_not_found for o in answerable) / max(len(answerable), 1)
    tokens = report.input_total  # batch-level: correct whether the run was sequential or concurrent

    if answerable:
        print(f"\n  ANSWER   {acc:>6.1%}   of the {len(answerable)} answerable questions")
    if null_rows:
        refused = sum(o.correct for o in null_rows)
        print(
            f"  HONESTY  {honesty:>6.1%}   {refused}/{len(null_rows)} UNANSWERABLE questions "
            f"correctly refused"
        )
        print(
            f"           the other {len(null_rows) - refused} were IMPROVISED "
            f"— straight P6 violations"
        )
    if answerable:
        print(f"  coward   {coward:>6.1%}   answerable questions it wrongly gave up on")
        print("\n  (refusing everything scores 100% honesty and is useless — read both numbers)")

    if len(report.by_kind) > 1:
        print("\n  by question type:")
    for kind, rows in sorted(report.by_kind.items()) if len(report.by_kind) > 1 else []:
        hits = sum(o.correct for o in rows)
        print(f"    {kind.replace('_query', ''):<12} {hits}/{len(rows)}  {hits / len(rows):>6.1%}")

    print(f"\n  cost  {tokens // max(report.n, 1):,} input tokens/query (mean)")

    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(
            json.dumps(
                {
                    "basket": max_pages,
                    "model": settings.model,
                    "rows": [
                        {
                            "query": o.case.query,
                            "kind": o.case.kind,
                            "gold": o.case.answer,
                            "answer": o.text,
                            "not_found": o.said_not_found,
                            "correct": o.correct,
                            "confidence": o.confidence,
                            "pages": o.pages,
                            "input_tokens": o.input_tokens,
                        }
                        for rows in report.by_kind.values()
                        for o in rows
                    ],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\n  answers saved to {args.save} — re-judging them later costs nothing (D-035)")
    return 0


def _cmd_bench_multihop(args, settings) -> int:
    from pathlib import Path

    from libkb.catalog.store import Catalog
    from libkb.evals.multihop import INDEXES, KS, article_of_page, build, load_queries, score

    root = Path(args.root)
    store = LibraryStore(settings.library_dir)
    catalog = Catalog(settings.db_path)
    if not catalog.count():
        print(f"No catalog at {settings.db_path} — import the corpus with --index first.")
        return 1

    queries = load_queries(root / "MultiHopRAG.json")
    if args.limit:
        queries = queries[: args.limit]
    article_of = article_of_page(store, root / "src")
    print(
        f"{len(catalog.page_ids()):,} pages from {len(set(article_of.values())):,} articles · "
        f"{len(queries):,} answerable queries (the 301 null_query rows have no evidence and belong "
        f"to the cascade eval, not to retrieval)"
    )

    indexes = build(store, catalog, progress=lambda m: print(f"  {m}"))
    rows = score(indexes, queries, article_of, progress=lambda m: print(f"  {m}"))
    catalog.close()

    ks = "".join(f"{'@' + str(k):>8}" for k in KS)
    for metric, label, why in (
        ("hit", "Hit", "≥1 gold article in the top k — the loosest thing anyone reports"),
        ("coverage", "Coverage", "the FRACTION of the gold evidence assembled"),
        ("allgold", "AllGold", "EVERY gold article — what a correct multi-hop answer REQUIRES"),
    ):
        print(f"\n{label}@k — {why}")
        print(f"  {'index':<11}{ks}")
        for name in INDEXES:
            row = next(r for r in rows if r.index == name and r.kind == "all")
            vals = getattr(row, metric)
            print(f"  {name:<11}" + "".join(f"{vals[k]:>8.1%}" for k in KS))

    print("\nAllGold@3 is the one that matters: the cascade opens a basket of 3 pages")
    print("(cascade_max_pages). Evidence it does not deliver cannot be recovered by any prompt.")
    print("\nBy question type (AllGold@3):")
    kinds = sorted({r.kind for r in rows} - {"all"})
    print(f"  {'index':<11}" + "".join(f"{k.replace('_query', ''):>14}" for k in kinds))
    for name in INDEXES:
        cells = []
        for kind in kinds:
            row = next((r for r in rows if r.index == name and r.kind == kind), None)
            cells.append(f"{row.allgold[3]:>14.1%}" if row else f"{'—':>14}")
        print(f"  {name:<11}" + "".join(cells))
    return 0


def _cmd_probe_index(args, settings) -> int:
    import json
    from pathlib import Path

    from libkb.catalog.store import Catalog
    from libkb.evals.indexing import INDEXES, KS, probe_indexes

    store = LibraryStore(settings.library_dir)
    catalog = Catalog(settings.db_path)
    if not catalog.count():
        print("The catalog is empty — run `libkb reindex` first.")
        return 1

    holdout: list[tuple[str, str]] = []
    path = Path(args.holdout)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        holdout = [(c["question"], c["target_page_id"]) for c in data.get("cases", [])]

    rows = probe_indexes(
        store, catalog, holdout=holdout or None, progress=lambda m: print(f"  {m}")
    )
    catalog.close()

    ks = "".join(f"{'R@' + str(k):>9}" for k in KS)
    for regime in ("LOI", "holdout"):
        block = [r for r in rows if r.regime == regime]
        if not block:
            continue
        label = {
            "LOI": "LOI — an intent the generator NEVER anticipated (n=%d)",
            "holdout": "HELD-OUT — colloquial paraphrases, no leak anywhere (n=%d)",
        }[regime] % block[0].n_queries
        print(f"\n{label}")
        print(f"  {'index':<11}{'vectors':>9}{ks}")
        for name in INDEXES:
            r = next(x for x in block if x.index == name)
            at = "".join(f"{r.at_k.get(k, 0):>9.1%}" for k in KS)
            print(f"  {r.index:<11}{r.n_vectors:>9}{at}")
    print(
        "\nquestions = what we ship (1 LLM call per page at ingest)\n"
        "text      = the page body, embedded directly — **ZERO generation calls**\n"
        "sections  = each section embedded; a page scores as its best section\n"
        "both      = questions ∪ text, max-pooled per page\n"
        "\nThis is not only an accuracy question. Question-indexing a 22,633-article legal code\n"
        "costs ~34M generated tokens; text-indexing costs none. If `text` holds, a real corpus\n"
        "becomes reachable. If it does not, the flywheel is the ceiling on how big we can ever get."
    )
    return 0


def _cmd_probe_granularity(args, settings) -> int:
    from libkb.evals.granularity import (
        KS,
        Leaf,
        cut,
        default_strategies,
        probe_granularity,
        read_source,
    )

    files = read_source(args.folder, limit=args.limit)
    if not files:
        print(f"No .md files under {args.folder}")
        return 1
    strategies = default_strategies(settings)

    # The cost is real and it is the user's, so it is stated BEFORE it is spent. Leaves shared
    # between strategies are generated once (evals/granularity.py::_Bank), so the true bill is the
    # number of DISTINCT leaves, not the sum — which is usually far smaller than it looks.
    distinct = {leaf.key for s in strategies for leaf in cut(files, s)}
    distinct |= {Leaf(f.file_id, f.title, f.body).key for f in files}  # the query set
    print(f"{len(files)} files · {len(strategies)} strategies")
    print(
        f"~{len(distinct)} lite-tier calls ({settings.model_lite}) + embeddings, "
        "once — identical leaves are shared between strategies, so this is the real bill."
    )
    if not args.yes:
        print("\nNothing spent. Re-run with --yes to measure.")
        return 0

    rows = probe_granularity(files, strategies, progress=lambda m: print(f"  {m}"))
    ks = "".join(f"{'R@' + str(k):>8}" for k in KS)
    print(f"\n{'strategy':<13}{'leaves':>7}{'med':>6}{'p95':>7}{ks}{'read':>9}{'margin':>9}")
    print("-" * (13 + 7 + 6 + 7 + 8 * len(KS) + 9 + 9))
    for r in rows:
        at = "".join(f"{r.at_k.get(k, 0):>8.1%}" for k in KS)
        print(
            f"{r.strategy:<13}{r.n_leaves:>7}{r.median_tokens:>6}{r.p95_tokens:>7}"
            f"{at}{r.read_tokens:>9,}{r.margin:>9.3f}"
        )
    print(
        "\nread   = tokens the answerer is handed for a basket of 3 — the cost axis.\n"
        "margin = mean (score@1 − score@10): how sharply the sieve separates the winner from the\n"
        "         pack. SMALL = the near-duplicate flood — the ranking is flat and the shortlist\n"
        "         fills with restatements. Measured by margin, not by a cosine threshold, because\n"
        "         this embedder crowds every similarity into 0.87–0.95 (D-028) and a threshold\n"
        "         there calls 95.7% of our WORKING library duplicates.\n"
        "\nRecall is LOO (queries were generated from the text they index), so read the rows\n"
        "against EACH OTHER, not against the 39.3% LOI number. Comparing cuts is the only claim."
    )
    return 0


def _cmd_probe_recall(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.evals.recall import KS, probe_recall

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    catalog = Catalog(settings.db_path)
    rows = probe_recall(catalog)
    catalog.close()
    if not rows:
        print("Catalog is too small to probe.")
        return 1

    print("RECALL@k — the shortlist an LLM would receive. No LLM calls; free to re-run.")
    print("  LOO = a paraphrase of a question we DID anticipate")
    print("  LOI = an intent we NEVER anticipated  ← the honest, hard case\n")
    header = "  ".join(f"R@{k:<4}" for k in KS)
    print(f"  {'level':<6} {'regime':<5} {'pooling':<7} {'cands':>5}  {header}")
    print("  " + "-" * (26 + len(header)))
    for r in rows:
        cells = "  ".join(f"{100 * r.at_k[k]:5.1f}%" for k in KS)
        print(f"  {r.level:<6} {r.regime:<5} {r.pooling:<7} {r.n_targets:5d}  {cells}")

    print(
        "\nEmbedding is a BAD ORACLE and a GOOD SIEVE: top-1 on an unanticipated question is weak,"
    )
    print("but the right page is almost always inside the top-10. Shortlist with it; never gate.")
    print("MAX beats MEAN at every container level — a book is a union of topics, not one topic.")
    print("HYBRID (BM25 fused in) LOSES here (D-032): a reader's paraphrase reuses almost none of")
    print("the library's exact words, so lexical matching drags noise up. Off by default.")
    return 0


def _cmd_probe_misshelved(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.evals.misshelved import probe_misshelved

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    catalog = Catalog(settings.db_path)
    report = probe_misshelved(catalog, min_delta=args.min_delta)
    catalog.close()
    if not report.n_pages:
        print("Catalog is too small to probe.")
        return 1

    cross = [h for h in report.hits if h.cross_shelf]
    print(
        f"SHELF-READING — {len(report.hits)} of {report.n_pages} pages fit another book better "
        f"than their own ({report.rate:.0%})"
    )
    print(f"  of those, {len(cross)} pull ACROSS shelves — the ones the walk genuinely cannot see")
    print(f"  size bias (thief books vs the average book): {report.size_bias:.2f}x  [1.0 = none]\n")

    for h in report.hits[:12]:
        tag = "   CROSS-SHELF" if h.cross_shelf else ""
        print(f'  d+{h.delta:.3f}  "{h.page_title[:56]}"')
        print(f"              filed in : {h.own_book[:26]:<26} [{h.own_shelf}]")
        print(f"              fits best: {h.best_book[:26]:<26} [{h.best_shelf}]{tag}")
    if len(report.hits) > 12:
        print(f"  … and {len(report.hits) - 12} more")

    if report.mutual:
        print("\n  MUTUAL theft — two books stealing from EACH OTHER = one book split in two:")
        for a, b, ab, ba in report.mutual[:5]:
            print(f"    {ab:2d}x {a[:30]:<30} ⇄ {ba:2d}x {b}")

    print("\nThis is NOT a filing-error list. A page that is a KPI *definition* about *inventory*")
    print("belongs to both books; a single-parent tree just forces a choice. The fix is a")
    print("cross-reference, not a move: `libkb build-crosslinks`. Only the MUTUAL pairs above are")
    print("merge candidates, and a human decides those.")
    return 0


def _cmd_build_crosslinks(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.library.crosslinks import build_crosslinks

    if not settings.db_path.exists():
        print("No card catalog yet — run `libkb reindex` first.")
        return 1
    store = LibraryStore(settings.library_dir)
    catalog = Catalog(settings.db_path)
    report = build_crosslinks(
        store,
        catalog,
        min_delta=args.min_delta,
        max_per_book=args.max_per_book,
        dry_run=args.dry_run,
    )
    catalog.close()

    verb = "Would write" if args.dry_run else "Wrote"
    print(f"Misshelved pages considered: {report.considered}")
    print(f"  skipped, same shelf (already on the menu): {report.skipped_same_shelf}")
    print(
        f"  skipped, crosses a domain (false positives + D-020 privacy): "
        f"{report.skipped_cross_domain}"
    )
    print(f"  skipped, pull too weak (< {args.min_delta}): {report.skipped_below_floor}")
    print(f"  skipped, book already at the cap ({args.max_per_book}): {report.skipped_over_cap}")
    if not args.dry_run:
        print(f"  cleared stale machine-made links: {report.cleared}")
    print(f"\n{verb} {report.written or len(report.links)} cross-references:\n")
    for link in report.links:
        print(f'  d+{link.delta:.3f}  "{link.from_book}"  →  {link.to_path}')
    print("\nThese render on the shelf menu and are readable directly — the page stays where it")
    print("is, and the citation still reports its true home. A hint, never a gate.")
    return 0


def _cmd_harvest(args, settings) -> int:
    from libkb.catalog.store import Catalog
    from libkb.trajectory.harvest import harvest
    from libkb.trajectory.store import TrajectoryStore

    if not settings.db_path.exists():
        print("No catalog/trajectory db yet — ask the library something first.")
        return 1
    store = LibraryStore(settings.library_dir)
    catalog = Catalog(settings.db_path)
    trajectories = TrajectoryStore(settings.db_path)

    total = trajectories.count()
    answered = trajectories.count(status="answered")
    print(f"Trajectory log: {total} queries · {answered} answered\n")

    taken = harvest(trajectories, catalog, store, limit=args.limit, dry_run=args.dry_run)
    if not taken:
        print("Nothing new to harvest. (A trajectory is harvestable only if it was ANSWERED and")
        print("landed on exactly ONE page — otherwise we cannot say which page the question is")
        print("really about, and a mislabelled row is worse than a missing one.)")
    else:
        verb = "Would index" if args.dry_run else "Indexed"
        print(f"{verb} {len(taken)} REAL questions:\n")
        for query, path in taken:
            print(f'  "{query}"')
            print(f"      → {path}")

    failures = trajectories.failures(limit=5)
    if failures:
        print(f"\n{len(failures)} recent walks found nothing — each one names a description that")
        print("lied, or a real gap in the library:")
        for f in failures:
            print(f'  "{f.query}"   ({f.hops} hops / {f.backtracks} backtracks)')

    trajectories.close()
    catalog.close()
    print("\nGenerated questions are a guess about what a reader might ask. These are facts about")
    print("what one DID ask. Only the second kind compounds.")
    return 0


def _cmd_ask(args, settings) -> int:
    from libkb.agent.orchestrator import answer_query_safe
    from libkb.agent.tools import NavEvent

    library_dir = settings.library_dir
    if not (library_dir / "_meta.json").exists():
        print(f"No library at {library_dir.resolve()} — run `libkb seed` first.")
        return 1
    store = LibraryStore(library_dir)

    def on_event(ev: NavEvent) -> None:
        if not args.trace:
            return
        glyph = _TRACE_GLYPH.get(ev.action, "·")
        kind = f" ({ev.kind})" if ev.kind else ""
        detail = f"  — {ev.detail}" if ev.detail else ""
        print(f"  {glyph} {ev.title}{kind}{detail}")

    if args.trace:
        print(f'Walking the library for: "{args.query}"\n')
    result = answer_query_safe(args.query, store=store, event_cb=on_event)

    print("\n" + "─" * 60)
    print(result.answer.text)
    if result.answer.citations:
        print("\nCitations:")
        for c in result.answer.citations:
            print(f"  • {c.path}")
    nav = result.nav
    print(
        f"\n[{result.answer.status.upper()} · confidence {result.answer.confidence} · "
        f"{nav.hops} hops · {nav.backtracks} backtracks]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
