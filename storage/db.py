"""SQLite хранилище сделок Golden Scanner."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parent / "trades.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_time TEXT,
            entry_price REAL,
            quantity REAL,
            stop_price REAL,
            take_price REAL,
            exit_time TEXT,
            exit_price REAL,
            exit_reason TEXT,
            r_multiple REAL,
            pnl_usd REAL,
            fees REAL,
            status TEXT DEFAULT 'open'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_open_trade(
    symbol: str,
    strategy: str,
    side: str,
    entry_price: float,
    quantity: float,
    stop: float,
    take: float,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO trades (symbol, strategy, side, entry_time, entry_price, quantity,
                           stop_price, take_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            symbol,
            strategy,
            side,
            datetime.now(timezone.utc).isoformat(),
            entry_price,
            quantity,
            stop,
            take,
        ),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return int(tid)


def close_trade(
    trade_id: int,
    exit_price: float,
    exit_reason: str,
    r_multiple: float,
    pnl_usd: float,
    fees: float = 0.0,
):
    conn = get_conn()
    conn.execute(
        """
        UPDATE trades SET exit_time=?, exit_price=?, exit_reason=?,
               r_multiple=?, pnl_usd=?, fees=?, status='closed'
        WHERE id=?
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            exit_price,
            exit_reason,
            r_multiple,
            pnl_usd,
            fees,
            trade_id,
        ),
    )
    conn.commit()
    conn.close()


def count_open() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
    conn.close()
    return int(n)


def has_open(symbol: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM trades WHERE symbol=? AND status='open' LIMIT 1", (symbol,)
    ).fetchone()
    conn.close()
    return row is not None


def get_open_trades() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_state(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def get_state(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default
