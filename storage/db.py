"""SQLite хранилище сделок Golden Scanner."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "trades.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
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
    rows = conn.execute("SELECT * FROM trades WHERE status='open' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_trades(limit: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Агрегированная статистика для Telegram."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    open_n = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
    closed = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed'").fetchone()[0]

    wins = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND exit_reason='TP'"
    ).fetchone()[0]
    losses = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND exit_reason='SL'"
    ).fetchone()[0]
    expired = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND exit_reason='TIME'"
    ).fetchone()[0]

    long_win = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND side='LONG' AND exit_reason='TP'"
    ).fetchone()[0]
    long_loss = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND side='LONG' AND exit_reason='SL'"
    ).fetchone()[0]
    short_win = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND side='SHORT' AND exit_reason='TP'"
    ).fetchone()[0]
    short_loss = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND side='SHORT' AND exit_reason='SL'"
    ).fetchone()[0]

    sum_r = conn.execute(
        "SELECT COALESCE(SUM(r_multiple), 0) FROM trades WHERE status='closed'"
    ).fetchone()[0]
    sum_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades WHERE status='closed'"
    ).fetchone()[0]

    by_strat = conn.execute(
        """
        SELECT strategy,
               SUM(CASE WHEN exit_reason='TP' THEN 1 ELSE 0 END) as w,
               SUM(CASE WHEN exit_reason='SL' THEN 1 ELSE 0 END) as l,
               COUNT(*) as n
        FROM trades WHERE status='closed'
        GROUP BY strategy
        """
    ).fetchall()
    conn.close()

    closed_decisive = wins + losses
    wr = round(wins / closed_decisive * 100, 1) if closed_decisive else 0.0
    long_c = long_win + long_loss
    short_c = short_win + short_loss

    return {
        "total": total,
        "open": open_n,
        "closed": closed,
        "win": wins,
        "loss": losses,
        "expired": expired,
        "wr": wr,
        "long_wr": round(long_win / long_c * 100, 1) if long_c else 0.0,
        "short_wr": round(short_win / short_c * 100, 1) if short_c else 0.0,
        "long_win": long_win,
        "long_loss": long_loss,
        "short_win": short_win,
        "short_loss": short_loss,
        "total_r": round(float(sum_r or 0), 2),
        "total_pnl": round(float(sum_pnl or 0), 2),
        "by_strategy": [dict(r) for r in by_strat],
    }


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


def is_scanning_enabled() -> bool:
    return get_state("scanning_enabled", "1") != "0"


def set_scanning_enabled(enabled: bool):
    set_state("scanning_enabled", "1" if enabled else "0")
