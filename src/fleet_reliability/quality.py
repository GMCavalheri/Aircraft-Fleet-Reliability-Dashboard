"""Data-quality gate: run every sql/tests/*.sql check against the loaded
warehouse. Each check is a SELECT that should return zero rows -- any row
it does return describes one violation. Exits non-zero (and prints the
offending rows) if anything fails, so it can gate a CI/CD pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import Connection, Row, text

from fleet_reliability.db import get_engine

TESTS_DIR = Path(__file__).resolve().parents[2] / "sql" / "tests"


def run_checks(conn: Connection, tests_dir: Path = TESTS_DIR) -> dict[str, list[Row]]:
    """Run every check on the given connection and return the violating
    rows per check file. Taking a connection (rather than opening one)
    lets tests run the checks inside a transaction they later roll back."""
    return {
        sql_file.name: conn.execute(text(sql_file.read_text())).fetchall()
        for sql_file in sorted(tests_dir.glob("*.sql"))
    }


def run(tests_dir: Path = TESTS_DIR) -> bool:
    with get_engine().connect() as conn:
        results = run_checks(conn, tests_dir)

    all_passed = True
    for name, rows in results.items():
        if rows:
            all_passed = False
            print(f"FAIL  {name}  ({len(rows)} violation(s))")
            for row in rows[:10]:
                print(f"        {tuple(row)}")
            if len(rows) > 10:
                print(f"        ... and {len(rows) - 10} more")
        else:
            print(f"PASS  {name}")

    return all_passed


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
