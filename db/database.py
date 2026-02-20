"""
Database layer for the Expense Tracker MCP server.

Supports **two backends** selected by environment:
* ``mysql``  — Uses aiomysql (when MYSQL_PASSWORD is set)
* ``sqlite`` — Uses aiosqlite (default fallback)

**Multi-user support**: All expenses and budgets are scoped to a
``user_id``.  The ``users`` table stores API keys for authentication.

Call ``init_db()`` on server startup to auto-create tables.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("expense_tracker.db")

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _use_mysql() -> bool:
    explicit = os.getenv("DB_BACKEND", "").lower()
    if explicit == "mysql":
        return True
    if explicit == "sqlite":
        return False
    return bool(os.getenv("MYSQL_PASSWORD"))


USE_MYSQL = _use_mysql()

if USE_MYSQL:
    import aiomysql
else:
    import aiosqlite

logger.info("Database backend: %s", "MySQL" if USE_MYSQL else "SQLite")

# ---------------------------------------------------------------------------
# Connection pool (MySQL only)
# ---------------------------------------------------------------------------

_pool: aiomysql.Pool | None = None if USE_MYSQL else None


async def _get_pool() -> aiomysql.Pool:
    """Return (and lazily create) a MySQL connection pool."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = await aiomysql.create_pool(
            **_get_mysql_params(),
            minsize=1,
            maxsize=5,
        )
    return _pool


# ═══════════════════════════════════════════════════════════════════════════
# Connection helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_mysql_params() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "db": os.getenv("MYSQL_DATABASE", "expense_tracker"),
        "autocommit": False,
    }


async def _mysql_connection():
    pool = await _get_pool()
    return await pool.acquire()


async def _mysql_ensure_database() -> None:
    params = _get_mysql_params()
    db_name = params.pop("db")
    params.pop("autocommit", None)
    conn = await aiomysql.connect(**params, autocommit=True)
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
    finally:
        conn.close()


def _get_sqlite_path() -> str:
    db_path = os.getenv("DATABASE_PATH", "expenses.db")
    if not os.path.isabs(db_path):
        db_path = str(Path(__file__).resolve().parent.parent / db_path)
    return db_path


async def _sqlite_connection():
    conn = await aiosqlite.connect(_get_sqlite_path())
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ═══════════════════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════════════════

# ---- MySQL ----------------------------------------------------------------

