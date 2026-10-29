"""
retrieval/embedding_service.py
------------------------------
Embedding service using sentence-transformers.
Provides singleton model loading with lazy initialization.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton cache
# ---------------------------------------------------------------------------
_model_cache: dict[str, "SentenceTransformer"] = {}  # noqa: F821


def _get_model(model_name: str) -> "SentenceTransformer":  # noqa: F821
    """Return a cached SentenceTransformer instance, loading it on first use."""
    if model_name not in _model_cache:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required. Install it with: "
                "pip install sentence-transformers"
            ) from exc

        logger.info("Loading embedding model: %s", model_name)
        model = SentenceTransformer(model_name)
        _model_cache[model_name] = model
        logger.info("Embedding model '%s' loaded successfully.", model_name)

    return _model_cache[model_name]


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------

class EmbeddingService:
    """
    Wraps a sentence-transformers model to produce dense vector embeddings.

    The underlying model is loaded lazily on the first call to
    ``embed_text`` or ``embed_batch``, and is cached for the process
    lifetime so subsequent calls are instantaneous.

    Configuration
    -------------
    The model name is resolved in this priority order:
      1. ``model_name`` argument passed to the constructor.
      2. ``EMBEDDING_MODEL`` environment variable.
      3. Hard-coded default ``"all-MiniLM-L6-v2"``.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name: str = (
            model_name
            or os.getenv("EMBEDDING_MODEL", self.DEFAULT_MODEL)
        )
        # We do NOT load the model here – lazy loading on first use.
        self._model = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_model(self) -> "SentenceTransformer":  # noqa: F821
        """Load (or retrieve from cache) the underlying model."""
        if self._model is None:
            self._model = _get_model(self._model_name)
        return self._model

    @staticmethod
    def _validate_text(text: str) -> str:
        """Strip and return text; raise ValueError if the result is empty."""
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        return text.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        """Return the configured model name (may not be loaded yet)."""
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        """Return the dimensionality of the embeddings produced by this model."""
        model = self._ensure_model()
        return model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> list[float]:
        """
        Embed a single piece of text.

        Parameters
        ----------
        text:
            The text to embed.  Whitespace-only strings are treated as empty
            and return a zero vector of the appropriate dimension.

        Returns
        -------
        list[float]
            A list of floats representing the dense embedding vector.
        """
        cleaned = self._validate_text(text)
        if not cleaned:
            logger.debug("embed_text received empty text – returning zero vector.")
            model = self._ensure_model()
            dim = model.get_sentence_embedding_dimension()
            return [0.0] * dim

        model = self._ensure_model()
        embedding = model.encode(cleaned, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts in a single forward pass for efficiency.

        Parameters
        ----------
        texts:
            A list of strings to embed.  Empty strings or whitespace-only
            entries are replaced with zero vectors; the list length and
            ordering are always preserved.

        Returns
        -------
        list[list[float]]
            A list of embedding vectors, one per input text.
        """
        if not texts:
            return []

        model = self._ensure_model()
        dim = model.get_sentence_embedding_dimension()

        cleaned: list[str] = []
        empty_indices: set[int] = set()

        for i, text in enumerate(texts):
            stripped = self._validate_text(text) if isinstance(text, str) else ""
            if stripped:
                cleaned.append(stripped)
            else:
                empty_indices.add(i)
                cleaned.append("")  # placeholder – will be replaced

        # Encode all non-empty texts in one batch
        non_empty_texts = [t for t in cleaned if t]
        if non_empty_texts:
            encoded = model.encode(non_empty_texts, convert_to_numpy=True, batch_size=64)
            encoded_list = [row.tolist() for row in encoded]
        else:
            encoded_list = []

        # Reconstruct result preserving original order
        result: list[list[float]] = []
        encoded_iter = iter(encoded_list)
        for i in range(len(texts)):
            if i in empty_indices:
                result.append([0.0] * dim)
            else:
                result.append(next(encoded_iter))

        logger.debug(
            "embed_batch: encoded %d texts (%d empty/zero).",
            len(non_empty_texts),
            len(empty_indices),
        )
        return result

    def __repr__(self) -> str:
        loaded = self._model is not None
        return f"EmbeddingService(model={self._model_name!r}, loaded={loaded})"
