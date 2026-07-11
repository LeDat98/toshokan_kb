"""LibraryKB CLI: init, seed, ask (P1), ingest (P2), eval (P3), rebuild-views (P1)."""

from __future__ import annotations

import argparse
import shutil
import sys

from libkb import seed as seed_module
from libkb.config import get_settings
from libkb.library.models import ROOT_ID
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

    ingest_parser = sub.add_parser("ingest", help="Ingest a document [P2b]")
    ingest_parser.add_argument("source")

    sub.add_parser("eval", help="Run the routing eval — costs tokens [P3]")
    sub.add_parser("rebuild-views", help="Regenerate all descriptions bottom-up [P1]")

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

    if args.command == "ask":
        return _cmd_ask(args, settings)

    if args.command == "rebuild-views":
        from libkb.library.views import rebuild_all

        store = LibraryStore(settings.library_dir)
        report = rebuild_all(store)
        print(f"Rebuilt {report.rebuilt} descriptions across the tree.")
        return 0

    print(f"'{args.command}' arrives in a later phase — see .agent/ROADMAP.md")
    return 1


_TRACE_GLYPH = {
    "enter": "→",
    "open": "↳",
    "read": "▸",
    "back": "↩",
    "found": "✓",
    "not_found": "✗",
    "budget": "⏱",
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
    if args.shelves == "auto":
        from libkb.llm.client import get_llm

        llm = get_llm()

    report = import_folder(
        folder,
        args.domain,
        store,
        strategy=args.shelves,
        shelf_name=args.shelf_name,
        replace=args.replace,
        llm=llm,
        progress=print,
    )
    print(
        f"\nImported into '{report.domain}': {report.shelves} shelves · "
        f"{report.books} books · {report.pages} pages"
        + (f" ({report.skipped_pages} pages skipped)" if report.skipped_pages else "")
    )
    print(f"  provided by source: {', '.join(report.provided)}")
    print(f"  filled by import:   {', '.join(report.missing) or '(nothing missing)'}")
    print(
        "\nTip: run `libkb rebuild-views` to regenerate shelf/domain descriptions with the model."
    )
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
