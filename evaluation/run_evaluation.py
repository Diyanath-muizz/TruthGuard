"""
evaluation/run_evaluation.py
────────────────────────────
Standalone evaluation CLI runner.
Executes the gold standard benchmark suite and writes out timestamped evaluation reports.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import settings
from database.initialization import get_db, initialize_database
from evaluation.metrics import EvaluationMetrics
from workflows.question_answering_graph import run_qa_workflow

logging.basicConfig(level=logging.WARNING)


def main():
    print(f"Starting TruthGuard Evaluation Runner [Provider: {settings.llm_provider.upper()}]...")
    initialize_database()

    gold_path = Path(__file__).resolve().parent / "gold_standard.json"
    with open(gold_path, "r", encoding="utf-8") as f:
        gold_data = json.load(f)

    test_cases = gold_data.get("test_cases", [])
    print(f"Loaded {len(test_cases)} evaluation test cases.")

    results = []
    with get_db() as db_session:
        for idx, tc in enumerate(test_cases):
            print(f"[{idx+1:02d}/{len(test_cases)}] Evaluating {tc['id']}: '{tc['question'][:45]}...'")
            t0 = time.perf_counter()

            state = run_qa_workflow(
                question=tc["question"],
                db_session=db_session,
                max_revisions=2,
            )
            lat = int((time.perf_counter() - t0) * 1000)

            act_status = state.resolution_output.status.value if state.resolution_output else "failed"
            citations = [c.filename for c in state.resolution_output.citations] if state.resolution_output else []
            final_ans = state.resolution_output.final_answer if state.resolution_output else ""

            exp_status = tc.get("expected_status")
            status_match = (act_status == exp_status)

            results.append({
                "id": tc["id"],
                "category": tc.get("category"),
                "question": tc["question"],
                "expected_status": exp_status,
                "actual_status": act_status,
                "status_match": status_match,
                "citations": citations,
                "latency_ms": lat,
                "final_answer": final_ans,
            })

    metrics = EvaluationMetrics(gold_standard=test_cases, results=results)
    report = metrics.format_report()
    print("\n" + report)

    # Save to timestamped file
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = Path(__file__).resolve().parent / f"results_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics.compute_all(), "results": results}, f, indent=2)

    print(f"Detailed execution report saved to: {out_file.name}")


if __name__ == "__main__":
    main()
