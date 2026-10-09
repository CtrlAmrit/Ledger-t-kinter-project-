# Ledger — Personal Finance Management System

Ledger is a local-first, database-backed desktop personal finance management application built in Python. Designed to provide genuine clarity into personal finances, Ledger tracks accounts, transactions, atomic transfers, category budgets, scheduled recurring transactions, financial milestones, and historical net worth with built-in analytics, CSV export, and publication-quality PDF reporting.

---

## 1. Project Overview

Ledger addresses the core personal finance workflow:
- **Where is my money?** Account ledger view with real-time balance tracking across Banks, Cash, Savings, and Credit Cards.
- **Where did it go?** Categorized transaction tracking, payee tracking, multi-column search, and category distribution donut charts.
- **Where is it going?** Monthly category budgets with threshold warning alerts, and automated recurring transaction templates.
- **Am I meeting my financial goals?** Progress tracking towards financial milestones with automated required monthly contribution calculation.
- **What is my overall standing?** Asset vs. liability balance calculation and net worth history over time.

---

## 2. Technology Stack

- **Core Language**: Python 3.12+ (tested on Python 3.12 / 3.14)
- **GUI Framework**: Tkinter & `ttk` with high-DPI scaling and custom modern Dark and Light themes
- **Database**: SQLite3 (`sqlite3` standard library module) with WAL journaling and strict foreign key constraints
- **Visualizations**: Matplotlib (embedded via `FigureCanvasTkAgg` and exported via `PdfPages`)
- **Testing**: `pytest`

### External Dependencies
Defined in `requirements.txt`:
```txt
matplotlib>=3.8.0
pytest>=8.0.0
```
*Note: `tkinter` and `sqlite3` are built into the standard Python installation and require no additional package manager dependencies.*

---

## 3. Architecture & Design Principles

Ledger uses a clean layered architecture that strictly separates user interface, business logic, calculations, and data persistence:

```text
Tkinter Desktop UI (ui.py)
         ↓
Service Layer (services.py)
         ↓
Pure Financial Calculations (calculations.py)
         ↓
Data Persistence Layer (database.py)
         ↓
SQLite Database (ledger.db)
```

### Architectural Boundaries
1. **Zero SQL in UI**: No UI component or widget directly runs SQL queries; all data operations go through the `FinanceService` facade.
2. **Zero Tkinter in Domain/Data**: `models.py`, `database.py`, and `calculations.py` have no knowledge of Tkinter widgets.
3. **Integer Money Storage**: Monetary values are stored and calculated strictly as integer **paise** (1 Rupee = 100 Paise). This eliminates floating-point rounding errors and non-deterministic totals. User input is validated and converted via `Decimal`.
4. **Atomic Transfers**: Transfers generate a pair of outflow and inflow transactions linked by a shared `transfer_group_id`. Transfers are executed in an atomic transaction; deleting or modifying either side updates both accounts and neither side affects income or expense reports.
5. **Duplicate-Resistant Recurring Transactions**: Recurring templates evaluate due dates and generate real transactions with audit tags preventing duplicate generation upon repeated triggers.

---

## 4. Object-Oriented Programming (OOP) Implementation

The application is structured to clearly demonstrate core OOP principles for academic evaluation and oral examination (viva):

### A. Encapsulation
- **Domain Models (`models.py`)**: `Account`, `Transaction`, `Budget`, `RecurringTransaction`, `FinancialGoal`, `GoalContribution`, and `Category` encapsulate their attributes, validation logic, and domain properties (e.g. `Account.is_liability`, `RecurringTransaction.is_due()`, `RecurringTransaction.calculate_next_date()`, `Transaction.formatted_amount`).
- **Database (`database.py`)**: `Database` class encapsulates SQLite connection pooling, WAL mode pragmas, schema migrations, and safe backup operations behind clean context managers.

### B. Abstraction & Facade Pattern
- **`FinanceService` (`services.py`)**: Acts as a unified Facade coordinating `AccountService`, `TransactionService`, `BudgetService`, `RecurringService`, `GoalService`, `AnalyticsService`, and `DemoDataService`. The UI interacts solely with this clean high-level interface.
- **`LedgerCharts` (`charts.py`)**: Abstracted Matplotlib canvas rendering functions that handle figure lifecycle, memory management, and dark/light styling cleanly.

### C. Inheritance & Polymorphism
- **`BasePage` (`ui.py`)**: Extends `ttk.Frame` and establishes a polymorphic interface (`refresh()`, `theme`) implemented by all 8 pages (`DashboardPage`, `TransactionsPage`, `AccountsPage`, `BudgetsPage`, `RecurringPage`, `GoalsPage`, `ReportsPage`, `SettingsPage`).
- **Modal Dialogs**: `TransactionDialog`, `AccountDialog`, `BudgetDialog`, `RecurringDialog`, `GoalDialog`, and `ContributionDialog` inherit from `tk.Toplevel` and standardize modal grabs, keyboard shortcuts, and form lifecycle.

---

## 5. Project File Structure

