"""
Expense Tracker MCP Server — main entry point.

Creates a FastMCP server instance, registers all tools and resources,
configures logging, initialises the MySQL database, and exposes the
server over stdio transport for Claude Desktop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Bootstrap — load .env and fix sys.path so local packages resolve
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Set up dual logging: console + logs/app.log."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(fmt)

    # Console handler (stderr so it doesn't interfere with stdio transport)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(log_level)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(fh)
    root.addHandler(ch)


_configure_logging()
logger = logging.getLogger("expense_tracker")

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Expense Tracker",
    instructions=(
        "A production-level MCP server for tracking personal expenses, "
        "managing budgets, and generating spending summaries. "
        "Backed by a MySQL database."
    ),
)

# ---------------------------------------------------------------------------
# Register Tools — Expenses
# ---------------------------------------------------------------------------

from tools.expenses import (          # noqa: E402
    add_expense,
    delete_expense,
    get_expenses,
    get_summary,
    get_top_expenses,
    update_expense,
)

mcp.tool()(add_expense)
mcp.tool()(get_expenses)
mcp.tool()(update_expense)
mcp.tool()(delete_expense)
mcp.tool()(get_summary)
mcp.tool()(get_top_expenses)

# ---------------------------------------------------------------------------
# Register Tools — Budgets
# ---------------------------------------------------------------------------

from tools.budgets import get_budget_status, set_budget  # noqa: E402

mcp.tool()(set_budget)
mcp.tool()(get_budget_status)

# ---------------------------------------------------------------------------
# Register Resources
# ---------------------------------------------------------------------------

from resources.expense_resources import (  # noqa: E402
    get_all_expenses,
    get_budget_status_resource,
    get_categories,
    get_expense_summary,
)

mcp.resource("expense://all")(get_all_expenses)
mcp.resource("expense://summary")(get_expense_summary)
mcp.resource("expense://categories")(get_categories)
mcp.resource("budget://status")(get_budget_status_resource)

# ---------------------------------------------------------------------------
# Startup — initialise database then run server
# ---------------------------------------------------------------------------

from db.database import init_db  # noqa: E402


if __name__ == "__main__":
    logger.info("Launching Expense Tracker MCP server (stdio transport)…")
    # Ensure database is initialised before the server starts listening
    asyncio.run(init_db())
    mcp.run(transport="stdio")
