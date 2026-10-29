"""
scripts/rebuild_index.py
────────────────────────
Rebuilds both the persistent ChromaDB vector index and BM25 sparse index
from existing SQLite document records.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from database.initialization import get_db, initialize_database
from services.document_service import DocumentService


def main():
    print("=== Rebuilding TruthGuard Retrieval Indexes ===")
    initialize_database()

    doc_service = DocumentService()
    with get_db() as session:
        res = doc_service.rebuild_index(session)
        print(f"Rebuilt index with {res['total_documents']} documents and {res['total_chunks']} chunks.")

    print("[SUCCESS] Index synchronization complete.")


if __name__ == "__main__":
    main()
