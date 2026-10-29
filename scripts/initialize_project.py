"""
scripts/initialize_project.py
─────────────────────────────
Initializes directories, SQLite database tables, and default settings.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import settings
from database.initialization import initialize_database
from evaluation.synthetic_corpus import write_synthetic_corpus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("truthguard.init")


def main():
    print("=== TruthGuard Initialization ===")
    # 1. Ensure data directories exist
    Path(settings.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.project_root) / "data" / "documents").mkdir(parents=True, exist_ok=True)
    print(f"Verified directories at {Path(settings.project_root) / 'data'}")

    # 2. Initialize SQLite tables
    initialize_database()
    print(f"SQLite database initialized at {settings.sqlite_db_path}")

    # 3. Create synthetic demonstration files
    corpus_dir = settings.project_root / "data" / "documents"
    paths = write_synthetic_corpus(corpus_dir)
    print(f"Created {len(paths)} demonstration documents in {corpus_dir}")

    print("\n[SUCCESS] Initialization complete! You can now start the Streamlit UI with:")
    print("   streamlit run app.py")


if __name__ == "__main__":
    main()
