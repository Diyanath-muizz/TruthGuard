"""
evaluation/__init__.py
──────────────────────
Evaluation dataset generators, gold-standard definitions, and metrics calculators.
"""

from evaluation.synthetic_corpus import get_synthetic_documents, write_synthetic_corpus
from evaluation.metrics import EvaluationMetrics

__all__ = ["get_synthetic_documents", "write_synthetic_corpus", "EvaluationMetrics"]
