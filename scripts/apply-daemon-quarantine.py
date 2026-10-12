#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply a prepared, fingerprint-guarded single-record quarantine.

Run with native Termux Python, only within an authorized repair. No service,
package, system setting, system partition or SELinux changes are performed.
The original row and complete online backup remain in the prepared directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import time


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def file_metadata(path):
    info = path.stat()
    if hasattr(os, "getxattr"):
        context = os.getxattr(path, "security.selinux").rstrip(b"\0").decode()
    else:
        # Native Android Python omits this optional os API; use the read-only
        # platform utility instead of altering labels or guessing a context.
        context = subprocess.check_output(["/system/bin/ls", "-Z", str(path)], text=True).split()[0]
    return dict(uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode),
                selinux=context)


def table_hashes(connection, exclude_record):
    result = {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        condition = " WHERE _id!=1" if name == "featuredata" and exclude_record else ""
        rows = [list(row) for row in connection.execute('SELECT * FROM "'+name+'"'+condition+' ORDER BY rowid')]
        result[name] = hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if not args.apply:
        print("Prepared operation only; no live database change.")
        return
    if plan["database"] != "/data/user/0/com.miui.daemon/databases/mqsas.db":
        raise RuntimeError("unexpected target database")
    database = Path(plan["database"])
    backup = args.plan.parent / "mqsas-before.sqlite"
    if hashlib.sha256(backup.read_bytes()).hexdigest() != plan["backup_sha256"]:
        raise RuntimeError("prepared backup hash mismatch")
    if hashlib.sha256(Path("/system_ext/app/MiuiDaemon/MiuiDaemon.apk").read_bytes()).hexdigest() != plan["source_apk_sha256"]:
        raise RuntimeError("firmware APK changed since diagnosis")
    journal = Path(str(database)+"-journal")
    # Preserve the existing journal's ownership and label, avoiding a root-owned
    # journal or an unlink/recreate cycle while Android has its own connection.
    before_db, before_journal = file_metadata(database), file_metadata(journal)
    connection = sqlite3.connect(database, timeout=3, isolation_level=None)
    connection.row_factory = sqlite3.Row
    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    if mode not in ("delete", "truncate", "persist"):
        raise RuntimeError("unexpected journaling mode; do not switch a live WAL database")
    connection.execute("PRAGMA journal_mode=PERSIST")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT * FROM featuredata WHERE _id=1").fetchone()
        if row is None or fingerprint(dict(row)) != plan["row_sha256"]:
            raise RuntimeError("live row changed; refusing a broader repair")
        unchanged = table_hashes(connection, exclude_record=True)
        started = dict(monotonic_ns=time.monotonic_ns(), boottime_ns=time.clock_gettime_ns(7), realtime_ns=time.time_ns())
        count = connection.execute("DELETE FROM featuredata WHERE _id=1 AND ty=388 AND subclass IS NULL AND isuploaded=0").rowcount
        if count != 1 or connection.total_changes != 1:
            raise RuntimeError("unexpected mutation count")
        if table_hashes(connection, exclude_record=False) != unchanged:
            raise RuntimeError("another database row changed in the repair transaction")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    after_db, after_journal = file_metadata(database), file_metadata(journal)
    result = dict(applied=True, deleted_rows=count, record_retained_in_backup=True,
                  other_rows_unchanged_in_transaction=True, clocks_at_mutation=started,
                  before_database_metadata=before_db, after_database_metadata=after_db,
                  before_journal_metadata=before_journal, after_journal_metadata=after_journal,
                  ownership_and_selinux_preserved=before_db == after_db and before_journal == after_journal)
    (args.plan.parent / "apply-result.json").write_text(json.dumps(result, indent=2)+"\n")
    if not result["ownership_and_selinux_preserved"]:
        raise RuntimeError("repair committed; metadata mismatch requires investigation, do not overwrite database")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
