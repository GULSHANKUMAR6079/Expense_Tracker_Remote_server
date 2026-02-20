"""
MCP Resource implementations for the Expense Tracker.

All resources use the module-level ``_DEFAULT_USER_ID`` for per-user scoping.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from db import database as db

logger = logging.getLogger("expense_tracker.resources")

# Module-level default user_id (set by main.py on startup)
_DEFAULT_USER_ID: int = 1


def set_default_user_id(uid: int) -> None:
    global _DEFAULT_USER_ID
    _DEFAULT_USER_ID = uid


# ---------------------------------------------------------------------------
# expense://all
# ---------------------------------------------------------------------------

async def get_all_expenses() -> str:
    """Return all expenses as a formatted JSON list.

    Resource URI: expense://all
    """
    try:
        rows = await db.fetch_expenses(user_id=_DEFAULT_USER_ID, limit=500)
        if not rows:
            return json.dumps({"message": "No expenses recorded yet.", "expenses": []}, indent=2)
        return json.dumps({"count": len(rows), "expenses": rows}, indent=2)
    except Exception as e:
        logger.error("Error fetching all expenses resource: %s", e)
        return json.dumps({"error": f"Failed to load expenses: {e}"})


# ---------------------------------------------------------------------------
# expense://summary
# ---------------------------------------------------------------------------

async def get_expense_summary() -> str:
    """Return the current month's spending summary.

    Resource URI: expense://summary
    """
    try:
        today = datetime.utcnow().date()
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()

        rows = await db.fetch_spending_summary(
            user_id=_DEFAULT_USER_ID, start_date=start_date, end_date=end_date,
        )
        grand_total = sum(r["total_spent"] for r in rows)
        return json.dumps({
            "period": "monthly", "month": today.month, "year": today.year,
            "start_date": start_date, "end_date": end_date,
            "grand_total": round(grand_total, 2), "categories": rows,
        }, indent=2)
    except Exception as e:
        logger.error("Error fetching summary resource: %s", e)
        return json.dumps({"error": f"Failed to load summary: {e}"})


# ---------------------------------------------------------------------------
# expense://categories
# ---------------------------------------------------------------------------

async def get_categories() -> str:
    """Return all unique categories used in expenses.

    Resource URI: expense://categories
    """
    try:
        categories = await db.fetch_all_categories(user_id=_DEFAULT_USER_ID)
        return json.dumps({"categories": categories}, indent=2)
    except Exception as e:
        logger.error("Error fetching categories resource: %s", e)
        return json.dumps({"error": f"Failed to load categories: {e}"})


# ---------------------------------------------------------------------------
# budget://status
# ---------------------------------------------------------------------------

async def get_budget_status_resource() -> str:
    """Return current budget vs actual for all categories.

    Resource URI: budget://status
    """
    try:
        now = datetime.utcnow()
        rows = await db.fetch_budget_status(
            user_id=_DEFAULT_USER_ID, month=now.month, year=now.year,
        )
        if not rows:
            return json.dumps({
                "month": now.month, "year": now.year,
                "message": "No budgets set for the current month.", "statuses": [],
            }, indent=2)
        return json.dumps({"month": now.month, "year": now.year, "statuses": rows}, indent=2)
    except Exception as e:
        logger.error("Error fetching budget status resource: %s", e)
        return json.dumps({"error": f"Failed to load budget status: {e}"})
