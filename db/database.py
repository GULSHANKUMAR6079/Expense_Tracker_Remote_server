"""
Database layer for the Expense Tracker MCP server.

Supports **two backends** selected by the ``DB_BACKEND`` env var:

* ``mysql``  — Uses aiomysql (default when MYSQL_PASSWORD is set)
* ``sqlite`` — Uses aiosqlite  (default fallback / FastMCP Cloud)

All CRUD functions are backend-agnostic; the internal helpers
abstract away the differences.

Call ``init_db()`` on server startup to auto-create tables.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("expense_tracker.db")

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _use_mysql() -> bool:
    """Return True if we should use the MySQL backend."""
    explicit = os.getenv("DB_BACKEND", "").lower()
    if explicit == "mysql":
        return True
    if explicit == "sqlite":
        return False
    # Auto-detect: use MySQL only if password is configured
    return bool(os.getenv("MYSQL_PASSWORD"))


USE_MYSQL = _use_mysql()

if USE_MYSQL:
    import aiomysql        # type: ignore[import-untyped]
else:
    import aiosqlite       # type: ignore[import-untyped]

logger.info("Database backend: %s", "MySQL" if USE_MYSQL else "SQLite")


# ═══════════════════════════════════════════════════════════════════════════
# Connection helpers
# ═══════════════════════════════════════════════════════════════════════════

# ---- MySQL ----------------------------------------------------------------

def _get_mysql_params() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "db": os.getenv("MYSQL_DATABASE", "expense_tracker"),
        "autocommit": False,
    }


async def _mysql_connection() -> aiomysql.Connection:
    return await aiomysql.connect(**_get_mysql_params())


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


# ---- SQLite ---------------------------------------------------------------

def _get_sqlite_path() -> str:
    db_path = os.getenv("DATABASE_PATH", "expenses.db")
    if not os.path.isabs(db_path):
        db_path = str(Path(__file__).resolve().parent.parent / db_path)
    return db_path


async def _sqlite_connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(_get_sqlite_path())
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ═══════════════════════════════════════════════════════════════════════════
# Schema initialisation
# ═══════════════════════════════════════════════════════════════════════════

_MYSQL_EXPENSES_TABLE = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    title       VARCHAR(200)   NOT NULL,
    amount      DECIMAL(12,2)  NOT NULL,
    category    VARCHAR(50)    NOT NULL,
    date        DATE           NOT NULL,
    notes       VARCHAR(500),
    created_at  DATETIME       NOT NULL,
    updated_at  DATETIME       NOT NULL,
    INDEX idx_category (category),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_MYSQL_BUDGETS_TABLE = """
CREATE TABLE IF NOT EXISTS budgets (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    category      VARCHAR(50)    NOT NULL,
    limit_amount  DECIMAL(12,2)  NOT NULL,
    month         INT            NOT NULL,
    year          INT            NOT NULL,
    UNIQUE KEY uq_cat_month_year (category, month, year),
    INDEX idx_month_year (month, year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_SQLITE_EXPENSES_TABLE = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

_SQLITE_BUDGETS_TABLE = """
CREATE TABLE IF NOT EXISTS budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT    NOT NULL,
    limit_amount  REAL    NOT NULL,
    month         INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    UNIQUE(category, month, year)
);
"""

_SQLITE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);",
    "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);",
    "CREATE INDEX IF NOT EXISTS idx_budgets_month_year ON budgets(month, year);",
]


async def init_db() -> None:
    """Create the database (if needed) and tables."""
    if USE_MYSQL:
        await _mysql_ensure_database()
        db_name = os.getenv("MYSQL_DATABASE", "expense_tracker")
        logger.info("Initialising MySQL database '%s'", db_name)
        conn = await _mysql_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(_MYSQL_EXPENSES_TABLE)
                await cur.execute(_MYSQL_BUDGETS_TABLE)
            await conn.commit()
        finally:
            conn.close()
    else:
        db_path = _get_sqlite_path()
        logger.info("Initialising SQLite database at %s", db_path)
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(_SQLITE_EXPENSES_TABLE)
            await conn.execute(_SQLITE_BUDGETS_TABLE)
            for idx in _SQLITE_INDEXES:
                await conn.execute(idx)
            await conn.commit()

    logger.info("Database initialised successfully.")


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers — abstract away backend differences
# ═══════════════════════════════════════════════════════════════════════════

def _ph(name: str = "") -> str:
    """Return the placeholder string for the current backend."""
    return "%s" if USE_MYSQL else "?"


def _phs(count: int) -> str:
    """Return comma-separated placeholders."""
    p = "%s" if USE_MYSQL else "?"
    return ", ".join(p for _ in range(count))


