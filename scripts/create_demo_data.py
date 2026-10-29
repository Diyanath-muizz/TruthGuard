"""
scripts/create_demo_data.py
───────────────────────────
Loads all demonstration documents into SQLite, ChromaDB, and the BM25 index.
Ensures TruthGuard is pre-loaded for real-time demonstrations.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import settings
from database.initialization import get_db, initialize_database
from evaluation.synthetic_corpus import get_synthetic_documents
from services.document_service import DocumentService


def main():
    print("=== Loading TruthGuard Demonstration Corpus ===")
    initialize_database()

    doc_service = DocumentService()
    docs = get_synthetic_documents()
    print(f"Preparing to ingest {len(docs)} demonstration documents...")

    with get_db() as session:
        for idx, d in enumerate(docs):
            filename = d["filename"]
            content = d["content"].encode("utf-8")
            res = doc_service.process_upload(
                file_bytes=content,
                filename=filename,
                db_session=session,
            )
            if res.success:
                print(f"[{idx+1:02d}/{len(docs)}] Ingested {filename} -> Doc ID {res.doc_id} ({res.chunk_count} chunks)")
                if res.conflict_count > 0:
                    print(f"     [!] {res.conflict_count} proactive conflicts surfaced!")
            else:
                print(f"[{idx+1:02d}/{len(docs)}] Skipped/Error on {filename}: {res.errors}")

    print("\n[SUCCESS] Demo corpus successfully ingested!")


if __name__ == "__main__":
    main()
