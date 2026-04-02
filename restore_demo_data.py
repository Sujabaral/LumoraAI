#!/usr/bin/env python3
import argparse
import os
import sqlite3
from collections import defaultdict

# -------------------------
# helpers
# -------------------------
def die(msg: str, code: int = 1):
    print(f"❌ {msg}")
    raise SystemExit(code)

def list_tables(conn: sqlite3.Connection):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    return [r[0] for r in cur.fetchall()]

def table_info(conn: sqlite3.Connection, table: str):
    cur = conn.execute(f"PRAGMA table_info({table});")
    # cid, name, type, notnull, dflt_value, pk
    return cur.fetchall()

def has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in table_info(conn, table))

def common_columns(src_conn, dst_conn, table: str):
    src_cols = [r[1] for r in table_info(src_conn, table)]
    dst_cols = [r[1] for r in table_info(dst_conn, table)]
    common = [c for c in src_cols if c in dst_cols]
    return common

def row_count(conn: sqlite3.Connection, table: str, where: str = "", params=()):
    q = f"SELECT COUNT(*) FROM {table} " + (f"WHERE {where}" if where else "")
    return conn.execute(q, params).fetchone()[0]

def fetchall(conn: sqlite3.Connection, table: str, cols: list[str], where: str = "", params=()):
    col_sql = ", ".join(cols)
    q = f"SELECT {col_sql} FROM {table} " + (f"WHERE {where}" if where else "")
    cur = conn.execute(q, params)
    return cur.fetchall()

def insert_many(conn, table, cols, rows):
    if not rows:
        return 0

    qmarks = ",".join(["?"] * len(cols))
    col_sql = ",".join(cols)

    # ✅ Prevent crashes on unique collisions (only for psychiatrist_booking)
    if table == "psychiatrist_booking":
        q = f"INSERT OR IGNORE INTO {table} ({col_sql}) VALUES ({qmarks})"
    else:
        q = f"INSERT INTO {table} ({col_sql}) VALUES ({qmarks})"

    conn.executemany(q, rows)
    return conn.execute("SELECT changes();").fetchone()[0]

def pick_source_user_id(backup: sqlite3.Connection) -> int:
    # prefer user with most chat sessions
    tables = set(list_tables(backup))
    if "chat_session" in tables and has_column(backup, "chat_session", "user_id"):
        cur = backup.execute("""
            SELECT user_id, COUNT(*) AS n
            FROM chat_session
            WHERE user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY n DESC
            LIMIT 1;
        """)
        r = cur.fetchone()
        if r and r[0] is not None:
            return int(r[0])

    # fallback: any non-admin user
    if "user" in tables and has_column(backup, "user", "id"):
        cols = [r[1] for r in table_info(backup, "user")]
        # try to avoid admin if column exists
        if "username" in cols:
            cur = backup.execute("SELECT id FROM user WHERE username != 'admin' ORDER BY id DESC LIMIT 1;")
            r = cur.fetchone()
            if r:
                return int(r[0])
        cur = backup.execute("SELECT id FROM user ORDER BY id DESC LIMIT 1;")
        r = cur.fetchone()
        if r:
            return int(r[0])

    die("Could not pick a source user id from backup DB.")
    return 0

