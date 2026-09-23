"""Data-quality gate: run every sql/tests/*.sql check against the loaded
warehouse. Each check is a SELECT that should return zero rows -- any row
it does return describes one violation. Exits non-zero (and prints the
offending rows) if anything fails, so it can gate a CI/CD pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

from fleet_reliability.db import get_engine

TESTS_DIR = Path(__file__).resolve().parents[2] / "sql" / "tests"


def run(tests_dir: Path = TESTS_DIR) -> bool:
    engine = get_engine()
    all_passed = True

    for sql_file in sorted(tests_dir.glob("*.sql")):
        with engine.connect() as conn:
            result = conn.execute(text(sql_file.read_text()))
            rows = result.fetchall()

        if rows:
            all_passed = False
            print(f"FAIL  {sql_file.name}  ({len(rows)} violation(s))")
            for row in rows[:10]:
                print(f"        {tuple(row)}")
            if len(rows) > 10:
                print(f"        ... and {len(rows) - 10} more")
        else:
            print(f"PASS  {sql_file.name}")

    return all_passed


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
