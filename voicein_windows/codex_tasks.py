import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

THREAD_ID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)

def _codex_home():
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"

def _state_database(home=None):
    root = Path(home) if home else _codex_home()
    databases = list(root.glob("state_*.sqlite"))
    if not databases:
        raise FileNotFoundError(f"未找到 Codex 状态数据库：{root}")
    return max(databases, key=lambda path: path.stat().st_mtime_ns)

def _clean_path(value):
    value = str(value or "")
    return value[4:].lstrip("\\") if value.startswith("\\\\?\\") else value

def discover_codex_tasks(home=None, limit=50):
    """Read recent local Codex tasks without writing to Codex state."""
    database = _state_database(home)
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
        if not {"id", "title", "cwd", "archived"}.issubset(columns):
            raise RuntimeError("当前 Codex 状态数据库缺少任务字段")
        title_parts = [f"NULLIF({name}, '')" for name in ("name", "title", "first_user_message") if name in columns]
        title_sql = "COALESCE(" + ", ".join(title_parts + ["id"]) + ")"
        recency = "recency_at_ms" if "recency_at_ms" in columns else ("updated_at_ms" if "updated_at_ms" in columns else "updated_at * 1000")
        source_filter = " AND (thread_source = 'user' OR thread_source IS NULL)" if "thread_source" in columns else ""
        query = f"SELECT id, {title_sql} AS display_title, cwd, {recency} AS updated_ms FROM threads WHERE archived = 0{source_filter} ORDER BY {recency} DESC LIMIT ?"
        tasks = []
        for row in connection.execute(query, (max(1, min(int(limit), 200)),)):
            thread_id = str(row["id"] or "")
            if not THREAD_ID.fullmatch(thread_id):
                continue
            updated_ms = int(row["updated_ms"] or 0)
            try:
                updated = datetime.fromtimestamp(updated_ms / 1000).astimezone().isoformat(timespec="seconds") if updated_ms else ""
            except (OSError, OverflowError, ValueError):
                updated = ""
            tasks.append({"id": thread_id, "title": str(row["display_title"] or thread_id).strip().replace("\r", " ").replace("\n", " ")[:160], "cwd": _clean_path(row["cwd"]), "updatedAt": updated})
        return tasks
    finally:
        connection.close()
