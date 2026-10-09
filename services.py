"""
services.py - Business Logic & Service Layer for Ledger.

Coordinates CRUD operations, atomic transfers, recurring processing,
budget tracking, and analytics without coupling to Tkinter UI or raw SQL in views.
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
import calendar
import sqlite3
from typing import Optional, Sequence
import uuid

from calculations import (
    calculate_budget_usage,
    calculate_goal_metrics,
    calculate_net_worth,
    calculate_savings_rate,
    BudgetStatus,
    GoalMetrics,
    MonthlySummary,
    NetWorthSummary,
)
from database import Database
from models import (
    Account,
    Budget,
    Category,
    FinancialGoal,
    GoalContribution,
    Merchant,
    RecurringTransaction,
    Transaction,
)


class AccountService:
    def __init__(self, db: Database):
        self.db = db

    def create_account(self, name: str, account_type: str, opening_balance_paise: int = 0) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Account name cannot be empty.")
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO accounts (name, account_type, opening_balance_paise, created_at, is_active)
                VALUES (?, ?, ?, ?, 1);
                """,
                (name, account_type, opening_balance_paise, date.today().isoformat()),
            )
            return cur.lastrowid

    def update_account(self, account_id: int, name: str, account_type: str, opening_balance_paise: int) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Account name cannot be empty.")
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE accounts
                SET name = ?, account_type = ?, opening_balance_paise = ?
                WHERE id = ?;
                """,
                (name, account_type, opening_balance_paise, account_id),
            )

    def toggle_active(self, account_id: int) -> bool:
        account = self.get_account(account_id)
        if not account:
            raise ValueError("Account not found.")
        new_status = 0 if account.is_active else 1
        with self.db.transaction() as cur:
            cur.execute("UPDATE accounts SET is_active = ? WHERE id = ?;", (new_status, account_id))
        return bool(new_status)

    def get_account(self, account_id: int) -> Optional[Account]:
        row = self.db.fetch_one("SELECT * FROM accounts WHERE id = ?;", (account_id,))
        if not row:
            return None
        return Account(
            id=row["id"],
            name=row["name"],
            account_type=row["account_type"],
            opening_balance_paise=row["opening_balance_paise"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    def get_all_accounts(self, include_inactive: bool = False) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY is_active DESC, name ASC;"
        rows = self.db.fetch_all(sql)
        return [
            Account(
                id=r["id"],
                name=r["name"],
                account_type=r["account_type"],
                opening_balance_paise=r["opening_balance_paise"],
                created_at=r["created_at"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    def get_account_balance(self, account_id: int) -> int:
        account = self.get_account(account_id)
        if not account:
            return 0

        # Calculate net change:
        # income: + amount
        # expense: - amount
        # transfer: if transfer_group_id has source, note shows Transfer to (outflow) or Transfer from (inflow)
        # We store transfer type with positive amount.
        # To determine inflow vs outflow for transfer:
        # Check transaction note: "Transfer to ..." is outflow (-), "Transfer from ..." is inflow (+)
        rows = self.db.fetch_all(
            """
            SELECT transaction_type, amount_paise, note
            FROM transactions
            WHERE account_id = ?;
            """,
            (account_id,),
        )

        net_paise = account.opening_balance_paise
        for r in rows:
            t_type = r["transaction_type"]
            amount = r["amount_paise"]
            note = r["note"] or ""

            if t_type == "income":
                net_paise += amount
            elif t_type == "expense":
                net_paise -= amount
            elif t_type == "transfer":
                if note.startswith("Transfer to"):
                    net_paise -= amount
                elif note.startswith("Transfer from"):
                    net_paise += amount
                else:
                    # Fallback if custom note
                    net_paise -= amount

        return net_paise

    def get_all_account_balances(self, include_inactive: bool = False) -> list[tuple[Account, int]]:
        accounts = self.get_all_accounts(include_inactive=include_inactive)
        return [(acct, self.get_account_balance(acct.id)) for acct in accounts]


class CategoryService:
    def __init__(self, db: Database):
        self.db = db

    def get_categories(self, category_type: Optional[str] = None, include_inactive: bool = False) -> list[Category]:
        sql = "SELECT * FROM categories WHERE 1=1"
        params: list[Any] = []
        if not include_inactive:
            sql += " AND is_active = 1"
        if category_type:
            sql += " AND category_type = ?"
            params.append(category_type)
        sql += " ORDER BY name ASC;"
        rows = self.db.fetch_all(sql, params)
        return [
            Category(
                id=r["id"],
                name=r["name"],
                category_type=r["category_type"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    def get_or_create_category(self, name: str, category_type: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty.")
        row = self.db.fetch_one(
            "SELECT id FROM categories WHERE name = ? COLLATE NOCASE AND category_type = ?;",
            (name, category_type),
        )
        if row:
            return row["id"]
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO categories (name, category_type, is_active) VALUES (?, ?, 1);",
                (name, category_type),
            )
            return cur.lastrowid


class MerchantService:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create_merchant(self, name: str) -> Optional[int]:
        name = name.strip()
        if not name:
            return None
        row = self.db.fetch_one("SELECT id FROM merchants WHERE name = ? COLLATE NOCASE;", (name,))
        if row:
            return row["id"]
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO merchants (name) VALUES (?);", (name,))
            return cur.lastrowid

    def get_all_merchants(self) -> list[Merchant]:
        rows = self.db.fetch_all("SELECT * FROM merchants ORDER BY name ASC;")
        return [Merchant(id=r["id"], name=r["name"]) for r in rows]


class TransactionService:
    def __init__(self, db: Database, merchant_service: MerchantService):
        self.db = db
        self.merchant_service = merchant_service

    def create_income_or_expense(
        self,
        account_id: int,
        amount_paise: int,
        transaction_type: str,
        transaction_date: str,
        category_id: Optional[int] = None,
        merchant_name: str = "",
        note: str = "",
    ) -> int:
        if amount_paise <= 0:
            raise ValueError("Amount must be greater than zero.")
        if transaction_type not in ("income", "expense"):
            raise ValueError("Transaction type must be 'income' or 'expense'.")
        if not transaction_date:
            raise ValueError("Transaction date is required.")

        merchant_id = self.merchant_service.get_or_create_merchant(merchant_name)

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO transactions (
                    account_id, category_id, merchant_id, amount_paise,
                    transaction_type, transaction_date, note, transfer_group_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?);
                """,
                (
                    account_id,
                    category_id,
                    merchant_id,
                    amount_paise,
                    transaction_type,
                    transaction_date,
                    note.strip(),
                    datetime.now().isoformat(),
                ),
            )
            return cur.lastrowid

    def create_transfer(
        self,
        source_account_id: int,
        destination_account_id: int,
        amount_paise: int,
        transaction_date: str,
        note: str = "",
    ) -> str:
        """
        Creates an atomic two-sided transfer.
        Both sides share the same transfer_group_id.
        Fails if source and destination accounts are the same.
        Neither side impacts income or expense reporting.
        """
        if amount_paise <= 0:
            raise ValueError("Transfer amount must be greater than zero.")
        if source_account_id == destination_account_id:
            raise ValueError("Source and destination accounts must be different.")
        if not transaction_date:
            raise ValueError("Transfer date is required.")

        # Fetch account names for informative notes
        src_row = self.db.fetch_one("SELECT name FROM accounts WHERE id = ?;", (source_account_id,))
        dst_row = self.db.fetch_one("SELECT name FROM accounts WHERE id = ?;", (destination_account_id,))
        if not src_row or not dst_row:
            raise ValueError("One or both accounts do not exist.")

        src_name = src_row["name"]
        dst_name = dst_row["name"]

        group_id = uuid.uuid4().hex
        custom_note = f" ({note.strip()})" if note.strip() else ""
        outflow_note = f"Transfer to {dst_name}{custom_note}"
        inflow_note = f"Transfer from {src_name}{custom_note}"
        now_ts = datetime.now().isoformat()

        # Execute atomically inside a single transaction
        with self.db.transaction() as cur:
            # Source outflow
            cur.execute(
                """
                INSERT INTO transactions (
                    account_id, category_id, merchant_id, amount_paise,
                    transaction_type, transaction_date, note, transfer_group_id, created_at
                ) VALUES (?, NULL, NULL, ?, 'transfer', ?, ?, ?, ?);
                """,
                (source_account_id, amount_paise, transaction_date, outflow_note, group_id, now_ts),
            )
            # Destination inflow
            cur.execute(
                """
                INSERT INTO transactions (
                    account_id, category_id, merchant_id, amount_paise,
                    transaction_type, transaction_date, note, transfer_group_id, created_at
                ) VALUES (?, NULL, NULL, ?, 'transfer', ?, ?, ?, ?);
                """,
                (destination_account_id, amount_paise, transaction_date, inflow_note, group_id, now_ts),
            )

        return group_id

    def update_transaction(
        self,
        transaction_id: int,
        account_id: int,
        amount_paise: int,
        transaction_date: str,
        category_id: Optional[int] = None,
        merchant_name: str = "",
        note: str = "",
    ) -> None:
        """Update an existing income or expense transaction."""
        if amount_paise <= 0:
            raise ValueError("Amount must be greater than zero.")
        tx = self.get_transaction(transaction_id)
        if not tx:
            raise ValueError("Transaction not found.")
        if tx.is_transfer:
            raise ValueError("Transfers cannot be updated via this method.")

        merchant_id = self.merchant_service.get_or_create_merchant(merchant_name)

        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE transactions
                SET account_id = ?, category_id = ?, merchant_id = ?,
                    amount_paise = ?, transaction_date = ?, note = ?
                WHERE id = ?;
                """,
                (account_id, category_id, merchant_id, amount_paise, transaction_date, note.strip(), transaction_id),
            )

    def delete_transaction(self, transaction_id: int) -> None:
        """
        Delete a transaction.
        If part of a transfer pair, deletes BOTH linked sides atomically.
        """
        tx = self.get_transaction(transaction_id)
        if not tx:
            return

        with self.db.transaction() as cur:
            if tx.transfer_group_id:
                cur.execute("DELETE FROM transactions WHERE transfer_group_id = ?;", (tx.transfer_group_id,))
            else:
                cur.execute("DELETE FROM transactions WHERE id = ?;", (transaction_id,))

    def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        sql = """
            SELECT t.*, a.name AS account_name, c.name AS category_name, m.name AS merchant_name
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN merchants m ON t.merchant_id = m.id
            WHERE t.id = ?;
        """
        row = self.db.fetch_one(sql, (transaction_id,))
        if not row:
            return None
        return self._row_to_transaction(row)

    def search_transactions(
        self,
        account_id: Optional[int] = None,
        category_id: Optional[int] = None,
        transaction_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search_text: str = "",
        sort_by: str = "transaction_date",
        sort_order: str = "DESC",
        limit: Optional[int] = None,
    ) -> list[Transaction]:
        sql = """
            SELECT t.*, a.name AS account_name, c.name AS category_name, m.name AS merchant_name
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN merchants m ON t.merchant_id = m.id
            WHERE 1=1
        """
        params: list[Any] = []

        if account_id:
            sql += " AND t.account_id = ?"
            params.append(account_id)
        if category_id:
            sql += " AND t.category_id = ?"
            params.append(category_id)
        if transaction_type and transaction_type != "all":
            sql += " AND t.transaction_type = ?"
            params.append(transaction_type)
        if start_date:
            sql += " AND t.transaction_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND t.transaction_date <= ?"
            params.append(end_date)
        if search_text.strip():
            like_term = f"%{search_text.strip()}%"
            sql += " AND (t.note LIKE ? OR c.name LIKE ? OR m.name LIKE ? OR a.name LIKE ?)"
            params.extend([like_term, like_term, like_term, like_term])

        valid_sorts = {
            "transaction_date": "t.transaction_date",
            "amount_paise": "t.amount_paise",
            "account_name": "a.name",
            "category_name": "c.name",
            "created_at": "t.created_at",
        }
        col = valid_sorts.get(sort_by, "t.transaction_date")
        direction = "DESC" if sort_order.upper() == "DESC" else "ASC"
        sql += f" ORDER BY {col} {direction}, t.id DESC"

        if limit:
            sql += f" LIMIT {int(limit)}"

        rows = self.db.fetch_all(sql, params)
        return [self._row_to_transaction(r) for r in rows]

    def get_recent_transactions(self, limit: int = 10) -> list[Transaction]:
        return self.search_transactions(limit=limit)

    @staticmethod
    def _row_to_transaction(r: sqlite3.Row) -> Transaction:
        return Transaction(
            id=r["id"],
            account_id=r["account_id"],
            category_id=r["category_id"],
            merchant_id=r["merchant_id"],
            amount_paise=r["amount_paise"],
            transaction_type=r["transaction_type"],
            transaction_date=r["transaction_date"],
            note=r["note"] or "",
            transfer_group_id=r["transfer_group_id"],
            created_at=r["created_at"],
            account_name=r["account_name"] or "",
            category_name=r["category_name"] or ("Transfer" if r["transaction_type"] == "transfer" else "Uncategorized"),
            merchant_name=r["merchant_name"] or "",
        )


class BudgetService:
    def __init__(self, db: Database):
        self.db = db

    def set_budget(self, month: str, category_id: int, limit_paise: int) -> int:
        if limit_paise < 0:
            raise ValueError("Budget limit cannot be negative.")
        if not month:
            raise ValueError("Month (YYYY-MM) is required.")

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO budgets (month, category_id, limit_paise, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(month, category_id) DO UPDATE SET limit_paise = excluded.limit_paise;
                """,
                (month, category_id, limit_paise, datetime.now().isoformat()),
            )
            return cur.lastrowid

    def delete_budget(self, budget_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM budgets WHERE id = ?;", (budget_id,))

    def get_budgets_for_month(self, month: str) -> list[tuple[Budget, BudgetStatus]]:
        """
        Retrieves all budgets for the given month (YYYY-MM),
        along with spent amount calculated strictly from 'expense' transactions in that month.
        Transfers are explicitly ignored.
        """
        budgets_sql = """
            SELECT b.*, c.name AS category_name
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            WHERE b.month = ?
            ORDER BY c.name ASC;
        """
        b_rows = self.db.fetch_all(budgets_sql, (month,))

        # Query spending per category for this month: YYYY-MM%
        spend_sql = """
            SELECT category_id, SUM(amount_paise) as total_spent
            FROM transactions
            WHERE transaction_type = 'expense'
              AND transaction_date LIKE ?
              AND category_id IS NOT NULL
            GROUP BY category_id;
        """
        spend_rows = self.db.fetch_all(spend_sql, (f"{month}%",))
        spend_map = {r["category_id"]: r["total_spent"] for r in spend_rows}

        results: list[tuple[Budget, BudgetStatus]] = []
        for r in b_rows:
            budget = Budget(
                id=r["id"],
                month=r["month"],
                category_id=r["category_id"],
                limit_paise=r["limit_paise"],
                created_at=r["created_at"],
                category_name=r["category_name"],
            )
            spent = spend_map.get(budget.category_id, 0)
            status = calculate_budget_usage(
                limit_paise=budget.limit_paise,
                spent_paise=spent,
                category_id=budget.category_id,
                category_name=budget.category_name,
            )
            results.append((budget, status))
        return results


class RecurringService:
    def __init__(self, db: Database, merchant_service: MerchantService):
        self.db = db
        self.merchant_service = merchant_service

    def create_recurring(
        self,
        account_id: int,
        amount_paise: int,
        transaction_type: str,
        frequency: str,
        next_run_date: str,
        category_id: Optional[int] = None,
        merchant_name: str = "",
        note: str = "",
    ) -> int:
        if amount_paise <= 0:
            raise ValueError("Amount must be greater than zero.")
        if transaction_type not in ("income", "expense"):
            raise ValueError("Type must be income or expense.")
        if frequency not in ("daily", "weekly", "monthly", "yearly"):
            raise ValueError("Frequency must be daily, weekly, monthly, or yearly.")
        if not next_run_date:
            raise ValueError("Next run date is required.")

        merchant_id = self.merchant_service.get_or_create_merchant(merchant_name)

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO recurring_transactions (
                    account_id, category_id, merchant_id, amount_paise,
                    transaction_type, frequency, next_run_date, note, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                (
                    account_id,
                    category_id,
                    merchant_id,
                    amount_paise,
                    transaction_type,
                    frequency,
                    next_run_date,
                    note.strip(),
                ),
            )
            return cur.lastrowid

    def update_recurring(
        self,
        recurring_id: int,
        account_id: int,
        amount_paise: int,
        transaction_type: str,
        frequency: str,
        next_run_date: str,
        category_id: Optional[int] = None,
        merchant_name: str = "",
        note: str = "",
        is_active: bool = True,
    ) -> None:
        merchant_id = self.merchant_service.get_or_create_merchant(merchant_name)
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE recurring_transactions
                SET account_id = ?, category_id = ?, merchant_id = ?, amount_paise = ?,
                    transaction_type = ?, frequency = ?, next_run_date = ?, note = ?, is_active = ?
                WHERE id = ?;
                """,
                (
                    account_id,
                    category_id,
                    merchant_id,
                    amount_paise,
                    transaction_type,
                    frequency,
                    next_run_date,
                    note.strip(),
                    1 if is_active else 0,
                    recurring_id,
                ),
            )

    def delete_recurring(self, recurring_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM recurring_transactions WHERE id = ?;", (recurring_id,))

    def get_all_recurring(self, include_inactive: bool = False) -> list[RecurringTransaction]:
        sql = """
            SELECT r.*, a.name AS account_name, c.name AS category_name, m.name AS merchant_name
            FROM recurring_transactions r
            JOIN accounts a ON r.account_id = a.id
            LEFT JOIN categories c ON r.category_id = c.id
            LEFT JOIN merchants m ON r.merchant_id = m.id
            WHERE 1=1
        """
        if not include_inactive:
            sql += " AND r.is_active = 1"
        sql += " ORDER BY r.next_run_date ASC;"

        rows = self.db.fetch_all(sql)
        return [
            RecurringTransaction(
                id=r["id"],
                account_id=r["account_id"],
                category_id=r["category_id"],
                merchant_id=r["merchant_id"],
                amount_paise=r["amount_paise"],
                transaction_type=r["transaction_type"],
                frequency=r["frequency"],
                next_run_date=r["next_run_date"],
                note=r["note"] or "",
                is_active=bool(r["is_active"]),
                account_name=r["account_name"] or "",
                category_name=r["category_name"] or "",
                merchant_name=r["merchant_name"] or "",
            )
            for r in rows
        ]

    def process_due_transactions(self, as_of_date: Optional[date] = None) -> int:
        """
        Identifies all recurring items due on or before as_of_date.
        Creates corresponding real transactions and advances next_run_date.
        Prevents accidental duplicate generation using unique signature checks.
        Returns the number of created transactions.
        """
        if as_of_date is None:
            as_of_date = date.today()

        as_of_str = as_of_date.isoformat()
        due_items = self.get_all_recurring(include_inactive=False)
        processed_count = 0

        for item in due_items:
            if not item.is_due(as_of_date):
                continue

            audit_tag = f"[Recurring #{item.id}]"
            full_note = f"{item.note} {audit_tag}".strip()

            # Prevent duplicate generation if already run for this exact run date
            dup_check = self.db.fetch_one(
                """
                SELECT id FROM transactions
                WHERE account_id = ?
                  AND amount_paise = ?
                  AND transaction_date = ?
                  AND note LIKE ?;
                """,
                (item.account_id, item.amount_paise, item.next_run_date, f"%{audit_tag}%"),
            )

            with self.db.transaction() as cur:
                if not dup_check:
                    cur.execute(
                        """
                        INSERT INTO transactions (
                            account_id, category_id, merchant_id, amount_paise,
                            transaction_type, transaction_date, note, transfer_group_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?);
                        """,
                        (
                            item.account_id,
                            item.category_id,
                            item.merchant_id,
                            item.amount_paise,
                            item.transaction_type,
                            item.next_run_date,
                            full_note,
                            datetime.now().isoformat(),
                        ),
                    )
                    processed_count += 1

                # Advance next run date
                next_date = item.calculate_next_date()
                cur.execute(
                    "UPDATE recurring_transactions SET next_run_date = ? WHERE id = ?;",
                    (next_date, item.id),
                )

        return processed_count


class GoalService:
    def __init__(self, db: Database):
        self.db = db

    def create_goal(self, name: str, target_amount_paise: int, target_date: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Goal name cannot be empty.")
        if target_amount_paise <= 0:
            raise ValueError("Target amount must be greater than zero.")
        if not target_date:
            raise ValueError("Target date is required.")

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO financial_goals (name, target_amount_paise, target_date, created_at, is_active)
                VALUES (?, ?, ?, ?, 1);
                """,
                (name, target_amount_paise, target_date, date.today().isoformat()),
            )
            return cur.lastrowid

    def update_goal(self, goal_id: int, name: str, target_amount_paise: int, target_date: str, is_active: bool) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Goal name cannot be empty.")
        if target_amount_paise <= 0:
            raise ValueError("Target amount must be greater than zero.")

        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE financial_goals
                SET name = ?, target_amount_paise = ?, target_date = ?, is_active = ?
                WHERE id = ?;
                """,
                (name, target_amount_paise, target_date, 1 if is_active else 0, goal_id),
            )

    def delete_goal(self, goal_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM financial_goals WHERE id = ?;", (goal_id,))

    def add_contribution(self, goal_id: int, amount_paise: int, contribution_date: str, note: str = "") -> int:
        if amount_paise <= 0:
            raise ValueError("Contribution amount must be greater than zero.")
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO goal_contributions (goal_id, amount_paise, contribution_date, note)
                VALUES (?, ?, ?, ?);
                """,
                (goal_id, amount_paise, contribution_date, note.strip()),
            )
            return cur.lastrowid

    def get_contributions(self, goal_id: int) -> list[GoalContribution]:
        rows = self.db.fetch_all(
            "SELECT * FROM goal_contributions WHERE goal_id = ? ORDER BY contribution_date DESC, id DESC;",
            (goal_id,),
        )
        return [
            GoalContribution(
                id=r["id"],
                goal_id=r["goal_id"],
                amount_paise=r["amount_paise"],
                contribution_date=r["contribution_date"],
                note=r["note"] or "",
            )
            for r in rows
        ]

    def get_all_goals(self, include_inactive: bool = False) -> list[tuple[FinancialGoal, GoalMetrics]]:
        sql = "SELECT * FROM financial_goals"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY target_date ASC;"
        rows = self.db.fetch_all(sql)

        # Get contributions total for each goal
        sums_rows = self.db.fetch_all("SELECT goal_id, SUM(amount_paise) as total FROM goal_contributions GROUP BY goal_id;")
        contrib_map = {r["goal_id"]: r["total"] for r in sums_rows}

        results: list[tuple[FinancialGoal, GoalMetrics]] = []
        for r in rows:
            saved = contrib_map.get(r["id"], 0)
            goal = FinancialGoal(
                id=r["id"],
                name=r["name"],
                target_amount_paise=r["target_amount_paise"],
                target_date=r["target_date"],
                created_at=r["created_at"],
                is_active=bool(r["is_active"]),
                saved_amount_paise=saved,
            )
            metrics = calculate_goal_metrics(
                target_paise=goal.target_amount_paise,
                saved_paise=saved,
                target_date_str=goal.target_date,
            )
            results.append((goal, metrics))
        return results


