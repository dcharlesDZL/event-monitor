"""SQLite persistence for news items (dedup + history across restarts)."""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, List

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id        TEXT PRIMARY KEY,   -- hash(link)
                category  TEXT,
                country   TEXT,
                source    TEXT,
                title     TEXT,
                link      TEXT,
                summary   TEXT,
                urgent    INTEGER DEFAULT 0,
                published INTEGER,            -- unix ts (best effort)
                fetched   INTEGER             -- unix ts when we saw it
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_news_pub ON news(published DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_news_cat ON news(category)")


def upsert_news(items: List[Dict]) -> int:
    """Insert items, ignoring ones we've already stored. Returns new count."""
    new = 0
    with _lock, _conn() as c:
        for it in items:
            cur = c.execute(
                """
                INSERT OR IGNORE INTO news
                (id, category, country, source, title, link, summary, urgent, published, fetched)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    it["id"], it["category"], it["country"], it["source"],
                    it["title"], it["link"], it.get("summary", ""),
                    int(it.get("urgent", 0)), it.get("published", 0), it["fetched"],
                ),
            )
            new += cur.rowcount
    return new


def query_news(category: str = "", country: str = "", limit: int = 100) -> List[Dict]:
    sql = "SELECT * FROM news WHERE 1=1"
    args: List = []
    if category:
        sql += " AND category = ?"
        args.append(category)
    if country:
        sql += " AND country = ?"
        args.append(country)
    sql += " ORDER BY COALESCE(NULLIF(published,0), fetched) DESC LIMIT ?"
    args.append(limit)
    with _lock, _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def prune(keep: int = 2000) -> None:
    """Keep only the most recent N items to bound DB size."""
    with _lock, _conn() as c:
        c.execute(
            """
            DELETE FROM news WHERE id NOT IN (
                SELECT id FROM news
                ORDER BY COALESCE(NULLIF(published,0), fetched) DESC
                LIMIT ?
            )
            """,
            (keep,),
        )
