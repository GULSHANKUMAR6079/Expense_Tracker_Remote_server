"""
MCP tool implementations for budget management.
"""

from __future__ import annotations

import logging
from datetime import datetime

from models.schemas import GetBudgetStatusInput, SetBudgetInput
from db import database as db

logger = logging.getLogger("expense_tracker.tools.budgets")


# ---------------------------------------------------------------------------
# set_budget
# ---------------------------------------------------------------------------

async def set_budget(
    category: str,
    limit_amount: float,
    month: int,
    year: int,
) -> dict:
    """Set or update a monthly budget for a category.

    Args:
        category: One of Food, Travel, Bills, Entertainment, Health, Shopping, Education, Other.
        limit_amount: The budget limit amount (must be > 0).
        month: Month number (1-12).
        year: Year (2000-2100).

    Returns:
        The created or updated budget record.
    """
    try:
        validated = SetBudgetInput(
            category=category,
            limit_amount=limit_amount,
            month=month,
            year=year,
        )
    except Exception as e:
        logger.warning("Validation failed for set_budget: %s", e)
        return {"error": f"Validation error: {e}"}

    try:
        record = await db.upsert_budget(
            category=validated.category.value,
            limit_amount=validated.limit_amount,
            month=validated.month,
            year=validated.year,
        )
        logger.info(
            "Budget set: %s %s/%s → %.2f",
            validated.category.value,
            validated.month,
            validated.year,
            validated.limit_amount,
        )
        return {"message": "Budget set successfully.", "budget": record}
    except Exception as e:
        logger.error("Database error in set_budget: %s", e)
        return {"error": f"Failed to set budget: {e}"}


# ---------------------------------------------------------------------------
# get_budget_status
# ---------------------------------------------------------------------------

async def get_budget_status(
    month: int | None = None,
    year: int | None = None,
) -> dict:
    """Compare budget vs actual spending per category.

    Args:
        month: Month number 1-12 (defaults to current month).
        year: Year (defaults to current year).

    Returns:
        Per-category budget status with limit, spent, remaining, and percentage.
    """
    try:
        validated = GetBudgetStatusInput(month=month, year=year)
    except Exception as e:
        logger.warning("Validation failed for get_budget_status: %s", e)
        return {"error": f"Validation error: {e}"}

    now = datetime.utcnow()
    target_month = validated.month or now.month
    target_year = validated.year or now.year

    try:
        rows = await db.fetch_budget_status(month=target_month, year=target_year)
        if not rows:
            return {
                "month": target_month,
                "year": target_year,
                "message": "No budgets set for this period.",
                "statuses": [],
            }
        return {
            "month": target_month,
            "year": target_year,
            "statuses": rows,
        }
    except Exception as e:
        logger.error("Database error in get_budget_status: %s", e)
        return {"error": f"Failed to get budget status: {e}"}