class AnalyticsService:
    def __init__(self, db: Database, account_service: AccountService):
        self.db = db
        self.account_service = account_service

    def get_monthly_summary(self, month: str) -> MonthlySummary:
        """
        Calculate total income, expenses, and savings for a month (YYYY-MM).
        Transfers are strictly excluded.
        """
        rows = self.db.fetch_all(
            """
            SELECT transaction_type, SUM(amount_paise) as total, COUNT(*) as cnt
            FROM transactions
            WHERE transaction_date LIKE ?
              AND transaction_type IN ('income', 'expense')
            GROUP BY transaction_type;
            """,
            (f"{month}%",),
        )
        income = 0
        expense = 0
        count = 0
        for r in rows:
            if r["transaction_type"] == "income":
                income = r["total"] or 0
                count += r["cnt"] or 0
            elif r["transaction_type"] == "expense":
                expense = r["total"] or 0
                count += r["cnt"] or 0

        net_savings = income - expense
        savings_rate = calculate_savings_rate(income, expense)
        return MonthlySummary(
            income_paise=income,
            expense_paise=expense,
            net_savings_paise=net_savings,
            savings_rate_percent=savings_rate,
            transaction_count=count,
        )

    def get_net_worth(self) -> NetWorthSummary:
        account_balances = self.account_service.get_all_account_balances(include_inactive=False)
        type_balance_pairs = [(acct.account_type, bal) for acct, bal in account_balances]
        return calculate_net_worth(type_balance_pairs)

    def get_category_spending(self, start_date: str, end_date: str) -> list[tuple[str, int]]:
        """Returns sorted list of (category_name, total_paise) for expenses in date range."""
        rows = self.db.fetch_all(
            """
            SELECT COALESCE(c.name, 'Uncategorized') as cat_name, SUM(t.amount_paise) as total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.transaction_type = 'expense'
              AND t.transaction_date >= ?
              AND t.transaction_date <= ?
            GROUP BY cat_name
            ORDER BY total DESC;
            """,
            (start_date, end_date),
        )
        return [(r["cat_name"], r["total"]) for r in rows]

    def get_monthly_cashflow_history(self, num_months: int = 6) -> list[dict[str, Any]]:
        """
        Returns monthly income, expense, and savings for the past `num_months`.
        """
        results = []
        today = date.today()
        # Collect months in chronological order
        for i in range(num_months - 1, -1, -1):
            # calculate year and month
            total_m = today.year * 12 + today.month - 1 - i
            y = total_m // 12
            m = (total_m % 12) + 1
            month_str = f"{y:04d}-{m:02d}"
            summary = self.get_monthly_summary(month_str)
            results.append({
                "month": month_str,
                "label": calendar.month_abbr[m] + f" '{str(y)[2:]}",
                "income_paise": summary.income_paise,
                "expense_paise": summary.expense_paise,
                "savings_paise": summary.net_savings_paise,
            })
        return results


