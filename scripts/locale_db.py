"""Locate Locale_<Table> SQLite files in decrypted/ by CONTENT, not filename.

NKDB 解密产物的文件名来自源文件的内容 hash——游戏每次更新 hash 都会变，
脚本里硬编码 hash 路径会静默失效（2026-11-19 版本刷新时主线三个库就换了名）。
这里的接口按「表名 -> 文件」动态解析，一次建索引，全程只读。

    import locale_db
    p = locale_db.find("Locale_MainScenario")     # Path | None
    d  = locale_db.load("Locale_Stage")           # {Key: zh-CN}
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEC = BASE / "decrypted"

_INDEX: dict[str, list[Path]] | None = None


def _build() -> dict[str, list[Path]]:
    global _INDEX
    idx: dict[str, list[Path]] = {}
    for p in sorted(DEC.glob("*.dec")):
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            for (t,) in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Locale_%'"):
                idx.setdefault(t, []).append(p)
            con.close()
        except Exception:
            continue
    _INDEX = idx
    return idx


def index(refresh: bool = False) -> dict[str, list[Path]]:
    if _INDEX is None or refresh:
        return _build()
    return _INDEX


def find(table: str) -> Path | None:
    """包含该 Locale 表的解密库；有多个时取最新的文件。"""
    paths = index().get(table)
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def load(table: str, col: str = "zh-CN") -> dict[str, str]:
    """{Key: col}，key 重复时后者覆盖前者（表内 key 理论唯一）。"""
    p = find(table)
    if p is None:
        raise FileNotFoundError(f"decrypted/ 里没有任何库包含 {table}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        return dict(con.execute(f'SELECT "Key","{col}" FROM "{table}"'))
    finally:
        con.close()


def rowdicts(table: str, cols: tuple[str, ...]) -> list[dict]:
    """逐行返回 dict(cols)，供需要多语言列的脚本用。"""
    p = find(table)
    if p is None:
        raise FileNotFoundError(f"decrypted/ 里没有任何库包含 {table}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        sel = ",".join(f'"{c}"' for c in cols)
        return [dict(r) for r in con.execute(f'SELECT {sel} FROM "{table}"')]
    finally:
        con.close()
