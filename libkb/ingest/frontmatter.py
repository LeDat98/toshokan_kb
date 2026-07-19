"""Parse YAML frontmatter out of a markdown document."""

from __future__ import annotations

import re
from typing import Any

import yaml

# PDF→markdown converters emit headings already in bold/italic ("# **1 Introduction**"), and the
# emphasis then rides into the page/book title, the TOC, the citation and the triage card. Lives
# here (not in split.py) so `parse.py` can clean the DOCUMENT title too without a circular import —
# split.py imports parse.py, so the shared helper must sit below both.
_EMPHASIS = re.compile(r"[*_`]{1,3}")


def clean_title(text: str) -> str:
    """A heading's markdown emphasis is formatting, not part of its name.

    Left in, `**PDF Retrieval Augmented Question Answering**` becomes the book title, then the shelf
    menu, then the citation the reader sees — MEASURED: a whole book was named that way. Applied to
    every title, from every source, at the one funnel each passes through.
    """
    return _EMPHASIS.sub("", text).strip()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body). Body excludes the YAML block.

    Tolerant: a document with no frontmatter returns ({}, text).
    """
    stripped = text.lstrip("﻿")  # tolerate a BOM
    if not stripped.startswith("---"):
        return {}, text
    lines = stripped.splitlines(keepends=True)
    # find the closing '---' after line 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    block = "".join(lines[1:end])
    body = "".join(lines[end + 1 :]).lstrip("\n")
    try:
        data = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, body


def first_heading(body: str) -> str | None:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or None
    return None
