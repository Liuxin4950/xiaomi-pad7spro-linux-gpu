#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare an online SQLite backup and test a one-row quarantine on a copy.

This preparation tool never writes to the live database. Run with native
Termux Python from Android root so SQLite sees the real journal paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3


def row_hash(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def dump_hash(connection):
    return hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("/data/user/0/com.miui.daemon/databases/mqsas.db"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    args.output.chmod(0o700)
    live = sqlite3.connect(args.database.resolve().as_uri()+"?mode=ro", uri=True, timeout=2)
    live.row_factory = sqlite3.Row
    row = live.execute("SELECT * FROM featuredata WHERE _id=1 AND ty=388 AND subclass IS NULL AND isuploaded=0").fetchone()
    if not row or row["det"] != "me.weishu.kernelsu have been installed;" or row["prn"] != "system_server":
        raise RuntimeError("the identified malformed record no longer matches; do not repair by inference")
    row = dict(row)
    backup_path = args.output / "mqsas-before.sqlite"
    backup = sqlite3.connect(backup_path)
    live.backup(backup)
    live.close()
    if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("backup integrity check failed")
    backup.close()
    backup_path.chmod(0o600)
    (args.output / "quarantined-row.json").write_text(json.dumps(row, indent=2, ensure_ascii=False)+"\n")
    (args.output / "quarantined-row.json").chmod(0o600)
    stage_path = args.output / "staging.sqlite"
    shutil.copyfile(backup_path, stage_path)
    stage = sqlite3.connect(stage_path)
    stage.row_factory = sqlite3.Row
    before = dump_hash(stage)
    with stage:
        deleted = stage.execute("DELETE FROM featuredata WHERE _id=1 AND ty=388 AND subclass IS NULL AND isuploaded=0").rowcount
        if deleted != 1:
            raise RuntimeError("staging did not remove exactly one row")
    pending_after = stage.execute("SELECT COUNT(*) FROM featuredata WHERE isuploaded=0").fetchone()[0]
    with stage:
        columns = list(row)
        stage.execute("INSERT INTO featuredata ("+",".join(columns)+") VALUES ("+",".join("?" for _ in columns)+")",
                      [row[c] for c in columns])
    if dump_hash(stage) != before:
        raise RuntimeError("staging row restoration did not preserve all database contents")
    stage.close()
    plan = dict(database=str(args.database), row_id=1, row_type=388, subclass=None,
                operation="remove only this malformed row from the active upload queue; retain full backup and original row",
                row_sha256=row_hash(row), backup_sha256=hashlib.sha256(backup_path.read_bytes()).hexdigest(),
                source_apk_sha256=hashlib.sha256(Path("/system_ext/app/MiuiDaemon/MiuiDaemon.apk").read_bytes()).hexdigest(),
                live_database_modified=False, staging_delete_count=deleted,
                staging_pending_feature_rows_after=pending_after, staging_full_restore_verified=True)
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2)+"\n")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