_MYSQL_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100)   NOT NULL,
    email       VARCHAR(200),
    api_key     VARCHAR(64)    NOT NULL UNIQUE,
    created_at  DATETIME       NOT NULL,
    INDEX idx_api_key (api_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_MYSQL_EXPENSES_TABLE = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT            NOT NULL,
    title       VARCHAR(200)   NOT NULL,
    amount      DECIMAL(12,2)  NOT NULL,
    category    VARCHAR(50)    NOT NULL,
    date        DATE           NOT NULL,
    notes       VARCHAR(500),
    created_at  DATETIME       NOT NULL,
    updated_at  DATETIME       NOT NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_category (category),
    INDEX idx_date (date),
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_MYSQL_BUDGETS_TABLE = """
CREATE TABLE IF NOT EXISTS budgets (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT            NOT NULL,
    category      VARCHAR(50)    NOT NULL,
    limit_amount  DECIMAL(12,2)  NOT NULL,
    month         INT            NOT NULL,
    year          INT            NOT NULL,
    UNIQUE KEY uq_user_cat_month_year (user_id, category, month, year),
    INDEX idx_month_year (month, year),
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ---- SQLite ---------------------------------------------------------------

_SQLITE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT,
    api_key     TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);
"""

_SQLITE_EXPENSES_TABLE = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

_SQLITE_BUDGETS_TABLE = """
CREATE TABLE IF NOT EXISTS budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    category      TEXT    NOT NULL,
    limit_amount  REAL    NOT NULL,
    month         INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    UNIQUE(user_id, category, month, year),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

_SQLITE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);",
    "CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);",
    "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);",
    "CREATE INDEX IF NOT EXISTS idx_budgets_month_year ON budgets(month, year);",
]


async def init_db() -> None:
    """Create the database (if needed) and all tables."""
    if USE_MYSQL:
        await _mysql_ensure_database()
        logger.info("Initialising MySQL database '%s'",
                     os.getenv("MYSQL_DATABASE", "expense_tracker"))
        conn = await _mysql_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(_MYSQL_USERS_TABLE)
                await cur.execute(_MYSQL_EXPENSES_TABLE)
                await cur.execute(_MYSQL_BUDGETS_TABLE)
            await conn.commit()
        finally:
            conn.close()
        # Ensure user_id column exists (migration for pre-multi-user tables)
        await _ensure_user_id_columns()
    else:
        logger.info("Initialising SQLite database at %s", _get_sqlite_path())
        async with aiosqlite.connect(_get_sqlite_path()) as conn:
            await conn.execute(_SQLITE_USERS_TABLE)
            await conn.execute(_SQLITE_EXPENSES_TABLE)
            await conn.execute(_SQLITE_BUDGETS_TABLE)
            for idx in _SQLITE_INDEXES:
                await conn.execute(idx)
            await conn.commit()

    # Create a default user if none exists
    await _ensure_default_user()
    logger.info("Database initialised successfully.")


async def _ensure_user_id_columns() -> None:
    """Add user_id column to expenses/budgets if missing (migration)."""
    if not USE_MYSQL:
        return
    conn = await _mysql_connection()
    try:
        async with conn.cursor() as cur:
            for table in ("expenses", "budgets"):
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = 'user_id'",
                    (os.getenv("MYSQL_DATABASE", "expense_tracker"), table),
                )
                (count,) = await cur.fetchone()
                if count == 0:
                    logger.warning("Migrating table '%s': adding user_id column ...", table)
                    await cur.execute(
                        f"ALTER TABLE `{table}` ADD COLUMN user_id INT NOT NULL DEFAULT 1 AFTER id"
                    )
                    await cur.execute(
                        f"ALTER TABLE `{table}` ADD FOREIGN KEY (user_id) REFERENCES users(id)"
                    )
                    logger.info("Migration complete for table '%s'.", table)
        await conn.commit()
    finally:
        conn.close()


async def _ensure_default_user() -> None:
    """Create a default user for local/stdio usage if no users exist."""
    users = await _fetchall("SELECT id FROM users")
    if not users:
        default_key = os.getenv("DEFAULT_API_KEY", "default-local-key")
        await create_user("Default User", "local@localhost", default_key)
        logger.info("Created default user with API key: %s", default_key)


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

P = "%s" if USE_MYSQL else "?"


def _phs(count: int) -> str:
    return ", ".join(P for _ in range(count))


def _serialise_row(row: dict[str, Any]) -> dict[str, Any]:
    import decimal
    from datetime import date as date_type, datetime as dt_type
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, dt_type):
            out[k] = v.isoformat()
        elif isinstance(v, date_type):
            out[k] = v.isoformat()
        elif isinstance(v, decimal.Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


async def _fetchall(query: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    if USE_MYSQL:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                return list(await cur.fetchall())
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def _fetchone(query: str, params: tuple | list = ()) -> Optional[dict[str, Any]]:
    if USE_MYSQL:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                return dict(row) if row else None
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None


async def _execute(query: str, params: tuple | list = ()) -> tuple[int, int]:
    if USE_MYSQL:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                lid, rc = cur.lastrowid, cur.rowcount
            await conn.commit()
            return lid, rc
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.lastrowid, cursor.rowcount


# ═══════════════════════════════════════════════════════════════════════════
# CRUD — Users / Authentication
# ═══════════════════════════════════════════════════════════════════════════

async def create_user(
    name: str,
    email: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create a new user with a unique API key. Returns the user record."""
    if not api_key:
        api_key = secrets.token_hex(32)  # 64-char hex key
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    lid, _ = await _execute(
        f"INSERT INTO users (name, email, api_key, created_at) VALUES ({P}, {P}, {P}, {P})",
        (name, email, api_key, now),
    )
    return {"id": lid, "name": name, "email": email, "api_key": api_key, "created_at": now}


async def authenticate_user(api_key: str) -> Optional[dict[str, Any]]:
    """Look up a user by API key. Returns user dict or None."""
    row = await _fetchone(f"SELECT * FROM users WHERE api_key = {P}", (api_key,))
    return _serialise_row(row) if row else None


async def list_users() -> list[dict[str, Any]]:
    """List all users (without exposing full API keys)."""
    rows = await _fetchall("SELECT id, name, email, created_at FROM users")
    return [_serialise_row(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# CRUD — Expenses (scoped by user_id)
# ═══════════════════════════════════════════════════════════════════════════

async def insert_expense(
    user_id: int,
    title: str,
    amount: float,
    category: str,
    date: str,
    notes: Optional[str],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lid, _ = await _execute(
        f"""
        INSERT INTO expenses (user_id, title, amount, category, date, notes, created_at, updated_at)
        VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P})
        """,
        (user_id, title, amount, category, date, notes, now, now),
    )
    return {
        "id": lid, "user_id": user_id, "title": title, "amount": amount,
        "category": category, "date": date, "notes": notes,
        "created_at": now, "updated_at": now,
    }


async def fetch_expenses(
    user_id: int,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = f"SELECT * FROM expenses WHERE user_id = {P}"
    params: list[Any] = [user_id]
    if category:
        query += f" AND category = {P}"
        params.append(category)
    if start_date:
        query += f" AND date >= {P}"
        params.append(start_date)
    if end_date:
        query += f" AND date <= {P}"
        params.append(end_date)
    query += f" ORDER BY date DESC LIMIT {P}"
    params.append(limit)
    rows = await _fetchall(query, params)
    return [_serialise_row(r) for r in rows]


async def fetch_expense_by_id(user_id: int, expense_id: int) -> Optional[dict[str, Any]]:
    row = await _fetchone(
        f"SELECT * FROM expenses WHERE id = {P} AND user_id = {P}",
        (expense_id, user_id),
    )
    return _serialise_row(row) if row else None


async def update_expense(user_id: int, expense_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    if not fields:
        return await fetch_expense_by_id(user_id, expense_id)
    fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = {P}" for k in fields)
    values = list(fields.values()) + [expense_id, user_id]
    await _execute(f"UPDATE expenses SET {set_clause} WHERE id = {P} AND user_id = {P}", values)
    return await fetch_expense_by_id(user_id, expense_id)


async def delete_expense(user_id: int, expense_id: int) -> bool:
    _, rc = await _execute(
        f"DELETE FROM expenses WHERE id = {P} AND user_id = {P}",
        (expense_id, user_id),
    )
    return rc > 0


async def fetch_spending_summary(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    sum_expr = "CAST(SUM(amount) AS DOUBLE)" if USE_MYSQL else "SUM(amount)"
    query = f"""
        SELECT category, {sum_expr} AS total_spent, COUNT(*) AS transaction_count
        FROM expenses WHERE user_id = {P}
    """
    params: list[Any] = [user_id]
    if start_date:
        query += f" AND date >= {P}"
        params.append(start_date)
    if end_date:
        query += f" AND date <= {P}"
        params.append(end_date)
    query += " GROUP BY category ORDER BY total_spent DESC"
    rows = await _fetchall(query, params)
    return [_serialise_row(r) for r in rows]


async def fetch_top_expenses(user_id: int, n: int = 5) -> list[dict[str, Any]]:
    rows = await _fetchall(
        f"SELECT * FROM expenses WHERE user_id = {P} ORDER BY amount DESC LIMIT {P}",
        (user_id, n),
    )
    return [_serialise_row(r) for r in rows]


async def fetch_all_categories(user_id: int) -> list[str]:
    rows = await _fetchall(
        f"SELECT DISTINCT category FROM expenses WHERE user_id = {P} ORDER BY category",
        (user_id,),
    )
    return [row["category"] for row in rows]


# ═══════════════════════════════════════════════════════════════════════════
# CRUD — Budgets (scoped by user_id)
# ═══════════════════════════════════════════════════════════════════════════

async def upsert_budget(
    user_id: int,
    category: str,
    limit_amount: float,
    month: int,
    year: int,
) -> dict[str, Any]:
    if USE_MYSQL:
        await _execute(
            f"""
            INSERT INTO budgets (user_id, category, limit_amount, month, year)
            VALUES ({P}, {P}, {P}, {P}, {P}) AS new_val
            ON DUPLICATE KEY UPDATE limit_amount = new_val.limit_amount
            """,
            (user_id, category, limit_amount, month, year),
        )
    else:
        await _execute(
            f"""
            INSERT INTO budgets (user_id, category, limit_amount, month, year)
            VALUES ({P}, {P}, {P}, {P}, {P})
            ON CONFLICT(user_id, category, month, year)
            DO UPDATE SET limit_amount = excluded.limit_amount
            """,
            (user_id, category, limit_amount, month, year),
        )

    row = await _fetchone(
        f"SELECT * FROM budgets WHERE user_id = {P} AND category = {P} AND month = {P} AND year = {P}",
        (user_id, category, month, year),
    )
    return _serialise_row(row) if row else {}


async def fetch_budget_status(user_id: int, month: int, year: int) -> list[dict[str, Any]]:
    budgets = await _fetchall(
        f"SELECT * FROM budgets WHERE user_id = {P} AND month = {P} AND year = {P}",
        (user_id, month, year),
    )
    if not budgets:
        return []
    budgets = [_serialise_row(b) for b in budgets]

    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    placeholders = _phs(len(budgets))
    categories = [b["category"] for b in budgets]
    sum_expr = "CAST(SUM(amount) AS DOUBLE)" if USE_MYSQL else "SUM(amount)"

    rows = await _fetchall(
        f"""
        SELECT category, {sum_expr} AS total_spent
        FROM expenses
        WHERE user_id = {P} AND category IN ({placeholders})
          AND date >= {P} AND date < {P}
        GROUP BY category
        """,
        [user_id] + categories + [start_date, end_date],
    )
    spending = {row["category"]: float(row["total_spent"]) for row in rows}

    results = []
    for b in budgets:
        cat = b["category"]
        limit_amt = b["limit_amount"]
        spent = spending.get(cat, 0.0)
        remaining = limit_amt - spent
        pct = (spent / limit_amt * 100) if limit_amt > 0 else 0.0
        results.append({
            "category": cat, "limit_amount": limit_amt,
            "total_spent": round(spent, 2), "remaining": round(remaining, 2),
            "percentage_used": round(pct, 1),
        })
    return results
