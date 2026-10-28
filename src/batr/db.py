"""SQLCipher 加密库的打开、遍历与写回。"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import sqlcipher3


def connect(path: str | Path, key: str) -> sqlite3.Connection:
    """打开 SQLCipher 加密的库并验证密钥（打不开会抛 sqlite3.DatabaseError）。"""
    con = sqlcipher3.connect(path)
    cur = con.cursor()
    cur.execute(f"PRAGMA key = \"x'{key}'\"")
    try:
        cur.execute("SELECT count(*) FROM sqlite_master")
        cur.fetchall()
    except Exception:
        con.close()
        raise
    return con


def list_tables(con: sqlite3.Connection) -> list[str]:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def select_tables(con: sqlite3.Connection, pattern: str) -> list[str]:
    """按正则筛出可能含玩家文本的表。"""
    pat = re.compile(pattern, re.I)
    return [t for t in list_tables(con) if pat.search(t)]
