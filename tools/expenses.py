"""
MCP tool implementations for expense management.

Uses FastMCP Context for elicitation — if a required field is missing,
the server prompts the user interactively before proceeding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastmcp import Context

from models.schemas import (
    AddExpenseInput,
    CategoryEnum,
    DeleteExpenseInput,
    GetExpensesInput,
    GetSummaryInput,
    GetTopExpensesInput,
    UpdateExpenseInput,
)
from db import database as db

logger = logging.getLogger("expense_tracker.tools.expenses")


# ---------------------------------------------------------------------------
# Elicitation helpers
# ---------------------------------------------------------------------------

@dataclass
class ConfirmDelete:
    """Elicitation schema for delete confirmation."""
    confirm: str


async def _elicit_missing_fields(
    ctx: Context,
    title: str | None,
    amount: float | None,
    category: str | None,
    date: str | None,
) -> tuple[str | None, float | None, str | None, str | None]:
    """Prompt the user for any missing required expense fields via elicitation."""
    if not title:
        result = await ctx.elicit("What is the expense title?", response_type=str)
        if result.action == "accept":
            title = result.data

    if not amount:
        result = await ctx.elicit("What is the expense amount?", response_type=float)
        if result.action == "accept":
            amount = result.data

    if not category:
        cats = [c.value for c in CategoryEnum]
        result = await ctx.elicit(
            f"Choose a category: {', '.join(cats)}",
            response_type=cats,
        )
        if result.action == "accept":
            category = result.data

    if not date:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        result = await ctx.elicit(
            f"What date? (YYYY-MM-DD, default: {today})",
            response_type=str,
        )
        if result.action == "accept":
            date = result.data or today
        else:
            date = today

    return title, amount, category, date


# ---------------------------------------------------------------------------
# add_expense
# ---------------------------------------------------------------------------

async def add_expense(
    title: str,
    amount: float,
    category: str,
    date: str,
    notes: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Add a new expense record.

    Args:
        title: Expense title (1-200 chars).
        amount: Expense amount (must be > 0).
        category: One of Food, Travel, Bills, Entertainment, Health, Shopping, Education, Other.
        date: Expense date in YYYY-MM-DD format.
        notes: Optional notes (max 500 chars).
        ctx: MCP Context for elicitation (auto-injected).

    Returns:
        The created expense record with its new ID.
    """
    # Elicit missing required fields if context is available
    if ctx and (not title or not amount or not category or not date):
        title, amount, category, date = await _elicit_missing_fields(
            ctx, title, amount, category, date
        )

    try:
        validated = AddExpenseInput(
            title=title,
            amount=amount,
            category=category,
            date=date,
            notes=notes,
        )
    except Exception as e:
        logger.warning("Validation failed for add_expense: %s", e)
        return {"error": f"Validation error: {e}"}

    try:
        record = await db.insert_expense(
            title=validated.title,
            amount=validated.amount,
            category=validated.category.value,
            date=validated.date,
            notes=validated.notes,
        )
        logger.info("Added expense #%s: %s", record["id"], validated.title)
        return {"message": "Expense added successfully.", "expense": record}
    except Exception as e:
        logger.error("Database error in add_expense: %s", e)
        return {"error": f"Failed to add expense: {e}"}


# ---------------------------------------------------------------------------
# get_expenses
# ---------------------------------------------------------------------------