# -------------------------
# main restore
# -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-db", required=True)
    ap.add_argument("--backup-db", required=True)
    ap.add_argument("--target-user-id", required=True, type=int)
    ap.add_argument("--source-user-id", type=int, default=None)
    args = ap.parse_args()

    main_db = os.path.abspath(args.main_db)
    backup_db = os.path.abspath(args.backup_db)

    if not os.path.exists(main_db):
        die(f"Main DB not found: {main_db}")
    if not os.path.exists(backup_db):
        die(f"Backup DB not found: {backup_db}")

    print(f"📌 main  : {main_db} ({os.path.getsize(main_db)} bytes)")
    print(f"📌 backup: {backup_db} ({os.path.getsize(backup_db)} bytes)")

    main_conn = sqlite3.connect(main_db)
    backup_conn = sqlite3.connect(backup_db)

    # enforce FK in sqlite for this connection
    main_conn.execute("PRAGMA foreign_keys=ON;")
    backup_conn.execute("PRAGMA foreign_keys=ON;")

    main_tables = set(list_tables(main_conn))
    backup_tables = set(list_tables(backup_conn))

    print(f"✅ main tables  ({len(main_tables)}): {sorted(list(main_tables))}")
    print(f"✅ backup tables({len(backup_tables)}): {sorted(list(backup_tables))}")

    if "user" not in main_tables or "user" not in backup_tables:
        die("Both DBs must contain a 'user' table.")

    target_uid = args.target_user_id
    # verify target exists in main
    r = main_conn.execute("SELECT id, username, email FROM user WHERE id = ?", (target_uid,)).fetchone()
    if not r:
        die(f"Target user_id={target_uid} does not exist in MAIN DB.")
    print(f"🎯 target user in MAIN: id={r[0]} username={r[1]} email={r[2]}")

    source_uid = args.source_user_id
    if source_uid is None:
        source_uid = pick_source_user_id(backup_conn)

    r2 = backup_conn.execute("SELECT id, username, email FROM user WHERE id = ?", (source_uid,)).fetchone()
    if not r2:
        die(f"Source user_id={source_uid} does not exist in BACKUP DB.")
    print(f"🧲 source user in BACKUP: id={r2[0]} username={r2[1]} email={r2[2]}")

    # tables we want to copy (only if present in BOTH)
    candidates = [
        "chat_session",
        "chat_history",
        "chat_message",
        "mood_entry",
        "journal",
        "assessment_result",
        "user_feedback",
        "user_emotion_profile",
        "user_emotion_event",
        "distortion_event",
        "message_label",
        "eval_dataset",
        "eval_dataset_item",
        "appointment",
        "notification",
        "psychiatrist_booking",
    ]

    total_inserted = 0

    # We need to remap session ids if we copy chat_session
    session_id_map = {}  # old_session_id -> new_session_id

    # --- copy chat_session first (if exists) ---
    if "chat_session" in main_tables and "chat_session" in backup_tables and has_column(backup_conn, "chat_session", "user_id"):
        cols = common_columns(backup_conn, main_conn, "chat_session")
        # never copy raw PK id; let sqlite generate new ids
        if "id" in cols:
            cols.remove("id")

        rows = fetchall(
            backup_conn,
            "chat_session",
            cols,
            where="user_id = ?",
            params=(source_uid,),
        )

        # rewrite user_id
        if "user_id" in cols:
            uid_idx = cols.index("user_id")
            rows = [tuple((target_uid if i == uid_idx else v) for i, v in enumerate(row)) for row in rows]

        before = row_count(main_conn, "chat_session", "user_id = ?", (target_uid,))
        inserted = insert_many(main_conn, "chat_session", cols, rows)
        after = row_count(main_conn, "chat_session", "user_id = ?", (target_uid,))
        main_conn.commit()

        print(f"✅ chat_session inserted: {inserted} (before={before}, after={after})")
        total_inserted += inserted

        # build session_id_map by matching order of insertion using updated_at/created_at/title if possible
        # simplest: re-read newest sessions for target and map by row order
        # This is “good enough” for demo restore.
        if inserted > 0:
            # get old session ids from backup
            old_ids = [sid for (sid,) in backup_conn.execute(
                "SELECT id FROM chat_session WHERE user_id = ? ORDER BY id ASC", (source_uid,)
            ).fetchall()]
            # get new session ids from main
            new_ids = [sid for (sid,) in main_conn.execute(
                "SELECT id FROM chat_session WHERE user_id = ? ORDER BY id ASC", (target_uid,)
            ).fetchall()]

            # map last N (newly inserted) to old ids (same count)
            if len(new_ids) >= inserted:
                new_tail = new_ids[-inserted:]
                old_tail = old_ids[-inserted:]
                session_id_map = dict(zip(old_tail, new_tail))

    else:
        print("ℹ️ chat_session missing in one DB or has no user_id — skipping session copy")

    # --- helper to copy tables with user_id and maybe session_id ---
    def copy_user_table(table: str):
        nonlocal total_inserted
        if table not in main_tables:
            print(f"ℹ️ {table}: not in main DB, skipped")
            return
        if table not in backup_tables:
            print(f"ℹ️ {table}: not in backup DB, skipped")
            return

        cols = common_columns(backup_conn, main_conn, table)
        if not cols:
            print(f"ℹ️ {table}: no common columns, skipped")
            return

        # do not copy primary key
        if "id" in cols:
            cols.remove("id")

        # filter condition
        where = ""
        params = ()
        if has_column(backup_conn, table, "user_id"):
            where = "user_id = ?"
            params = (source_uid,)
        elif has_column(backup_conn, table, "labeled_by"):  # message_label labeled_by
            where = "labeled_by = ?"
            params = (source_uid,)
        else:
            print(f"ℹ️ {table}: no user_id/labeled_by in backup -> skipped")
            return

        rows = fetchall(backup_conn, table, cols, where=where, params=params)

        # rewrite user_id / labeled_by
        if "user_id" in cols:
            idx = cols.index("user_id")
            rows = [tuple((target_uid if i == idx else v) for i, v in enumerate(row)) for row in rows]
        if "labeled_by" in cols:
            idx = cols.index("labeled_by")
            rows = [tuple((target_uid if i == idx else v) for i, v in enumerate(row)) for row in rows]

        # rewrite session_id if table has session_id and we built a map
        if session_id_map and "session_id" in cols:
            sidx = cols.index("session_id")
            def remap_session(row):
                old_sid = row[sidx]
                new_sid = session_id_map.get(old_sid, old_sid)
                return tuple((new_sid if i == sidx else v) for i, v in enumerate(row))
            rows = [remap_session(r) for r in rows]

        inserted = insert_many(main_conn, table, cols, rows)
        main_conn.commit()
        print(f"✅ {table} inserted: {inserted}")
        total_inserted += inserted

    # copy remaining tables (history/message should come after sessions)
    for t in [
        "chat_history",
        "chat_message",
        "mood_entry",
        "journal",
        "assessment_result",
        "user_feedback",
        "user_emotion_profile",
        "user_emotion_event",
        "distortion_event",
        "message_label",
        "eval_dataset",
        "eval_dataset_item",
        "appointment",
        "notification",
        "psychiatrist_booking",
    ]:
        copy_user_table(t)

    print(f"\n🎉 Done. Total inserted rows: {total_inserted}")

