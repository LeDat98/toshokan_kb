from pathlib import Path

import pytest

from libkb.config import Settings


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Keep tests away from the repo's real .env and ambient env vars."""
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_API_KEY", "LIBKB_MODEL", "LIBKB_MODEL_LITE", "LIBKB_EMBED_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_env_key_matches_case_insensitively(monkeypatch):
    # the user's .env spells it `Gemini_API_Key`
    monkeypatch.setenv("Gemini_Api_KEY", "test-key-123")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key == "test-key-123"


def test_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    settings = Settings(_env_file=None)
    assert settings.model == "gemini-3.5-flash"  # navigation needs the strong tier (D-027)
    assert settings.model_lite == "gemini-3.1-flash-lite"  # bulk question generation
    assert settings.embed_model == "gemini-embedding-001"
    assert settings.library_dir == Path("./library")
    assert settings.max_hops == 12
    assert settings.max_pages_per_nav == 6
    assert settings.ingest_confidence_gate == 0.7


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("LIBKB_MODEL", "gemini-x")
    monkeypatch.setenv("LIBKB_MAX_HOPS", "5")
    settings = Settings(_env_file=None)
    assert settings.model == "gemini-x"
    assert settings.max_hops == 5


def test_reads_env_file_with_spaces_and_casing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("Gemini_API_Key = from-file\n", encoding="utf-8")
    settings = Settings(_env_file=str(env_file))
    assert settings.gemini_api_key == "from-file"
