import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meditrack.db")

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_TRANSFERRED = "transferred"
STATUS_REVOKED = "revoked"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id       TEXT PRIMARY KEY,
            telegram_id     INTEGER NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            code            TEXT,
            transfer_number TEXT,
            date            TEXT
        )
    """)
    conn.commit()
    conn.close()


def now_str():
    return datetime.now().isoformat()


# ---------- قراءة ----------

def get_device(device_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    conn.close()
    return row


def get_active_by_telegram(telegram_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM devices WHERE telegram_id = ? AND status = ? "
        "ORDER BY date DESC",
        (telegram_id, STATUS_ACTIVE),
    ).fetchall()
    conn.close()
    return rows


def get_pending_by_telegram(telegram_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM devices WHERE telegram_id = ? AND status = ?",
        (telegram_id, STATUS_PENDING),
    ).fetchone()
    conn.close()
    return row


def get_all():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM devices ORDER BY date DESC").fetchall()
    conn.close()
    return rows


# ---------- كتابة ----------

def insert_device(device_id, telegram_id, status, code=None, transfer_number=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO devices "
        "(device_id, telegram_id, status, code, transfer_number, date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (device_id, telegram_id, status, code, transfer_number, now_str()),
    )
    conn.commit()
    conn.close()


def set_status(device_id, status):
    conn = get_conn()
    conn.execute(
        "UPDATE devices SET status = ? WHERE device_id = ?", (status, device_id)
    )
    conn.commit()
    conn.close()


def set_transfer_number(device_id, transfer_number):
    conn = get_conn()
    conn.execute(
        "UPDATE devices SET transfer_number = ? WHERE device_id = ?",
        (transfer_number, device_id),
    )
    conn.commit()
    conn.close()


def set_code(device_id, code):
    conn = get_conn()
    conn.execute(
        "UPDATE devices SET code = ?, status = ? WHERE device_id = ?",
        (code, STATUS_ACTIVE, device_id),
    )
    conn.commit()
    conn.close()


def delete_device(device_id):
    conn = get_conn()
    conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()


# ---------- لسيرفر /verify ----------

def verify_status(device_id):
    """يعيد أحد القيم: active / transferred / revoked / trial / not_found"""
    row = get_device(device_id)
    if row is None:
        return "not_found"
    return row["status"]


def export_status_json(path):
    """يكتب status.json بصيغة: {"devices": {"<device_id>": "<status>", ...}}
    تُنشر على GitHub Pages ليتحقق منها التطبيق."""
    conn = get_conn()
    rows = conn.execute("SELECT device_id, status FROM devices").fetchall()
    conn.close()
    data = {"devices": {row["device_id"]: row["status"] for row in rows}}
    with open(path, "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, ensure_ascii=False, indent=2)
