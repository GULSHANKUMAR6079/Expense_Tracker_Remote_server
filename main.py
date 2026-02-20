"""
Expense Tracker — FastMCP Server (main entry-point)

Runs as a local **stdio** MCP server by default.
For HTTP access use the companion ``proxy_server.py``.

Features:
  • 8 MCP tools (expense + budget CRUD)
  • 4 MCP resources (read-only views)
  • Multi-user support via API-key authentication
  • Interactive elicitation for missing fields
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap — env + sys.path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Set up console + optional file logging."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(log_level)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(ch)

    for log_path in [PROJECT_ROOT / "logs", Path("/tmp")]:
        try:
            log_path.mkdir(exist_ok=True)
            fh = logging.FileHandler(log_path / "app.log", encoding="utf-8")
            fh.setLevel(log_level)
            fh.setFormatter(fmt)
            root.addHandler(fh)
            break
        except OSError:
            continue


_configure_logging()
logger = logging.getLogger("expense_tracker")

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

from fastmcp import FastMCP

mcp = FastMCP(
    name="Expense Tracker",
    instructions=(
        "A personal expense tracking assistant.\n\n"
        "TOOLS:\n"
        "  • add_expense     — record a new expense\n"
        "  • get_expenses    — list / filter expenses\n"
        "  • update_expense  — edit an expense by ID\n"
        "  • delete_expense  — remove an expense (with confirmation)\n"
        "  • get_summary     — spending summary by category\n"
        "  • get_top_expenses— highest expenses\n"
        "  • set_budget      — set a monthly budget per category\n"
        "  • get_budget_status— compare budget vs actual\n"
        "  • register_user   — create a new user (returns API key)\n"
        "  • switch_user     — switch active user by API key\n"
        "  • list_users      — list all registered users\n\n"
        "RESOURCES (read-only):\n"
        "  expense://all, expense://summary,\n"
        "  expense://categories, budget://status"
    ),
)

# ---------------------------------------------------------------------------
# Imports — tools, resources, db
# ---------------------------------------------------------------------------

from db.database import init_db, create_user, authenticate_user, list_users as db_list_users
from tools.expenses import (
    add_expense, get_expenses, update_expense, delete_expense,
    get_summary, get_top_expenses,
    set_default_user_id as set_expense_user_id,
)
from tools.budgets import (
    set_budget, get_budget_status,
    set_default_user_id as set_budget_user_id,
)
from resources.expense_resources import (
    get_all_expenses, get_expense_summary, get_categories,
    get_budget_status_resource,
    set_default_user_id as set_resource_user_id,
)


def _set_active_user(user_id: int) -> None:
    """Propagate the active user_id to all modules."""
    set_expense_user_id(user_id)
    set_budget_user_id(user_id)
    set_resource_user_id(user_id)


# ---------------------------------------------------------------------------
# Register expense & budget tools
# ---------------------------------------------------------------------------

mcp.tool()(add_expense)
mcp.tool()(get_expenses)
mcp.tool()(update_expense)
mcp.tool()(delete_expense)
mcp.tool()(get_summary)
mcp.tool()(get_top_expenses)
mcp.tool()(set_budget)
mcp.tool()(get_budget_status)

# ---------------------------------------------------------------------------
# User management tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def register_user(name: str, email: str | None = None) -> dict:
    """Register a new user and receive their unique API key.

    Args:
        name: User's display name.
        email: Optional email address.

    Returns:
        The new user record with their API key. Save this key!
    """
    try:
        user = await create_user(name=name, email=email)
        logger.info("Registered new user: %s (id=%s)", name, user["id"])
        return {
            "message": f"User '{name}' registered successfully!",
            "user": user,
            "note": "Save your API key — you'll need it to switch users.",
        }
    except Exception as e:
        logger.error("Failed to register user: %s", e)
        return {"error": f"Failed to register user: {e}"}


@mcp.tool()
async def switch_user(api_key: str) -> dict:
    """Switch the active user by providing an API key.

    Args:
        api_key: The user's API key received during registration.

    Returns:
        Confirmation with user details, or error if the key is invalid.
    """
    user = await authenticate_user(api_key)
    if not user:
        return {"error": "Invalid API key. Use register_user to create an account."}

    _set_active_user(user["id"])
    logger.info("Switched to user: %s (id=%s)", user["name"], user["id"])
    return {
        "message": f"Switched to user '{user['name']}'.",
        "user": {"id": user["id"], "name": user["name"], "email": user.get("email")},
    }


@mcp.tool()
async def list_users() -> dict:
    """List all registered users (API keys are hidden).

    Returns:
        List of users with their ID, name, email, and creation date.
    """
    try:
        users = await db_list_users()
        return {"count": len(users), "users": users}
    except Exception as e:
        logger.error("Failed to list users: %s", e)
        return {"error": f"Failed to list users: {e}"}


# ---------------------------------------------------------------------------
# Register resources
# ---------------------------------------------------------------------------

mcp.resource("expense://all")(get_all_expenses)
mcp.resource("expense://summary")(get_expense_summary)
mcp.resource("expense://categories")(get_categories)
mcp.resource("budget://status")(get_budget_status_resource)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Initialising database ...")
    asyncio.run(init_db())

    # Set default user to user #1 (auto-created on first run)
    _set_active_user(1)

    logger.info("Starting Expense Tracker MCP server (stdio) ...")
    mcp.run()
