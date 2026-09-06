"""Validate formal material units and write an auditable ingestion report."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.material_qa.services import MaterialDocumentValidator, MaterialIngestionReportStore


DOCUMENTS = {
    "ml": PROJECT_ROOT / "data/question_new/教材/ML-For-Beginners",
    "dl": PROJECT_ROOT / "data/question_new/教材/AI-For-Beginners/lessons",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=["ml", "dl"], action="append", dest="books")
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "data/material-reports")
    args = parser.parse_args()

    validator = MaterialDocumentValidator()
    reports = []
    for book_id in args.books or list(DOCUMENTS):
        report = {
            "batch_id": f"validate-{book_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
            "phase": "validation",
            "status": "valid",
            **validator.validate_tree(book_id=book_id, document_root=DOCUMENTS[book_id]),
        }
        if int(report["error_count"]):
            report["status"] = "invalid"
        report_path = MaterialIngestionReportStore(args.report_dir).write(report)
        reports.append((book_id, report, report_path))
        print(
            f"{book_id}: approved={report['approved_count']}, pending={report['pending_count']}, "
            f"excluded={report['excluded_count']}, errors={report['error_count']}\nreport={report_path}"
        )
    if any(int(report["error_count"]) for _, report, _ in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
