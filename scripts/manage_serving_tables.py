import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from octane_db import default_db_path


DEFAULT_DBS = [
    Path(default_db_path()),
]


def _existing_paths(paths: Iterable[Path]) -> List[Path]:
    return [p for p in paths if p.exists()]


def _list_serving_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'serving_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _backup_db_file(src_db: Path, backup_dir: Path, timestamp: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{src_db.stem}.serving_backup.{timestamp}.db"
    shutil.copy2(src_db, backup_path)
    return backup_path


def _drop_tables(conn: sqlite3.Connection, table_names: List[str]) -> None:
    for table in table_names:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')


def process_db(db_path: Path, backup_dir: Path, execute: bool) -> None:
    conn = sqlite3.connect(db_path)
    try:
        tables = _list_serving_tables(conn)
        if not tables:
            print(f"[SKIP] {db_path}: no serving_* tables")
            return

        print(f"[FOUND] {db_path}: {tables}")
        if not execute:
            print(f"[DRY-RUN] {db_path}: would backup and drop {len(tables)} table(s)")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = _backup_db_file(db_path, backup_dir, timestamp)
        print(f"[BACKUP] {db_path} -> {backup_path}")

        conn.execute("BEGIN")
        _drop_tables(conn, tables)
        conn.commit()
        print(f"[DONE] {db_path}: dropped {len(tables)} table(s)")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup and optionally remove legacy serving_* tables from SQLite databases."
    )
    parser.add_argument(
        "--db-path",
        action="append",
        default=[],
        help="Path to a SQLite DB. Can be specified multiple times. Defaults to the shared auto DB path strategy (prefer local_data_rebuilt.db, fallback local_data.db).",
    )
    parser.add_argument(
        "--backup-dir",
        default="database/backups",
        help="Directory to store backup DB copies before dropping tables.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform backup + drop. Without this flag, runs as dry-run.",
    )
    args = parser.parse_args()

    user_paths = [Path(p) for p in args.db_path] if args.db_path else DEFAULT_DBS
    db_paths = _existing_paths(user_paths)
    if not db_paths:
        print("No database files found.")
        return

    backup_dir = Path(args.backup_dir)
    for db_path in db_paths:
        process_db(db_path, backup_dir, execute=args.execute)


if __name__ == "__main__":
    main()
