"""Routing evaluation (P3).

The question flywheel (D-005) doubles as the eval set: each generated question has a known
target page, so we can measure how often the librarian actually reaches it. `dataset` samples
cases from the catalog, `runner` walks each and scores how deep it got, `gates` turns a report
into pass/fail. This is how "beat PageIndex's 98.7%" becomes a number we can track and how the
catalog shortcut threshold gets calibrated.
"""
