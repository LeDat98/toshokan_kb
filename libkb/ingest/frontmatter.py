"""Parse YAML frontmatter out of a markdown document."""

from __future__ import annotations

from typing import Any

import yaml


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