```text
Ledger/
│
├── main.py                 # Application entry point and high-DPI initialization
├── database.py             # SQLite connection, schema creation, seed categories, WAL mode
├── models.py               # Domain model classes and entity dataclasses
├── services.py             # Business logic, service layer, and demo dataset manager
├── calculations.py         # Pure financial formulas, integer paise math, currency formatting
├── ui.py                   # Desktop GUI shell, 8 application views, and modal dialogs
├── charts.py               # Embedded Matplotlib figures with dark/light themes
├── export.py               # CSV export and multi-section PDF report generation
├── requirements.txt        # External dependencies (matplotlib, pytest)
├── pytest.ini             # Pytest test discovery and Python path configuration
├── README.md               # Complete project documentation
├── .gitignore              # Git exclusions for cache, local database, and test artifacts
│
└── tests/
    ├── test_calculations.py # Unit tests for financial formulas, conversions, edge cases
    ├── test_transactions.py # Integration tests for accounts, transfers, budgets, recurring
    └── test_ui.py           # Automated headless smoke tests for GUI navigation and dialogs
```

---

## 6. Database Schema

Managed automatically by `database.py`:

```sql
accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    account_type TEXT NOT NULL,
    opening_balance_paise INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE,
    category_type TEXT NOT NULL CHECK(category_type IN ('income', 'expense')),
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(name, category_type)
);

merchants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    merchant_id INTEGER REFERENCES merchants(id) ON DELETE SET NULL,
    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('income', 'expense', 'transfer')),
    transaction_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    transfer_group_id TEXT,
    created_at TEXT NOT NULL
);

budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    limit_paise INTEGER NOT NULL CHECK(limit_paise >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(month, category_id)
);

recurring_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    merchant_id INTEGER REFERENCES merchants(id) ON DELETE SET NULL,
    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('income', 'expense')),
    frequency TEXT NOT NULL CHECK(frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
    next_run_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1
);

financial_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    target_amount_paise INTEGER NOT NULL CHECK(target_amount_paise > 0),
    target_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

goal_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
    contribution_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
```

Indexes are created on `transactions(transaction_date)`, `transactions(account_id)`, `transactions(category_id)`, `transactions(transfer_group_id)`, and `budgets(month)` for sub-millisecond lookups.

---

## 7. Setup & Installation

### Step 1: Clone or Open Workspace
Ensure you are in the project root directory:
```bash
cd Ledger
```

### Step 2: Install Dependencies
Install the required packages using pip:
```bash
pip install -r requirements.txt
```

---

## 8. Running the Application

### Normal Launch (Empty database with default categories)
```bash
python main.py
```

### Demonstration Launch (With sample dataset)
To launch with sample realistic bank accounts, multi-month transactions, budgets, recurring items, and goals:
```bash
python main.py --demo
```

### In-App Demo Data Controls
You can also load or cleanly wipe demo data at any time from inside the application:
1. Open the **Settings** tab in the sidebar.
2. Click **Load Demo Dataset** to seed realistic data.
3. Click **Clear All Data** to reset the database.

---

## 9. Keyboard Shortcuts

- `Ctrl + N`: Open New Transaction dialog
- `Ctrl + F`: Jump to Transactions page and focus the search box
- `Esc`: Dismiss active modal dialog

---

## 10. Running the Test Suite

Run the full automated test suite via `pytest`:
```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

### Test Coverage Highlights
- **`tests/test_calculations.py`**:
  - Rupee to integer paise conversions (handles floats, strings with commas and symbols, Decimals, negative values)
  - Indian numbering currency formatting (`₹12,34,567.89`)
  - Savings rate formulas including edge cases (zero income, expenses > income)
  - Budget calculations (on-track, >=80% warning threshold, >=100% exceeded)
  - Net worth asset vs. liability computation
  - Goal metrics and required monthly savings rate calculation
- **`tests/test_transactions.py`**:
  - Account balance integrity
  - Atomic two-sided transfer creation (balances update correctly, net worth unaffected, zero impact on income/expense reporting)
  - Transfer deletion pair integrity (both sides deleted simultaneously)
  - Monthly budget calculations excluding transfers
  - Recurring transaction due processing and duplicate prevention
  - Demo data seeding and clean reset
  - Filtered CSV transaction export and Matplotlib PDF generation
- **`tests/test_ui.py`**:
  - Headless instantiation of the Tkinter application shell
  - Seamless navigation across all 8 views
  - Dark/Light theme switching
  - Construction and destruction of all modal dialogs

---

## 11. Academic / Viva Explanation Guide

For presentations and viva evaluations, key topics to highlight:

1. **Why SQLite rather than client-server SQL?**
   - Personal finance is local-first and privacy-centric. Single-user desktop applications do not require a separate database daemon or network overhead. SQLite provides ACID compliance, WAL journaling, zero setup, and portability.
2. **Why integer paise instead of floating-point numbers?**
   - Floating-point representations (IEEE 754) produce binary approximation errors (e.g. `0.1 + 0.2 = 0.30000000000000004`). In finance, every fraction of a cent or paisa matters. Converting rupees to integer paise guarantees deterministic, lossless arithmetic.
3. **How does transfer accounting work?**
   - Transfers represent movement between assets, not revenue or expense. A transfer from Bank to Cash generates two linked records sharing a `transfer_group_id`. Reporting queries filter for `transaction_type IN ('income', 'expense')`, ensuring cashflow totals and net worth remain strictly accurate.
4. **How are recurring transactions prevented from duplicating?**
   - Before executing a recurring schedule, `RecurringService` queries existing records for an audit signature (`[Recurring #ID]` in notes on that execution date). If already processed, it simply advances the `next_run_date` without inserting redundant transactions.