async def get_expenses(
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = 50,
) -> dict:
    """List expenses with optional filters.

    Args:
        category: Filter by category (optional).
        start_date: Start date filter YYYY-MM-DD (optional).
        end_date: End date filter YYYY-MM-DD (optional).
        limit: Maximum number of results (1-500, default 50).

    Returns:
        A dict with the list of matching expenses and the count.
    """
    try:
        validated = GetExpensesInput(
            category=category,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except Exception as e:
        logger.warning("Validation failed for get_expenses: %s", e)
        return {"error": f"Validation error: {e}"}

    try:
        rows = await db.fetch_expenses(
            category=validated.category.value if validated.category else None,
            start_date=validated.start_date,
            end_date=validated.end_date,
            limit=validated.limit or 50,
        )
        return {"count": len(rows), "expenses": rows}
    except Exception as e:
        logger.error("Database error in get_expenses: %s", e)
        return {"error": f"Failed to fetch expenses: {e}"}


# ---------------------------------------------------------------------------
# update_expense
# ---------------------------------------------------------------------------

async def update_expense(
    id: int,
    title: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    date: str | None = None,
    notes: str | None = None,
) -> dict:
    """Update an existing expense by ID.

    Args:
        id: The expense ID to update.
        title: New title (optional).
        amount: New amount (optional).
        category: New category (optional).
        date: New date YYYY-MM-DD (optional).
        notes: New notes (optional).

    Returns:
        The updated expense record, or an error if not found.
    """
    try:
        validated = UpdateExpenseInput(
            id=id,
            title=title,
            amount=amount,
            category=category,
            date=date,
            notes=notes,
        )
    except Exception as e:
        logger.warning("Validation failed for update_expense: %s", e)
        return {"error": f"Validation error: {e}"}

    existing = await db.fetch_expense_by_id(validated.id)
    if not existing:
        return {"error": f"Expense with ID {validated.id} not found."}

    fields: dict = {}
    if validated.title is not None:
        fields["title"] = validated.title
    if validated.amount is not None:
        fields["amount"] = validated.amount
    if validated.category is not None:
        fields["category"] = validated.category.value
    if validated.date is not None:
        fields["date"] = validated.date
    if validated.notes is not None:
        fields["notes"] = validated.notes

    if not fields:
        return {"message": "No fields to update.", "expense": existing}

    try:
        updated = await db.update_expense(validated.id, **fields)
        logger.info("Updated expense #%s", validated.id)
        return {"message": "Expense updated successfully.", "expense": updated}
    except Exception as e:
        logger.error("Database error in update_expense: %s", e)
        return {"error": f"Failed to update expense: {e}"}


# ---------------------------------------------------------------------------
# delete_expense (with elicitation confirmation)
# ---------------------------------------------------------------------------

async def delete_expense(id: int, ctx: Context | None = None) -> dict:
    """Delete an expense by ID.

    Args:
        id: The expense ID to delete.
        ctx: MCP Context for elicitation (auto-injected).

    Returns:
        Success or not-found message.
    """
    try:
        validated = DeleteExpenseInput(id=id)
    except Exception as e:
        logger.warning("Validation failed for delete_expense: %s", e)
        return {"error": f"Validation error: {e}"}

    # Confirm deletion with the user via elicitation
    if ctx:
        existing = await db.fetch_expense_by_id(validated.id)
        if not existing:
            return {"error": f"Expense with ID {validated.id} not found."}

        result = await ctx.elicit(
            f"Are you sure you want to delete expense #{validated.id} "
            f"'{existing.get('title', '')}' (₹{existing.get('amount', 0)})? "
            f"Type 'yes' to confirm.",
            response_type=["yes", "no"],
        )
        if result.action != "accept" or result.data != "yes":
            return {"message": "Deletion cancelled by user."}

    try:
        deleted = await db.delete_expense(validated.id)
        if deleted:
            logger.info("Deleted expense #%s", validated.id)
            return {"message": f"Expense #{validated.id} deleted successfully."}
        else:
            return {"error": f"Expense with ID {validated.id} not found."}
    except Exception as e:
        logger.error("Database error in delete_expense: %s", e)
        return {"error": f"Failed to delete expense: {e}"}


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------

async def get_summary(period: str | None = "monthly") -> dict:
    """Get a spending summary grouped by category.

    Args:
        period: One of 'weekly', 'monthly', or 'all' (default: 'monthly').

    Returns:
        Summary with total amount, period info, and per-category breakdown.
    """
    try:
        validated = GetSummaryInput(period=period)
    except Exception as e:
        logger.warning("Validation failed for get_summary: %s", e)
        return {"error": f"Validation error: {e}"}

    today = datetime.utcnow().date()
    start_date: str | None = None
    end_date: str | None = None

    if validated.period == "weekly":
        start = today - timedelta(days=today.weekday())
        start_date = start.isoformat()
        end_date = today.isoformat()
    elif validated.period == "monthly":
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()

    try:
        rows = await db.fetch_spending_summary(start_date=start_date, end_date=end_date)
        grand_total = sum(r["total_spent"] for r in rows)
        return {
            "period": validated.period,
            "start_date": start_date,
            "end_date": end_date,
            "grand_total": round(grand_total, 2),
            "categories": rows,
        }
    except Exception as e:
        logger.error("Database error in get_summary: %s", e)
        return {"error": f"Failed to get summary: {e}"}


# ---------------------------------------------------------------------------
# get_top_expenses
# ---------------------------------------------------------------------------

async def get_top_expenses(n: int | None = 5) -> dict:
    """Get the top N highest expenses.

    Args:
        n: Number of top expenses to return (1-100, default 5).

    Returns:
        List of top expenses ordered by amount descending.
    """
    try:
        validated = GetTopExpensesInput(n=n)
    except Exception as e:
        logger.warning("Validation failed for get_top_expenses: %s", e)
        return {"error": f"Validation error: {e}"}

    try:
        rows = await db.fetch_top_expenses(validated.n or 5)
        return {"count": len(rows), "expenses": rows}
    except Exception as e:
        logger.error("Database error in get_top_expenses: %s", e)
        return {"error": f"Failed to get top expenses: {e}"}
