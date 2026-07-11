from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model: str = Field(default="gemini-3.5-flash", alias="LIBKB_MODEL")
    model_lite: str = Field(default="gemini-3.5-flash", alias="LIBKB_MODEL_LITE")
    embed_model: str = Field(default="gemini-embedding-001", alias="LIBKB_EMBED_MODEL")

    library_dir: Path = Field(default=Path("./library"), alias="LIBKB_LIBRARY_DIR")
    db_path: Path = Field(default=Path("./library/_catalog/catalog.db"), alias="LIBKB_DB_PATH")

    max_hops: int = Field(default=12, alias="LIBKB_MAX_HOPS")
    max_pages_per_nav: int = Field(default=6, alias="LIBKB_MAX_PAGES_PER_NAV")
    max_ask_librarian: int = Field(default=2, alias="LIBKB_MAX_ASK_LIBRARIAN")
    ingest_confidence_gate: float = Field(default=0.7, alias="LIBKB_INGEST_CONFIDENCE_GATE")
    questions_per_page: int = Field(default=4, alias="LIBKB_QUESTIONS_PER_PAGE")
    question_langs: tuple[str, ...] = ("vi", "en")
    branching_split_threshold: int = Field(default=50, alias="LIBKB_BRANCHING_SPLIT_THRESHOLD")


@lru_cache
def get_settings() -> Settings:
    return Settings()