class DemoDataService:
    def __init__(self, db: Database, account_service: AccountService, transaction_service: TransactionService,
                 budget_service: BudgetService, recurring_service: RecurringService, goal_service: GoalService):
        self.db = db
        self.account_service = account_service
        self.transaction_service = transaction_service
        self.budget_service = budget_service
        self.recurring_service = recurring_service
        self.goal_service = goal_service

    def load_demo_data(self) -> None:
        """
        Seeds rich, realistic financial data spanning multiple accounts,
        transactions across recent months, category budgets, recurring templates, and financial goals.
        """
        # 1. Accounts
        hdfc_id = self.account_service.create_account("HDFC Salary Account", "Bank", 4500000)  # ₹45,000
        sbi_id = self.account_service.create_account("SBI Emergency Fund", "Savings", 12000000)  # ₹1,20,000
        cash_id = self.account_service.create_account("Cash Wallet", "Cash", 350000)  # ₹3,500
        icici_id = self.account_service.create_account("ICICI Amazon Pay Card", "Credit Card", -850000)  # -₹8,500

        # Helper to lookup category id
        def get_cat(name: str, cat_type: str) -> Optional[int]:
            row = self.db.fetch_one("SELECT id FROM categories WHERE name = ? AND category_type = ?;", (name, cat_type))
            return row["id"] if row else None

        salary_cat = get_cat("Salary", "income")
        freelance_cat = get_cat("Freelance / Consulting", "income")
        food_cat = get_cat("Food & Dining", "expense")
        groc_cat = get_cat("Groceries", "expense")
        trans_cat = get_cat("Transportation", "expense")
        shop_cat = get_cat("Shopping", "expense")
        rent_cat = get_cat("Housing & Rent", "expense")
        util_cat = get_cat("Utilities & Bills", "expense")
        ent_cat = get_cat("Entertainment", "expense")
        health_cat = get_cat("Healthcare", "expense")

        today = date.today()

        # Generate realistic data for the past 3 months
        for m_offset in (2, 1, 0):
            # Calculate base date for month
            total_m = today.year * 12 + today.month - 1 - m_offset
            y = total_m // 12
            m = (total_m % 12) + 1
            month_prefix = f"{y:04d}-{m:02d}"

            # 1st of month: Salary
            self.transaction_service.create_income_or_expense(
                account_id=hdfc_id,
                amount_paise=8500000,  # ₹85,000
                transaction_type="income",
                transaction_date=f"{month_prefix}-01",
                category_id=salary_cat,
                merchant_name="TechCorp India",
                note="Monthly Salary",
            )

            # 2nd of month: Rent
            self.transaction_service.create_income_or_expense(
                account_id=hdfc_id,
                amount_paise=2200000,  # ₹22,000
                transaction_type="expense",
                transaction_date=f"{month_prefix}-02",
                category_id=rent_cat,
                merchant_name="Apartment Landlord",
                note="Monthly Flat Rent",
            )

            # 3rd of month: ATM Cash Withdrawal (Transfer: HDFC -> Cash)
            self.transaction_service.create_transfer(
                source_account_id=hdfc_id,
                destination_account_id=cash_id,
                amount_paise=500000,  # ₹5,000
                transaction_date=f"{month_prefix}-03",
                note="ATM Cash Withdrawal",
            )

            # 5th of month: Groceries
            self.transaction_service.create_income_or_expense(
                account_id=hdfc_id,
                amount_paise=425000,  # ₹4,250
                transaction_type="expense",
                transaction_date=f"{month_prefix}-05",
                category_id=groc_cat,
                merchant_name="Zepto / Blinkit",
                note="Monthly Pantry Staples",
            )

            # 8th of month: Utilities & Broadband
            self.transaction_service.create_income_or_expense(
                account_id=hdfc_id,
                amount_paise=185000,  # ₹1,850
                transaction_type="expense",
                transaction_date=f"{month_prefix}-08",
                category_id=util_cat,
                merchant_name="Airtel Broadband",
                note="Fiber Internet & Mobile",
            )

            # 12th of month: Dining / Eating Out
            self.transaction_service.create_income_or_expense(
                account_id=icici_id,
                amount_paise=142000,  # ₹1,420
                transaction_type="expense",
                transaction_date=f"{month_prefix}-12",
                category_id=food_cat,
                merchant_name="Swiggy",
                note="Weekend Dinner with friends",
            )

            # 15th of month: Transfer to Emergency Fund (HDFC -> SBI)
            self.transaction_service.create_transfer(
                source_account_id=hdfc_id,
                destination_account_id=sbi_id,
                amount_paise=1500000,  # ₹15,000
                transaction_date=f"{month_prefix}-15",
                note="Monthly Savings Allocation",
            )

            # 18th of month: Shopping
            self.transaction_service.create_income_or_expense(
                account_id=icici_id,
                amount_paise=320000,  # ₹3,200
                transaction_type="expense",
                transaction_date=f"{month_prefix}-18",
                category_id=shop_cat,
                merchant_name="Amazon India",
                note="Books & Home Ergonomics",
            )

            # 22nd of month: Transportation
            self.transaction_service.create_income_or_expense(
                account_id=cash_id,
                amount_paise=95000,  # ₹950
                transaction_type="expense",
                transaction_date=f"{month_prefix}-22",
                category_id=trans_cat,
                merchant_name="Metro & Auto",
                note="Weekly Commute",
            )

            # Extra freelance income in month 1
            if m_offset == 1:
                self.transaction_service.create_income_or_expense(
                    account_id=hdfc_id,
                    amount_paise=3500000,  # ₹35,000
                    transaction_type="income",
                    transaction_date=f"{month_prefix}-20",
                    category_id=freelance_cat,
                    merchant_name="Acme Digital Client",
                    note="Frontend UI Consulting",
                )

        # 2. Budgets for Current Month
        curr_month = today.strftime("%Y-%m")
        if food_cat:
            self.budget_service.set_budget(curr_month, food_cat, 800000)  # ₹8,000
        if groc_cat:
            self.budget_service.set_budget(curr_month, groc_cat, 1200000)  # ₹12,000
        if shop_cat:
            self.budget_service.set_budget(curr_month, shop_cat, 600000)  # ₹6,000
        if util_cat:
            self.budget_service.set_budget(curr_month, util_cat, 400000)  # ₹4,000
        if trans_cat:
            self.budget_service.set_budget(curr_month, trans_cat, 350000)  # ₹3,500

        # 3. Recurring Transactions
        next_sal_date = f"{today.year:04d}-{today.month:02d}-28"
        self.recurring_service.create_recurring(
            account_id=hdfc_id,
            amount_paise=8500000,
            transaction_type="income",
            frequency="monthly",
            next_run_date=next_sal_date,
            category_id=salary_cat,
            merchant_name="TechCorp India",
            note="Monthly Payroll",
        )
        self.recurring_service.create_recurring(
            account_id=hdfc_id,
            amount_paise=64900,
            transaction_type="expense",
            frequency="monthly",
            next_run_date=today.isoformat(),  # Due today for testing!
            category_id=ent_cat,
            merchant_name="Netflix India",
            note="Premium 4K Subscription",
        )

        # 4. Financial Goals
        next_year = f"{today.year + 1:04d}-06-30"
        goal1_id = self.goal_service.create_goal("Emergency Fund (6 Months)", 30000000, next_year)  # ₹3,00,000
        self.goal_service.add_contribution(goal1_id, 12000000, today.isoformat(), "Initial Seed from Savings")
        self.goal_service.add_contribution(goal1_id, 3000000, today.isoformat(), "Bonus Contribution")

        laptop_date = f"{today.year:04d}-12-31"
        goal2_id = self.goal_service.create_goal("M3 MacBook Pro", 15000000, laptop_date)  # ₹1,50,000
        self.goal_service.add_contribution(goal2_id, 6500000, today.isoformat(), "Saved from Freelance Project")

    def clear_all_data(self) -> None:
        """Wipes all transactional data while preserving categories."""
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM goal_contributions;")
            cur.execute("DELETE FROM financial_goals;")
            cur.execute("DELETE FROM recurring_transactions;")
            cur.execute("DELETE FROM budgets;")
            cur.execute("DELETE FROM transactions;")
            cur.execute("DELETE FROM accounts;")
            cur.execute("DELETE FROM merchants;")


class FinanceService:
    """
    High-level facade coordinating all services for the presentation/UI layer.
    """
    def __init__(self, db_path: str = "ledger.db"):
        self.db = Database(db_path)
        self.merchants = MerchantService(self.db)
        self.accounts = AccountService(self.db)
        self.categories = CategoryService(self.db)
        self.transactions = TransactionService(self.db, self.merchants)
        self.budgets = BudgetService(self.db)
        self.recurring = RecurringService(self.db, self.merchants)
        self.goals = GoalService(self.db)
        self.analytics = AnalyticsService(self.db, self.accounts)
        self.demo = DemoDataService(
            self.db,
            self.accounts,
            self.transactions,
            self.budgets,
            self.recurring,
            self.goals,
        )
