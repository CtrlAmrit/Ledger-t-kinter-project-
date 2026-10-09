"""
calculations.py - Pure financial calculations for Ledger.

Rules:
1. Money is strictly calculated using integer paise (1 Rupee = 100 Paise).
2. Pure mathematical logic without UI dependencies or direct SQL queries.
3. Deterministic, easily unit-tested, and resilient to edge cases.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Sequence


# =====================================================================
# MONEY CONVERSION & FORMATTING HELPERS
# =====================================================================

def rupees_to_paise(amount: int | float | str | Decimal) -> int:
    """
    Convert a rupee value (string, float, int, or Decimal) into integer paise.
    Rounds to nearest whole paisa using standard half-up rounding.
    Raises ValueError on invalid numerical formats.
    """
    if isinstance(amount, int):
        return amount * 100

    if isinstance(amount, float):
        # Convert float to string first to avoid floating point precision artifacts
        amount_str = f"{amount:.4f}"
    elif isinstance(amount, Decimal):
        amount_str = str(amount)
    else:
        amount_str = str(amount).strip()

    # Clean out currency symbols and whitespace
    clean_str = re.sub(r"[^\d.-]", "", amount_str)
    if not clean_str or clean_str in ("-", ".", "-."):
        raise ValueError(f"Invalid monetary value: '{amount}'")

    try:
        dec = Decimal(clean_str)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value: '{amount}'") from exc

    # Multiply by 100 and quantize to 1
    paise_dec = (dec * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise_dec)


def paise_to_rupees(paise: int) -> Decimal:
    """Convert integer paise to Decimal rupees."""
    if not isinstance(paise, int):
        raise TypeError(f"Paise must be an integer, got {type(paise).__name__}")
    return Decimal(paise) / Decimal(100)


def format_currency(paise: int, symbol: str = "₹", include_sign: bool = False) -> str:
    """
    Format integer paise into a clean, human-readable Indian currency string.
    Example: 123456 paise -> "₹1,234.56"
             -5000 paise  -> "-₹50.00" (or "-₹50.00" if include_sign=False)
             +5000 paise with include_sign=True -> "+₹50.00"
    """
    if not isinstance(paise, int):
        try:
            paise = int(paise)
        except (ValueError, TypeError):
            paise = 0

    is_negative = paise < 0
    abs_paise = abs(paise)
    rupees_part = abs_paise // 100
    paise_part = abs_paise % 100

    # Format rupees part according to Indian numbering system (e.g. 12,34,567)
    s = str(rupees_part)
    if len(s) <= 3:
        formatted_rupees = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        # Group rest by 2 digits from right to left
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_rupees = ",".join(groups) + "," + last3

    formatted_value = f"{symbol}{formatted_rupees}.{paise_part:02d}"

    if is_negative:
        return f"-{formatted_value}"
    if include_sign and paise > 0:
        return f"+{formatted_value}"
    return formatted_value


# =====================================================================
# DATA TRANSFER OBJECTS (DATA CONTRACTS)
# =====================================================================

@dataclass(frozen=True)
class MonthlySummary:
    """Summary of cashflow metrics for a given period."""
    income_paise: int
    expense_paise: int
    net_savings_paise: int
    savings_rate_percent: float
    transaction_count: int

    @property
    def income_rupees(self) -> str:
        return format_currency(self.income_paise)

    @property
    def expense_rupees(self) -> str:
        return format_currency(self.expense_paise)

    @property
    def net_savings_rupees(self) -> str:
        return format_currency(self.net_savings_paise, include_sign=True)

    @property
    def savings_rate_formatted(self) -> str:
        return f"{self.savings_rate_percent:.1f}%"


@dataclass(frozen=True)
class BudgetStatus:
    """Status evaluation of a category budget."""
    category_id: int
    category_name: str
    limit_paise: int
    spent_paise: int
    remaining_paise: int
    percentage_used: float
    is_warning: bool
    is_exceeded: bool

    @property
    def limit_rupees(self) -> str:
        return format_currency(self.limit_paise)

    @property
    def spent_rupees(self) -> str:
        return format_currency(self.spent_paise)

    @property
    def remaining_rupees(self) -> str:
        return format_currency(self.remaining_paise)

    @property
    def percentage_formatted(self) -> str:
        return f"{self.percentage_used:.1f}%"


@dataclass(frozen=True)
class NetWorthSummary:
    """Summary of assets, liabilities, and total net worth."""
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int

    @property
    def total_assets_rupees(self) -> str:
        return format_currency(self.total_assets_paise)

    @property
    def total_liabilities_rupees(self) -> str:
        return format_currency(self.total_liabilities_paise)

    @property
    def net_worth_rupees(self) -> str:
        return format_currency(self.net_worth_paise)


@dataclass(frozen=True)
class GoalMetrics:
    """Financial goal tracking calculations."""
    target_paise: int
    saved_paise: int
    remaining_paise: int
    percentage_completed: float
    months_remaining: int
    required_monthly_paise: int
    is_achieved: bool

    @property
    def target_rupees(self) -> str:
        return format_currency(self.target_paise)

    @property
    def saved_rupees(self) -> str:
        return format_currency(self.saved_paise)

    @property
    def remaining_rupees(self) -> str:
        return format_currency(self.remaining_paise)

    @property
    def required_monthly_rupees(self) -> str:
        return format_currency(self.required_monthly_paise)

    @property
    def percentage_formatted(self) -> str:
        return f"{self.percentage_completed:.1f}%"


# =====================================================================
# CALCULATION FUNCTIONS
# =====================================================================

def calculate_savings_rate(income_paise: int, expense_paise: int) -> float:
    """
    Calculate the savings rate percentage: ((income - expense) / income) * 100.
    Returns 0.0 if income is zero or negative.
    Can be negative if expenses exceed income.
    """
    if income_paise <= 0:
        return 0.0
    net_savings = income_paise - expense_paise
    rate = (net_savings / income_paise) * 100.0
    return round(rate, 2)


def calculate_budget_usage(limit_paise: int, spent_paise: int, category_id: int = 0, category_name: str = "") -> BudgetStatus:
    """
    Evaluate budget performance for a given category.
    Warning triggers at >= 80% and < 100%. Exceeded triggers at >= 100%.
    """
    spent_paise = max(0, spent_paise)
    remaining_paise = limit_paise - spent_paise

    if limit_paise <= 0:
        percentage_used = 100.0 if spent_paise > 0 else 0.0
    else:
        percentage_used = (spent_paise / limit_paise) * 100.0

    is_warning = (percentage_used >= 80.0) and (percentage_used < 100.0)
    is_exceeded = percentage_used >= 100.0

    return BudgetStatus(
        category_id=category_id,
        category_name=category_name,
        limit_paise=limit_paise,
        spent_paise=spent_paise,
        remaining_paise=remaining_paise,
        percentage_used=round(percentage_used, 1),
        is_warning=is_warning,
        is_exceeded=is_exceeded,
    )


def calculate_net_worth(account_balances: Sequence[tuple[str, int]]) -> NetWorthSummary:
    """
    Calculate Net Worth given a sequence of (account_type, balance_paise).
    Assets = Positive balances in asset accounts (Bank, Cash, Savings, Other)
    Liabilities = Absolute balance of Credit Card (if negative or debt) + any negative account balances
    Net Worth = Total Assets - Total Liabilities
    """
    total_assets = 0
    total_liabilities = 0

    for acct_type, balance in account_balances:
        is_credit = acct_type.lower() in ("credit card", "credit", "liability", "loan")
        if is_credit:
            # For credit cards, if balance < 0, it is debt
            if balance < 0:
                total_liabilities += abs(balance)
            else:
                # Positive balance on credit card is credit/asset
                total_assets += balance
        else:
            if balance >= 0:
                total_assets += balance
            else:
                # Overdrawn asset account acts as liability
                total_liabilities += abs(balance)

    net_worth = total_assets - total_liabilities
    return NetWorthSummary(
        total_assets_paise=total_assets,
        total_liabilities_paise=total_liabilities,
        net_worth_paise=net_worth,
    )


def calculate_goal_metrics(target_paise: int, saved_paise: int, target_date_str: str, current_date: date | None = None) -> GoalMetrics:
    """
    Compute progress, remaining amount, and required monthly savings for a financial goal.
    """
    if current_date is None:
        current_date = date.today()

    target_paise = max(0, target_paise)
    saved_paise = max(0, saved_paise)
    remaining_paise = max(0, target_paise - saved_paise)
    is_achieved = saved_paise >= target_paise and target_paise > 0

    if target_paise == 0:
        percentage_completed = 100.0 if saved_paise >= 0 else 0.0
    else:
        percentage_completed = min(100.0, (saved_paise / target_paise) * 100.0)

    # Parse target date
    try:
        target_d = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        target_d = current_date

    # Months remaining calculation
    year_diff = target_d.year - current_date.year
    month_diff = target_d.month - current_date.month
    total_months = year_diff * 12 + month_diff

    # If target day is earlier in month, handle gracefully
    if total_months < 0:
        months_remaining = 0
    else:
        months_remaining = total_months

    if is_achieved or remaining_paise == 0:
        required_monthly = 0
    elif months_remaining <= 0:
        # Due now or past due: entire remaining amount needed
        required_monthly = remaining_paise
    else:
        required_monthly = (remaining_paise + months_remaining - 1) // months_remaining

    return GoalMetrics(
        target_paise=target_paise,
        saved_paise=saved_paise,
        remaining_paise=remaining_paise,
        percentage_completed=round(percentage_completed, 1),
        months_remaining=months_remaining,
        required_monthly_paise=required_monthly,
        is_achieved=is_achieved,
    )
