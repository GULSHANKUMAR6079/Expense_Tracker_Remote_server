"""
Pydantic v2 schemas for the Expense Tracker MCP server.

Defines all input/output models and the CategoryEnum used across
tools and resources.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------

class CategoryEnum(str, Enum):
    """Allowed expense categories."""
    FOOD = "Food"
    TRAVEL = "Travel"
    BILLS = "Bills"
    ENTERTAINMENT = "Entertainment"
    HEALTH = "Health"
    SHOPPING = "Shopping"
    EDUCATION = "Education"
    OTHER = "Other"


# ---------------------------------------------------------------------------
# Tool INPUT models
# ---------------------------------------------------------------------------

class AddExpenseInput(BaseModel):
    """Input for add_expense tool."""
    title: str = Field(..., min_length=1, max_length=200, description="Expense title")
    amount: float = Field(..., gt=0, description="Expense amount (must be positive)")
    category: CategoryEnum = Field(..., description="Expense category")
    date: str = Field(..., description="Expense date in YYYY-MM-DD format")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be in YYYY-MM-DD format")
        return v


class GetExpensesInput(BaseModel):
    """Input for get_expenses tool."""
    category: Optional[CategoryEnum] = Field(None, description="Filter by category")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    limit: Optional[int] = Field(50, ge=1, le=500, description="Max results to return")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("date must be in YYYY-MM-DD format")
        return v


class UpdateExpenseInput(BaseModel):
    """Input for update_expense tool."""
    id: int = Field(..., gt=0, description="Expense ID to update")
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="New title")
    amount: Optional[float] = Field(None, gt=0, description="New amount")
    category: Optional[CategoryEnum] = Field(None, description="New category")
    date: Optional[str] = Field(None, description="New date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, max_length=500, description="New notes")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("date must be in YYYY-MM-DD format")
        return v


class DeleteExpenseInput(BaseModel):
    """Input for delete_expense tool."""
    id: int = Field(..., gt=0, description="Expense ID to delete")


class GetSummaryInput(BaseModel):
    """Input for get_summary tool."""
    period: Optional[str] = Field(
        "monthly",
        description="Summary period: 'weekly', 'monthly', or 'all'",
    )

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"weekly", "monthly", "all"}
        if v is not None and v not in allowed:
            raise ValueError(f"period must be one of {allowed}")
        return v


class SetBudgetInput(BaseModel):
    """Input for set_budget tool."""
    category: CategoryEnum = Field(..., description="Budget category")
    limit_amount: float = Field(..., gt=0, description="Monthly budget limit")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2000, le=2100, description="Year")


class GetBudgetStatusInput(BaseModel):
    """Input for get_budget_status tool."""
    month: Optional[int] = Field(None, ge=1, le=12, description="Month (1-12)")
    year: Optional[int] = Field(None, ge=2000, le=2100, description="Year")


class GetTopExpensesInput(BaseModel):
    """Input for get_top_expenses tool."""
    n: Optional[int] = Field(5, ge=1, le=100, description="Number of top expenses")


# ---------------------------------------------------------------------------
# Tool OUTPUT / Record models
# ---------------------------------------------------------------------------

class ExpenseRecord(BaseModel):
    """Represents a single expense row."""
    id: int
    title: str
    amount: float
    category: str
    date: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class BudgetRecord(BaseModel):
    """Represents a single budget row."""
    id: int
    category: str
    limit_amount: float
    month: int
    year: int


class SpendingSummary(BaseModel):
    """Aggregated spending for one category."""
    category: str
    total_spent: float
    transaction_count: int


class BudgetStatusItem(BaseModel):
    """Budget vs actual spending for one category."""
    category: str
    limit_amount: float
    total_spent: float
    remaining: float
    percentage_used: float
