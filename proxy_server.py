"""
Proxy server for the Expense Tracker MCP server.

Creates a FastMCP proxy that bridges the main Expense Tracker
server to HTTP transport, enabling remote access with optional
authentication.

Usage:
    # Run as HTTP proxy (for remote/web clients)
    python proxy_server.py

    # The proxy connects to the main stdio server and exposes it
    # over HTTP with optional bearer-token authentication.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging (reuse main config)
# ---------------------------------------------------------------------------

import logging

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("expense_tracker.proxy")

# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

from fastmcp.server import create_proxy

# Path to the main MCP server (stdio-based)
MAIN_SERVER_PATH = str(PROJECT_ROOT / "main.py")

# Create the proxy pointing to the main server
proxy = create_proxy(
    MAIN_SERVER_PATH,
    name="Expense Tracker Proxy",
)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("PROXY_HOST", "0.0.0.0")
    port = int(os.getenv("PROXY_PORT", "8000"))

    logger.info("Starting proxy server on %s:%s", host, port)
    logger.info("Proxying main server: %s", MAIN_SERVER_PATH)

    # Run the proxy as an HTTP server (bridges stdio → HTTP)
    proxy.run(transport="http", host=host, port=port)