if __name__ == "__main__":
    main()
import argparse
import sqlite3

TABLES_TO_COPY = [
    # user-linked, safe demo content
    "chat_session",
    "chat_history",
    "chat_message",
    "mood_entry",
    "journal",
    "assessment_result",
    "user_feedback",
    "user_emotion_profile",
    "user_emotion_event",
    "distortion_event",
    "saved_insight",
    "message_label",
    "eval_dataset",
    "eval_dataset_item",
    "appointment",
    "notification",
    "psychiatrist_booking",
]

SKIP_IF_MISSING = {"saved_insight"}  # if not present in your DB, script will skip cleanly


def table_exists(conn, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    )
    return cur.fetchone() is not None


def get_columns(conn, table: str):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def copy_table(conn, table: str, target_user_id: int):
    # main = conn, bak = attached
    main_cols = get_columns(conn, table)
    bak_cols = get_columns(conn, f"bak.{table}")

    # Use only intersection, keep order of main table columns
    cols = [c for c in main_cols if c in bak_cols]

    if not cols:
        print(f"⚠️ {table}: no compatible columns, skipped")
        return 0

    # If the table has user_id, force it to target_user_id on insert
    has_user_id = "user_id" in cols
    select_cols = []
    for c in cols:
        if c == "user_id":
            select_cols.append(str(int(target_user_id)) + " AS user_id")
        else:
            select_cols.append(c)

    # IMPORTANT: Avoid copying the same user’s old rows repeatedly.
    # We’ll always copy ALL rows from backup, but all become owned by target user.
    # If you want to copy only one backup user, you can add a WHERE later.
    insert_sql = f"""
        INSERT INTO {table} ({",".join(cols)})
        SELECT {",".join(select_cols)}
        FROM bak.{table}
    """

    cur = conn.execute("SELECT COUNT(*) FROM bak." + table)
    bak_count = cur.fetchone()[0]
    if bak_count == 0:
        print(f"ℹ️ {table}: backup empty, skipped")
        return 0

    conn.execute(insert_sql)
    inserted = conn.execute("SELECT changes()").fetchone()[0]
    print(f"✅ {table}: inserted {inserted}")
    return inserted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-db", required=True)
    ap.add_argument("--backup-db", required=True)
    ap.add_argument("--target-user-id", required=True, type=int)
    args = ap.parse_args()

    conn = sqlite3.connect(args.main_db)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"ATTACH DATABASE ? AS bak", (args.backup_db,))

    # Only copy tables that exist in BOTH DBs
    to_copy = []
    for t in TABLES_TO_COPY:
        if not table_exists(conn, t):
            if t in SKIP_IF_MISSING:
                print(f"ℹ️ {t}: not in main DB, skipped")
                continue
            # If it’s missing, skip (you may have removed/renamed it)
            print(f"ℹ️ {t}: not in main DB, skipped")
            continue
        if not table_exists(conn, f"bak.{t}"):
            print(f"ℹ️ {t}: not in backup DB, skipped")
            continue
        to_copy.append(t)

    # Order matters a bit for FKs; sessions before histories/messages helps.
    # We’ll also temporarily disable FK checks during import to avoid “older schema” mismatches,
    # then re-enable at the end.
    conn.execute("PRAGMA foreign_keys=OFF")

    total = 0
    try:
        conn.execute("BEGIN")
        for t in to_copy:
            # Never copy user table (avoid conflicts)
            if t == "user":
                continue
            total += copy_table(conn, t, args.target_user_id)
        conn.execute("COMMIT")
        print(f"\n🎉 Done. Total inserted rows: {total}")
    except Exception as e:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DETACH DATABASE bak")
        conn.close()


if __name__ == "__main__":
    main()



