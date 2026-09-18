import sqlite3
from datetime import datetime

DB_PATH = "signals.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            entry REAL,
            stop REAL,
            take REAL,
            risk_distance REAL,
            atr REAL,
            created_at TEXT,
            status TEXT DEFAULT 'active',
            result_price REAL,
            closed_at TEXT,
            bars_held INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS strength_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            old_strength TEXT,
            new_strength TEXT,
            changed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_signal(data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO signals
        (symbol, direction, entry, stop, take, risk_distance, atr, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["symbol"], data["direction"], data["entry"],
        data["stop"], data["take"], data["risk_distance"], data["atr"],
        datetime.utcnow().isoformat()
    ))
    signal_id = c.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def has_open_position(symbol: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM signals WHERE symbol = ? AND status = 'active'",
        (symbol,)
    )
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def count_open_positions() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM signals WHERE status = 'active'")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_active_signals(limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM signals WHERE status='active' ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_recent_signals(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def update_signal_status(signal_id: int, status: str, result_price: float = None, bars_held: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE signals
        SET status = ?, result_price = ?, closed_at = ?, bars_held = COALESCE(?, bars_held)
        WHERE id = ?
    """, (status, result_price, datetime.utcnow().isoformat(), bars_held, signal_id))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    stats = {
        "total": 0, "win": 0, "loss": 0, "expired": 0, "active": 0,
        "long_win": 0, "long_loss": 0, "short_win": 0, "short_loss": 0,
    }

    c.execute("SELECT COUNT(*) FROM signals")
    stats["total"] = c.fetchone()[0] or 0

    c.execute("SELECT status, COUNT(*) FROM signals GROUP BY status")
    for status, count in c.fetchall():
        if status in stats:
            stats[status] = count

    c.execute("SELECT COUNT(*) FROM signals WHERE direction='LONG' AND status='win'")
    stats["long_win"] = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM signals WHERE direction='LONG' AND status='loss'")
    stats["long_loss"] = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM signals WHERE direction='SHORT' AND status='win'")
    stats["short_win"] = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM signals WHERE direction='SHORT' AND status='loss'")
    stats["short_loss"] = c.fetchone()[0] or 0

    conn.close()
    return stats
