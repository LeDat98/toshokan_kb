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

    ingest_parser = sub.add_parser("ingest", help="Ingest a document [P2]")
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

    print(f"'{args.command}' arrives in a later phase — see .agent/ROADMAP.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
