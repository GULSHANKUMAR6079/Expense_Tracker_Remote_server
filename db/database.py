"""
MySQL database layer for the Expense Tracker MCP server.

Uses aiomysql for async database operations.  Connection parameters
are read from environment variables (MYSQL_HOST, MYSQL_PORT,
MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE).

Call ``init_db()`` on server startup to auto-create the database
and tables.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

import aiomysql

logger = logging.getLogger("expense_tracker.db")

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_conn_params() -> dict[str, Any]:
    """Return MySQL connection parameters from environment variables."""
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "db": os.getenv("MYSQL_DATABASE", "expense_tracker"),
        "autocommit": False,
    }


async def get_connection() -> aiomysql.Connection:
    """Open and return an aiomysql connection."""
    params = _get_conn_params()
    conn = await aiomysql.connect(**params)
    return conn


async def _ensure_database_exists() -> None:
    """Create the database if it does not exist yet."""
    params = _get_conn_params()
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


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_EXPENSES_TABLE = """
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

_BUDGETS_TABLE = """
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


async def init_db() -> None:
    """Create the database (if needed) and tables."""
    await _ensure_database_exists()

    db_name = os.getenv("MYSQL_DATABASE", "expense_tracker")
    logger.info("Initialising MySQL database '%s'", db_name)

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(_EXPENSES_TABLE)
            await cur.execute(_BUDGETS_TABLE)
        await conn.commit()
    finally:
        conn.close()

    logger.info("Database initialised successfully.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetchall(query: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    """Execute a SELECT and return all rows as list of dicts."""
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()
            return list(rows)
    finally:
        conn.close()


async def _fetchone(query: str, params: tuple | list = ()) -> Optional[dict[str, Any]]:
    """Execute a SELECT and return a single row as dict or None."""
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            row = await cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _serialise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert non-JSON-serialisable types (date, datetime, Decimal) to strings/floats."""
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


# ---------------------------------------------------------------------------
# CRUD — Expenses
# ---------------------------------------------------------------------------

async def insert_expense(
    title: str,
    amount: float,
    category: str,
    date: str,
    notes: Optional[str],
) -> dict[str, Any]:
    """Insert a new expense and return the created row as a dict."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO expenses (title, amount, category, date, notes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (title, amount, category, date, notes, now, now),
            )
            row_id = cur.lastrowid
        await conn.commit()
    finally:
        conn.close()

    return {
        "id": row_id,
        "title": title,
        "amount": amount,
        "category": category,
        "date": date,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }


async def fetch_expenses(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch expenses with optional filters."""
    query = "SELECT * FROM expenses WHERE 1=1"
    params: list[Any] = []

    if category:
        query += " AND category = %s"
        params.append(category)
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)

    query += " ORDER BY date DESC LIMIT %s"
    params.append(limit)

    rows = await _fetchall(query, params)
    return [_serialise_row(r) for r in rows]


async def fetch_expense_by_id(expense_id: int) -> Optional[dict[str, Any]]:
    """Fetch a single expense by ID."""
    row = await _fetchone("SELECT * FROM expenses WHERE id = %s", (expense_id,))
    return _serialise_row(row) if row else None


async def update_expense(expense_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    """Update specified fields of an expense.  Returns updated row or None."""
    if not fields:
        return await fetch_expense_by_id(expense_id)

    fields["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [expense_id]

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE expenses SET {set_clause} WHERE id = %s",
                values,
            )
        await conn.commit()
    finally:
        conn.close()

    return await fetch_expense_by_id(expense_id)


async def delete_expense(expense_id: int) -> bool:
    """Delete an expense.  Returns True if a row was deleted."""
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
            affected = cur.rowcount
        await conn.commit()
        return affected > 0
    finally:
        conn.close()


async def fetch_spending_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return aggregated spending grouped by category."""
    query = """
        SELECT category,
               CAST(SUM(amount) AS DOUBLE) AS total_spent,
               COUNT(*)                    AS transaction_count
        FROM expenses
        WHERE 1=1
    """
    params: list[Any] = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    query += " GROUP BY category ORDER BY total_spent DESC"

    rows = await _fetchall(query, params)
    return [_serialise_row(r) for r in rows]


async def fetch_top_expenses(n: int = 5) -> list[dict[str, Any]]:
    """Return the top-N most expensive items."""
    rows = await _fetchall(
        "SELECT * FROM expenses ORDER BY amount DESC LIMIT %s", (n,)
    )
    return [_serialise_row(r) for r in rows]


async def fetch_all_categories() -> list[str]:
    """Return a sorted list of distinct categories that have been used."""
    rows = await _fetchall(
        "SELECT DISTINCT category FROM expenses ORDER BY category"
    )
    return [row["category"] for row in rows]


# ---------------------------------------------------------------------------
# CRUD — Budgets
# ---------------------------------------------------------------------------

async def upsert_budget(
    category: str,
    limit_amount: float,
    month: int,
    year: int,
) -> dict[str, Any]:
    """Insert or update a budget entry.  Returns the upserted row."""
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO budgets (category, limit_amount, month, year)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE limit_amount = VALUES(limit_amount)
                """,
                (category, limit_amount, month, year),
            )
        await conn.commit()
    finally:
        conn.close()

    row = await _fetchone(
        "SELECT * FROM budgets WHERE category = %s AND month = %s AND year = %s",
        (category, month, year),
    )
    return _serialise_row(row) if row else {}


async def fetch_budget_status(
    month: int,
    year: int,
) -> list[dict[str, Any]]:
    """Compare budgets vs actual spending for a given month/year."""
    budgets = await _fetchall(
        "SELECT * FROM budgets WHERE month = %s AND year = %s",
        (month, year),
    )
    if not budgets:
        return []

    budgets = [_serialise_row(b) for b in budgets]

    # Build date range for the month
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    # Get spending for those categories in that month
    placeholders = ", ".join("%s" for _ in budgets)
    categories = [b["category"] for b in budgets]

    rows = await _fetchall(
        f"""
        SELECT category, CAST(SUM(amount) AS DOUBLE) AS total_spent
        FROM expenses
        WHERE category IN ({placeholders})
          AND date >= %s AND date < %s
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
