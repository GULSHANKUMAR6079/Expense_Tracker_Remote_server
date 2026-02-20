# 💰 Expense Tracker MCP Server

A **production-level** Model Context Protocol (MCP) server for managing personal expenses and budgets, built with **FastMCP**, **MySQL**, and **Pydantic v2**.

Connect it to **Claude Desktop** and manage your finances through natural language!

---

## ✨ Features

| Area | Capabilities |
|------|-------------|
| **Expenses** | Add, list (with filters), update, delete expenses |
| **Budgets** | Set monthly budgets per category, compare budget vs actual |
| **Summaries** | Weekly / monthly / all-time spending breakdowns |
| **Resources** | Read-only data views via MCP resource URIs |
| **Validation** | All inputs validated with Pydantic v2 |
| **Logging** | Dual logging — console + `logs/app.log` |

### Supported Categories

`Food` · `Travel` · `Bills` · `Entertainment` · `Health` · `Shopping` · `Education` · `Other`

---

## 📁 Project Structure

```
expense-mcp/
├── main.py                  # Entry point — FastMCP server
├── db/
│   ├── __init__.py
│   └── database.py          # MySQL async database layer
├── tools/
│   ├── __init__.py
│   ├── expenses.py          # Expense CRUD tools
│   └── budgets.py           # Budget tools
├── resources/
│   ├── __init__.py
│   └── expense_resources.py # MCP resource endpoints
├── models/
│   ├── __init__.py
│   └── schemas.py           # Pydantic v2 models
├── logs/
│   └── app.log              # Auto-created at runtime
├── .env                     # Local config (do NOT commit)
├── .env.example             # Config template
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **MySQL 8.0+** running locally (or a remote instance)

### 2. Clone & Install

```bash
cd expense-mcp

# Create a virtual environment (recommended)
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure MySQL

1. Copy the example env file and edit it:

```bash
cp .env.example .env
```

1. Update `.env` with your MySQL credentials:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=expense_tracker
LOG_LEVEL=INFO
```

> **Note:** The server will **auto-create** the `expense_tracker` database and all tables on first run!

### 4. Run the Server

```bash
python main.py
```

The server starts in **stdio** mode and waits for a MCP client (e.g. Claude Desktop) to connect.

---

## 🔗 Connect to Claude Desktop

Add the following to your Claude Desktop configuration file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "python",
      "args": ["C:/Users/gulsh/MCP/MCP_PROJECT/expense-mcp/main.py"]
    }
  }
}
```

> ⚠️ **Adjust the path** to match your actual project location. Use absolute paths.

Restart Claude Desktop after saving the config.

---

## 🛠️ Available MCP Tools

| Tool | Description |
|------|-------------|
| `add_expense(title, amount, category, date, notes?)` | Add a new expense |
| `get_expenses(category?, start_date?, end_date?, limit?)` | List expenses with filters |
| `update_expense(id, title?, amount?, category?, date?, notes?)` | Update an expense |
| `delete_expense(id)` | Delete an expense by ID |
| `get_summary(period?)` | Spending summary (weekly / monthly / all) |
| `get_top_expenses(n?)` | Top N highest expenses |
| `set_budget(category, limit_amount, month, year)` | Set a monthly budget |
| `get_budget_status(month?, year?)` | Budget vs actual spending |

## 📚 Available MCP Resources

| URI | Description |
|-----|-------------|
| `expense://all` | All expenses as a formatted list |
| `expense://summary` | Current month's spending summary |
| `expense://categories` | All unique categories used |
| `budget://status` | Current budget vs actual for all categories |

---

## 🗄️ Database Schema

### `expenses` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT (PK, AUTO_INCREMENT) | Unique ID |
| `title` | VARCHAR(200) | Expense title |
| `amount` | DECIMAL(12,2) | Amount spent |
| `category` | VARCHAR(50) | Category name |
| `date` | DATE | Expense date |
| `notes` | VARCHAR(500) | Optional notes |
| `created_at` | DATETIME | Record creation time |
| `updated_at` | DATETIME | Last update time |

### `budgets` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT (PK, AUTO_INCREMENT) | Unique ID |
| `category` | VARCHAR(50) | Category name |
| `limit_amount` | DECIMAL(12,2) | Monthly budget limit |
| `month` | INT | Month (1-12) |
| `year` | INT | Year |

---

## 💡 Example Prompts for Claude

Once connected, try asking Claude:

- *"Add an expense: ₹500 for lunch under Food on 2026-02-20"*
- *"Show me all my expenses this month"*
- *"Set a budget of ₹5000 for Food in February 2026"*
- *"How much have I spent vs my budget this month?"*
- *"What are my top 5 most expensive purchases?"*
- *"Give me a weekly spending summary"*

---

## 📝 License

MIT — use freely for personal and commercial projects.
