"""
MCP tool implementations for budget management.

All tools use the module-level ``_DEFAULT_USER_ID`` for per-user scoping.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastmcp import Context

from models.schemas import CategoryEnum, GetBudgetStatusInput, SetBudgetInput
from db import database as db

logger = logging.getLogger("expense_tracker.tools.budgets")

# Module-level default user_id (set by main.py on startup)
_DEFAULT_USER_ID: int = 1


def set_default_user_id(uid: int) -> None:
    global _DEFAULT_USER_ID
    _DEFAULT_USER_ID = uid


# ---------------------------------------------------------------------------
# set_budget (with elicitation)
# ---------------------------------------------------------------------------

async def set_budget(
    category: str | None = None,
    limit_amount: float | None = None,
    month: int | None = None,
    year: int | None = None,
    ctx: Context | None = None,
) -> dict:
    """Set or update a monthly budget for a category.

    Args:
        category: One of Food, Travel, Bills, Entertainment, Health, Shopping, Education, Other.
        limit_amount: The budget limit amount (must be > 0).
        month: Month number (1-12).
        year: Year (2000-2100).
        ctx: MCP Context for elicitation (auto-injected).

    Returns:
        The created or updated budget record.
    """
    if ctx:
        if not category:
            cats = [c.value for c in CategoryEnum]
            result = await ctx.elicit(
                f"Which category? Choose from: {', '.join(cats)}", response_type=cats,
            )
            if result.action == "accept":
                category = result.data

        if not limit_amount:
            result = await ctx.elicit("What is the budget limit amount?", response_type=float)
            if result.action == "accept":
                limit_amount = result.data

        if not month:
            now = datetime.utcnow()
            result = await ctx.elicit(f"Which month? (1-12, default: {now.month})", response_type=int)
            month = result.data if result.action == "accept" else now.month

        if not year:
            now = datetime.utcnow()
            result = await ctx.elicit(f"Which year? (default: {now.year})", response_type=int)
            year = result.data if result.action == "accept" else now.year

    try:
        validated = SetBudgetInput(
            category=category, limit_amount=limit_amount, month=month, year=year,
        )
    except Exception as e:
        logger.warning("Validation failed for set_budget: %s", e)
        return {"error": f"Validation error: {e}"}

    try:
        record = await db.upsert_budget(
            user_id=_DEFAULT_USER_ID,
            category=validated.category.value,
            limit_amount=validated.limit_amount,
            month=validated.month,
            year=validated.year,
        )
        logger.info("Budget set: %s %s/%s → %.2f",
                     validated.category.value, validated.month, validated.year, validated.limit_amount)
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
        rows = await db.fetch_budget_status(
            user_id=_DEFAULT_USER_ID, month=target_month, year=target_year,
        )
        if not rows:
            return {
                "month": target_month, "year": target_year,
                "message": "No budgets set for this period.", "statuses": [],
            }
        return {"month": target_month, "year": target_year, "statuses": rows}
    except Exception as e:
        logger.error("Database error in get_budget_status: %s", e)
        return {"error": f"Failed to get budget status: {e}"}