def _serialise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal / date / datetime to JSON-safe types."""
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
        conn = await _mysql_connection()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                return list(await cur.fetchall())
        finally:
            conn.close()
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def _fetchone(query: str, params: tuple | list = ()) -> Optional[dict[str, Any]]:
    if USE_MYSQL:
        conn = await _mysql_connection()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None


async def _execute(query: str, params: tuple | list = ()) -> tuple[int, int]:
    """Execute an INSERT/UPDATE/DELETE. Returns (lastrowid, rowcount)."""
    if USE_MYSQL:
        conn = await _mysql_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                lid, rc = cur.lastrowid, cur.rowcount
            await conn.commit()
            return lid, rc
        finally:
            conn.close()
    else:
        async with await _sqlite_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.lastrowid, cursor.rowcount


# ═══════════════════════════════════════════════════════════════════════════
# CRUD — Expenses
# ═══════════════════════════════════════════════════════════════════════════

P = "%s" if USE_MYSQL else "?"   # module-level shorthand


async def insert_expense(
    title: str,
    amount: float,
    category: str,
    date: str,
    notes: Optional[str],
) -> dict[str, Any]:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    lid, _ = await _execute(
        f"""
        INSERT INTO expenses (title, amount, category, date, notes, created_at, updated_at)
        VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P})
        """,
        (title, amount, category, date, notes, now, now),
    )
    return {
        "id": lid, "title": title, "amount": amount,
        "category": category, "date": date, "notes": notes,
        "created_at": now, "updated_at": now,
    }


async def fetch_expenses(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM expenses WHERE 1=1"
    params: list[Any] = []
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


async def fetch_expense_by_id(expense_id: int) -> Optional[dict[str, Any]]:
    row = await _fetchone(f"SELECT * FROM expenses WHERE id = {P}", (expense_id,))
    return _serialise_row(row) if row else None


async def update_expense(expense_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    if not fields:
        return await fetch_expense_by_id(expense_id)
    fields["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = {P}" for k in fields)
    values = list(fields.values()) + [expense_id]
    await _execute(f"UPDATE expenses SET {set_clause} WHERE id = {P}", values)
    return await fetch_expense_by_id(expense_id)


async def delete_expense(expense_id: int) -> bool:
    _, rc = await _execute(f"DELETE FROM expenses WHERE id = {P}", (expense_id,))
    return rc > 0


async def fetch_spending_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    sum_expr = "CAST(SUM(amount) AS DOUBLE)" if USE_MYSQL else "SUM(amount)"
    query = f"""
        SELECT category,
               {sum_expr} AS total_spent,
               COUNT(*)   AS transaction_count
        FROM expenses WHERE 1=1
    """
    params: list[Any] = []
    if start_date:
        query += f" AND date >= {P}"
        params.append(start_date)
    if end_date:
        query += f" AND date <= {P}"
        params.append(end_date)
    query += " GROUP BY category ORDER BY total_spent DESC"
    rows = await _fetchall(query, params)
    return [_serialise_row(r) for r in rows]


async def fetch_top_expenses(n: int = 5) -> list[dict[str, Any]]:
    rows = await _fetchall(
        f"SELECT * FROM expenses ORDER BY amount DESC LIMIT {P}", (n,)
    )
    return [_serialise_row(r) for r in rows]


async def fetch_all_categories() -> list[str]:
    rows = await _fetchall(
        "SELECT DISTINCT category FROM expenses ORDER BY category"
    )
    return [row["category"] for row in rows]


# ═══════════════════════════════════════════════════════════════════════════
# CRUD — Budgets
# ═══════════════════════════════════════════════════════════════════════════

async def upsert_budget(
    category: str,
    limit_amount: float,
    month: int,
    year: int,
) -> dict[str, Any]:
    if USE_MYSQL:
        await _execute(
            f"""
            INSERT INTO budgets (category, limit_amount, month, year)
            VALUES ({P}, {P}, {P}, {P})
            ON DUPLICATE KEY UPDATE limit_amount = VALUES(limit_amount)
            """,
            (category, limit_amount, month, year),
        )
    else:
        await _execute(
            f"""
            INSERT INTO budgets (category, limit_amount, month, year)
            VALUES ({P}, {P}, {P}, {P})
            ON CONFLICT(category, month, year)
            DO UPDATE SET limit_amount = excluded.limit_amount
            """,
            (category, limit_amount, month, year),
        )

    row = await _fetchone(
        f"SELECT * FROM budgets WHERE category = {P} AND month = {P} AND year = {P}",
        (category, month, year),
    )
    return _serialise_row(row) if row else {}


async def fetch_budget_status(month: int, year: int) -> list[dict[str, Any]]:
    budgets = await _fetchall(
        f"SELECT * FROM budgets WHERE month = {P} AND year = {P}",
        (month, year),
    )
    if not budgets:
        return []

    budgets = [_serialise_row(b) for b in budgets]

    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    placeholders = _phs(len(budgets))
    categories = [b["category"] for b in budgets]
    sum_expr = "CAST(SUM(amount) AS DOUBLE)" if USE_MYSQL else "SUM(amount)"

    rows = await _fetchall(
        f"""
        SELECT category, {sum_expr} AS total_spent
        FROM expenses
        WHERE category IN ({placeholders})
          AND date >= {P} AND date < {P}
        GROUP BY category
        """,
        categories + [start_date, end_date],
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
            "category": cat,
            "limit_amount": limit_amt,
            "total_spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "percentage_used": round(pct, 1),
        })
    return results
