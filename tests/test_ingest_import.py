"""Import pipeline tests — deterministic, no LLM."""

import pytest

from libkb.ingest.importer import import_folder
from libkb.ingest.resolve import resolve_shelves
from libkb.ingest.survey import humanize, priority_of, survey_folder
from libkb.library.store import LibraryStore

PAGE = """---
title: Inventory Turnover Definition
description: >
  How many times stock sells and is replaced. COGS / Average Inventory. Matters to store
  managers because slow turns tie up cash.
related_kpis: [DIO, COGS, Sell-through Rate]
confidence: HIGH
---

# Inventory Turnover Definition

## Concept
Turnover = COGS / Average Inventory.

## Business Meaning
Higher is leaner.
"""

PAGE2 = """---
title: Gross Margin
description: Revenue minus COGS over revenue.
---

# Gross Margin
Body here.
"""

NO_FM = "# Stockout Detection\n\nPlain body, no frontmatter.\n"


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "knowledge"
    (root / "P0_KPI_Dictionary").mkdir(parents=True)
    (root / "P0_KPI_Dictionary" / "Inventory_Turnover.md").write_text(PAGE, encoding="utf-8")
    (root / "P0_KPI_Dictionary" / "Gross_Margin.md").write_text(PAGE2, encoding="utf-8")
    (root / "P1_Inventory_Management").mkdir()
    (root / "P1_Inventory_Management" / "Stockout Detection.md").write_text(NO_FM, encoding="utf-8")
    return root


def test_humanize_and_priority():
    assert humanize("P0_KPI_Dictionary") == "KPI Dictionary"
    assert humanize("lead-time_impact") == "Lead Time Impact"
    assert priority_of("P2_Store_Comparison") == "P2"
    assert priority_of("Random_Folder") is None


def test_survey_flat_folder(corpus):
    tree = survey_folder(corpus, "Retail")
    assert tree.domain_title == "Retail"
    assert {b.title for b in tree.books} == {"KPI Dictionary", "Inventory Management"}
    assert tree.missing == {"shelf"}
    assert "description" in tree.provided
    kpi = next(b for b in tree.books if b.title == "KPI Dictionary")
    assert kpi.priority == "P0"
    assert len(kpi.pages) == 2


def test_frontmatter_extraction(corpus):
    tree = survey_folder(corpus, "Retail")
    page = next(
        p for b in tree.books for p in b.pages if p.title == "Inventory Turnover Definition"
    )
    assert page.one_line.startswith("How many times stock sells")
    assert page.keywords == ["DIO", "COGS", "Sell-through Rate"]
    # frontmatter stripped from the reading body, content kept
    assert page.body_markdown.startswith("# Inventory Turnover Definition")
    assert "title:" not in page.body_markdown
    assert "## Concept" in page.body_markdown


def test_page_without_frontmatter_falls_back_to_heading(corpus):
    tree = survey_folder(corpus, "Retail")
    page = next(p for b in tree.books for p in b.pages if b.title == "Inventory Management")
    assert page.title == "Stockout Detection"  # from the first heading


def test_resolve_single_and_priority(corpus):
    tree = survey_folder(corpus, "Retail")
    resolve_shelves(tree, "single", shelf_name="Retail Analytics")
    assert len(tree.shelves) == 1
    assert tree.shelves[0].title == "Retail Analytics"
    assert "shelf" in tree.provided

    tree2 = survey_folder(corpus, "Retail")
    resolve_shelves(tree2, "priority")
    titles = sorted(sh.title for sh in tree2.shelves)
    assert titles == ["P0 — Core", "P1 — Extended"]


def test_import_commits_into_library(tmp_path, corpus):
    store = LibraryStore(tmp_path / "library")
    store.init_library()
    report = import_folder(
        corpus, "Retail", store, strategy="single", shelf_name="Retail Analytics"
    )
    assert (report.books, report.pages) == (2, 3)

    book_id = store.resolve_path("retail/retail-analytics/kpi-dictionary")
    toc = store.toc(book_id)
    titles = [e.title for ch in toc.chapters for e in ch.entries]
    assert "Inventory Turnover Definition" in titles
    page_id = next(
        e.page_id
        for ch in toc.chapters
        for e in ch.entries
        if e.title == "Inventory Turnover Definition"
    )
    page = store.page(page_id)
    assert "## Concept" in page.markdown
    assert page.source_ref.endswith("Inventory_Turnover.md")
    assert store.path_str(page_id).startswith("Retail ▸ Retail Analytics ▸ KPI Dictionary")


def test_reimport_is_idempotent(tmp_path, corpus):
    store = LibraryStore(tmp_path / "library")
    store.init_library()
    import_folder(corpus, "Retail", store, strategy="single")
    report2 = import_folder(corpus, "Retail", store, strategy="single")
    assert report2.pages == 0
    assert report2.skipped_pages == 3  # all three already there


def test_deep_folder_provides_shelves(tmp_path):
    root = tmp_path / "kb"
    book = root / "Analytics" / "KPIs"
    book.mkdir(parents=True)
    (book / "Turnover.md").write_text(PAGE, encoding="utf-8")
    tree = survey_folder(root, "Retail")
    assert tree.shelves and tree.shelves[0].title == "Analytics"
    assert tree.missing == set()
