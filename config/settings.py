"""
config/settings.py
──────────────────
Central configuration for TruthGuard loaded from environment variables /
.env file.  A module-level singleton ``settings`` is exported so callers
can do::

    from config.settings import settings

All values have safe defaults so the system starts even without a .env file
(using the ``mock`` LLM provider).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the project root (one directory above this file's package)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root if it exists
load_dotenv(_PROJECT_ROOT / ".env", override=False)


# ─────────────────────────────────────────────────────────────────────────────
# Authority hierarchy (higher number = higher authority)
# ─────────────────────────────────────────────────────────────────────────────
AUTHORITY_HIERARCHY: Dict[str, int] = {
    "Amendment": 4,
    "Policy": 3,
    "FAQ": 2,
    "Other": 1,
}

LLMProvider = Literal["openai", "groq", "ollama", "mock"]


class Settings(BaseSettings):
    """
    All configuration values for TruthGuard.

    Values are read (in priority order) from:
    1. Actual environment variables
    2. .env file at the project root
    3. The defaults defined here
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Project paths ────────────────────────────────────────────────────────
    project_root: Path = Field(default=_PROJECT_ROOT, description="Absolute project root")

    # ── LLM provider ─────────────────────────────────────────────────────────
    llm_provider: LLMProvider = Field(default="mock", description="Active LLM backend")

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI secret key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")

    # Groq
    groq_api_key: str = Field(default="", description="Groq secret key")
    groq_model: str = Field(default="llama3-70b-8192", description="Groq model name")

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    ollama_model: str = Field(default="llama3", description="Ollama model name")

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="HuggingFace sentence-transformers model name",
    )

    # ── Vector store ──────────────────────────────────────────────────────────
    chroma_persist_dir: str = Field(
        default="data/chroma",
        description="Path (relative or absolute) for ChromaDB persistence",
    )

    # ── Relational DB ─────────────────────────────────────────────────────────
    sqlite_db_path: str = Field(
        default="data/truthguard.db",
        description="Path (relative or absolute) for the SQLite database",
    )

    # ── Ingestion limits ──────────────────────────────────────────────────────
    max_file_size_mb: float = Field(default=50.0, description="Maximum upload size in MB")

    # ── Agent loop ────────────────────────────────────────────────────────────
    max_revisions: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Maximum critic–revise cycles before escalating to human review",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Python logging level")

    # ── Admin auth ────────────────────────────────────────────────────────────
    admin_password: str = Field(default="changeme", description="Simple local admin password")

    # ── Document authority hierarchy ──────────────────────────────────────────
    authority_hierarchy: Dict[str, int] = Field(
        default=AUTHORITY_HIERARCHY,
        description="Maps document type names to integer authority levels",
    )

    # ── Chunking defaults ─────────────────────────────────────────────────────
    default_chunk_size: int = Field(default=512, description="Target tokens per chunk")
    default_chunk_overlap: int = Field(default=50, description="Overlap tokens between chunks")

    # ─────────────────────────────────────────────────────────────────────────
    # Validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return upper

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """
        Ensure chroma_persist_dir and sqlite_db_path are absolute paths
        rooted at the project root when given as relative strings.
        """
        root = self.project_root

        def _abs(p: str) -> str:
            path = Path(p)
            if not path.is_absolute():
                path = root / path
            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)

        self.chroma_persist_dir = _abs(self.chroma_persist_dir)
        self.sqlite_db_path = _abs(self.sqlite_db_path)
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience helpers
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum allowed upload size in bytes."""
        return int(self.max_file_size_mb * 1024 * 1024)

    @property
    def sqlite_url(self) -> str:
        """SQLAlchemy-compatible database URL for SQLite."""
        return f"sqlite:///{self.sqlite_db_path}"

    def authority_level_for(self, doc_type: str) -> int:
        """Return the numeric authority level for a document type (default 1)."""
        return self.authority_hierarchy.get(doc_type, 1)

    def active_llm_model(self) -> str:
        """Return the model name string for the currently active LLM provider."""
        mapping = {
            "openai": self.openai_model,
            "groq": self.groq_model,
            "ollama": self.ollama_model,
            "mock": "mock-model",
        }
        return mapping.get(self.llm_provider, "mock-model")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Settings(llm_provider={self.llm_provider!r}, "
            f"embedding_model={self.embedding_model!r}, "
            f"max_revisions={self.max_revisions})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    Use this instead of instantiating Settings directly so that the
    same object is shared across the entire application.
    """
    return Settings()


# Module-level singleton for convenient import
settings: Settings = get_settings()
