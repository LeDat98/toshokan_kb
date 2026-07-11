"""Guardrail tests for conventions promised in .agent/CONVENTIONS.md."""

from pathlib import Path

LIBKB = Path(__file__).resolve().parents[1] / "libkb"


def _sources() -> list[Path]:
    return list(LIBKB.rglob("*.py"))


def test_genai_imported_only_in_llm_client():
    markers = ("google.genai", "from google import genai")
    offenders = [
        p.name
        for p in _sources()
        if p.name != "client.py"
        and any(marker in p.read_text(encoding="utf-8") for marker in markers)
    ]
    assert offenders == [], f"google.genai imported outside llm/client.py: {offenders}"


def test_set_description_called_only_from_views():
    allowed = {"store.py", "views.py"}
    offenders = [
        p.name
        for p in _sources()
        if p.name not in allowed and ".set_description(" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"set_description called outside views.py: {offenders}"
