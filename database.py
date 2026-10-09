"""
database.py - SQLite Database Management for Ledger.

Handles:
- SQLite connection pooling / safe context managers
- Schema initialization with proper constraints & indexes
- Foreign key enforcement (PRAGMA foreign_keys = ON)
- Default categories seeding
- Safe online database backup via SQLite backup API
"""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
import sqlite3
from typing import Generator, Any, Sequence


DEFAULT_DB_PATH = "ledger.db"

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    # Expense categories
    ("Food & Dining", "expense"),
    ("Groceries", "expense"),
    ("Transportation", "expense"),
    ("Shopping", "expense"),
    ("Housing & Rent", "expense"),
    ("Utilities & Bills", "expense"),
    ("Education", "expense"),
    ("Healthcare", "expense"),
    ("Entertainment", "expense"),
    ("Personal Care", "expense"),
    ("Travel", "expense"),
    ("Other Expense", "expense"),
    # Income categories
    ("Salary", "income"),
    ("Scholarship / Stipend", "income"),
    ("Freelance / Consulting", "income"),
    ("Investments & Dividends", "income"),
    ("Gift & Grants", "income"),
    ("Refunds / Cashbacks", "income"),
    ("Other Income", "income"),
]


class Database:
    """
    Manages SQLite database lifecycle, schema migrations, and transactions.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # Ensure parent directory exists if nested
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a SQLite connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        Context manager for atomic database transactions.
        Commits on normal exit, rolls back automatically on error.
        """
        conn = self.get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                yield cursor
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Execute a single write query with autocommit."""
        with self.transaction() as cur:
            cur.execute(sql, params)
            return cur

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Execute a read query and return all rows."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        """Execute a read query and return a single row or None."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Create all tables, constraints, indexes, and seed default categories."""
        conn = self.get_connection()
        try:
            with conn:
                cur = conn.cursor()

                # 1. Accounts Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        account_type TEXT NOT NULL,
                        opening_balance_paise INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    );
                """)

                # 2. Categories Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL COLLATE NOCASE,
                        category_type TEXT NOT NULL CHECK(category_type IN ('income', 'expense')),
                        is_active INTEGER NOT NULL DEFAULT 1,
                        UNIQUE(name, category_type)
                    );
                """)

                # 3. Merchants Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS merchants (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE COLLATE NOCASE
                    );
                """)

                # 4. Transactions Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
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
                """)

                # 5. Budgets Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS budgets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        month TEXT NOT NULL,
                        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                        limit_paise INTEGER NOT NULL CHECK(limit_paise >= 0),
                        created_at TEXT NOT NULL,
                        UNIQUE(month, category_id)
                    );
                """)

                # 6. Recurring Transactions Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS recurring_transactions (
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
                """)

                # 7. Financial Goals Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS financial_goals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        target_amount_paise INTEGER NOT NULL CHECK(target_amount_paise > 0),
                        target_date TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    );
                """)

                # 8. Goal Contributions Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS goal_contributions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        goal_id INTEGER NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
                        amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
                        contribution_date TEXT NOT NULL,
                        note TEXT NOT NULL DEFAULT ''
                    );
                """)

                # Performance Indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_date ON transactions(transaction_date);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_account ON transactions(account_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_category ON transactions(category_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_transfer ON transactions(transfer_group_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_recurring_run ON recurring_transactions(next_run_date, is_active);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_contributions_goal ON goal_contributions(goal_id);")

                # Seed default categories if none exist
                cur.execute("SELECT COUNT(*) FROM categories;")
                count = cur.fetchone()[0]
                if count == 0:
                    cur.executemany(
                        "INSERT OR IGNORE INTO categories (name, category_type) VALUES (?, ?);",
                        DEFAULT_CATEGORIES
                    )
        finally:
            conn.close()

    def backup(self, destination_path: str) -> str:
        """
        Creates an online, atomic backup of the database to destination_path.
        Safe against concurrent writes.
        """
        dest_dir = os.path.dirname(os.path.abspath(destination_path))
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        source_conn = self.get_connection()
        try:
            dest_conn = sqlite3.connect(destination_path)
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()
        return destination_path
