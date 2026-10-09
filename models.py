"""
models.py - Object-Oriented Domain Models for Ledger.

Each model encapsulates its domain logic, attributes, and relationships.
All monetary amounts are represented as integer paise.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import calendar
from typing import Optional

from calculations import format_currency, paise_to_rupees


# =====================================================================
# DOMAIN ENTITIES
# =====================================================================

@dataclass
class Account:
    """Represents a financial account (e.g., Bank, Cash, Credit Card)."""
    id: Optional[int]
    name: str
    account_type: str  # Bank, Cash, Credit Card, Savings, Other
    opening_balance_paise: int = 0
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    is_active: bool = True

    @property
    def is_liability(self) -> bool:
        """Determines if the account represents a liability/debt."""
        return self.account_type.lower() in ("credit card", "credit", "loan", "liability")

    @property
    def formatted_opening_balance(self) -> str:
        """Returns the formatted opening balance in Rupees."""
        return format_currency(self.opening_balance_paise)


@dataclass
class Category:
    """Represents a budget/transaction category."""
    id: Optional[int]
    name: str
    category_type: str  # 'expense' or 'income'
    is_active: bool = True

    def __post_init__(self) -> None:
        if self.category_type not in ("expense", "income"):
            raise ValueError(f"Category type must be 'expense' or 'income', got '{self.category_type}'")


@dataclass
class Merchant:
    """Represents a payee or payer."""
    id: Optional[int]
    name: str


@dataclass
class Transaction:
    """
    Represents an atomic financial transaction.
    Types: 'income', 'expense', 'transfer'.
    Transfers have a shared `transfer_group_id` linking the two sides.
    """
    id: Optional[int]
    account_id: int
    amount_paise: int
    transaction_type: str  # 'income', 'expense', 'transfer'
    transaction_date: str  # YYYY-MM-DD
    category_id: Optional[int] = None
    merchant_id: Optional[int] = None
    note: str = ""
    transfer_group_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Denormalized convenience fields for UI rendering
    account_name: str = ""
    category_name: str = ""
    merchant_name: str = ""

    def __post_init__(self) -> None:
        if self.transaction_type not in ("income", "expense", "transfer"):
            raise ValueError(f"Invalid transaction type: '{self.transaction_type}'")

    @property
    def is_income(self) -> bool:
        return self.transaction_type == "income"

    @property
    def is_expense(self) -> bool:
        return self.transaction_type == "expense"

    @property
    def is_transfer(self) -> bool:
        return self.transaction_type == "transfer"

    @property
    def formatted_amount(self) -> str:
        """Returns formatted amount with +/- prefix based on type."""
        if self.is_income:
            return f"+{format_currency(self.amount_paise)}"
        if self.is_expense:
            return f"-{format_currency(self.amount_paise)}"
        return format_currency(self.amount_paise)


@dataclass
class Budget:
    """Represents a spending limit for a category in a specific month."""
    id: Optional[int]
    month: str  # Format: YYYY-MM
    category_id: int
    limit_paise: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    category_name: str = ""

    @property
    def formatted_limit(self) -> str:
        return format_currency(self.limit_paise)


@dataclass
class RecurringTransaction:
    """
    Represents a recurring template for scheduled transactions.
    Frequency: 'daily', 'weekly', 'monthly', 'yearly'.
    """
    id: Optional[int]
    account_id: int
    amount_paise: int
    transaction_type: str  # 'income', 'expense'
    frequency: str  # 'daily', 'weekly', 'monthly', 'yearly'
    next_run_date: str  # YYYY-MM-DD
    category_id: Optional[int] = None
    merchant_id: Optional[int] = None
    note: str = ""
    is_active: bool = True

    # Denormalized fields
    account_name: str = ""
    category_name: str = ""
    merchant_name: str = ""

    def is_due(self, as_of_date: Optional[date] = None) -> bool:
        """Check if this recurring transaction is due on or before as_of_date."""
        if not self.is_active:
            return False
        if as_of_date is None:
            as_of_date = date.today()
        try:
            run_d = datetime.strptime(self.next_run_date, "%Y-%m-%d").date()
            return run_d <= as_of_date
        except (ValueError, TypeError):
            return False

    def calculate_next_date(self, from_date: Optional[date] = None) -> str:
        """
        Calculate the subsequent run date based on frequency.
        Handles end-of-month dates safely (e.g. Jan 31 -> Feb 28).
        """
        if from_date is None:
            try:
                from_date = datetime.strptime(self.next_run_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                from_date = date.today()

        freq = self.frequency.lower()
        if freq == "daily":
            next_d = from_date + timedelta(days=1)
        elif freq == "weekly":
            next_d = from_date + timedelta(weeks=1)
        elif freq == "monthly":
            # Add 1 month handling variable month lengths
            month = from_date.month + 1
            year = from_date.year
            if month > 12:
                month = 1
                year += 1
            max_days = calendar.monthrange(year, month)[1]
            day = min(from_date.day, max_days)
            next_d = date(year, month, day)
        elif freq == "yearly":
            try:
                next_d = from_date.replace(year=from_date.year + 1)
            except ValueError:
                # Feb 29 leap year edge case
                next_d = from_date.replace(year=from_date.year + 1, day=28)
        else:
            next_d = from_date + timedelta(days=30)

        return next_d.isoformat()


@dataclass
class FinancialGoal:
    """Represents a savings/financial target."""
    id: Optional[int]
    name: str
    target_amount_paise: int
    target_date: str  # YYYY-MM-DD
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    is_active: bool = True

    # Calculated metrics
    saved_amount_paise: int = 0

    @property
    def formatted_target(self) -> str:
        return format_currency(self.target_amount_paise)

    @property
    def formatted_saved(self) -> str:
        return format_currency(self.saved_amount_paise)


@dataclass
class GoalContribution:
    """Represents an individual contribution towards a financial goal."""
    id: Optional[int]
    goal_id: int
    amount_paise: int
    contribution_date: str  # YYYY-MM-DD
    note: str = ""

    @property
    def formatted_amount(self) -> str:
        return format_currency(self.amount_paise)
