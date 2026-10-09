"""
test_calculations.py - Unit tests for pure financial calculations.
"""

from datetime import date
from decimal import Decimal
import pytest

from calculations import (
    rupees_to_paise,
    paise_to_rupees,
    format_currency,
    calculate_savings_rate,
    calculate_budget_usage,
    calculate_net_worth,
    calculate_goal_metrics,
)


class TestMoneyConversions:
    def test_rupees_to_paise_integer(self):
        assert rupees_to_paise(100) == 10000
        assert rupees_to_paise(0) == 0
        assert rupees_to_paise(-50) == -5000

    def test_rupees_to_paise_float(self):
        assert rupees_to_paise(1234.56) == 123456
        assert rupees_to_paise(0.05) == 5
        assert rupees_to_paise(99.999) == 10000  # rounds up

    def test_rupees_to_paise_string_with_symbols_and_commas(self):
        assert rupees_to_paise("₹1,234.56") == 123456
        assert rupees_to_paise(" 5,000 ") == 500000
        assert rupees_to_paise("₹ 10.50") == 1050
        assert rupees_to_paise("-₹500.25") == -50025

    def test_rupees_to_paise_decimal(self):
        assert rupees_to_paise(Decimal("450.75")) == 45075

    def test_rupees_to_paise_invalid_input(self):
        with pytest.raises(ValueError):
            rupees_to_paise("abc")
        with pytest.raises(ValueError):
            rupees_to_paise("")
        with pytest.raises(ValueError):
            rupees_to_paise("₹")

    def test_paise_to_rupees(self):
        assert paise_to_rupees(123456) == Decimal("1234.56")
        assert paise_to_rupees(0) == Decimal("0.00")
        assert paise_to_rupees(-500) == Decimal("-5.00")

    def test_format_currency_indian_format(self):
        assert format_currency(123456) == "₹1,234.56"
        assert format_currency(123456789) == "₹12,34,567.89"
        assert format_currency(0) == "₹0.00"
        assert format_currency(-5000) == "-₹50.00"
        assert format_currency(5000, include_sign=True) == "+₹50.00"


class TestSavingsRate:
    def test_normal_savings_rate(self):
        # Income 1,00,000, Expense 40,000 -> 60%
        rate = calculate_savings_rate(10000000, 4000000)
        assert rate == 60.0

    def test_zero_income(self):
        assert calculate_savings_rate(0, 50000) == 0.0

    def test_expenses_exceed_income(self):
        # Income 10,000, Expense 15,000 -> -50%
        rate = calculate_savings_rate(1000000, 1500000)
        assert rate == -50.0


class TestBudgetCalculations:
    def test_budget_on_track(self):
        status = calculate_budget_usage(limit_paise=1000000, spent_paise=500000, category_name="Food")
        assert status.percentage_used == 50.0
        assert status.remaining_paise == 500000
        assert not status.is_warning
        assert not status.is_exceeded

    def test_budget_warning_threshold(self):
        # 85% spent -> warning
        status = calculate_budget_usage(limit_paise=1000000, spent_paise=850000, category_name="Dining")
        assert status.percentage_used == 85.0
        assert status.is_warning
        assert not status.is_exceeded

    def test_budget_exceeded(self):
        # 110% spent -> exceeded
        status = calculate_budget_usage(limit_paise=1000000, spent_paise=1100000, category_name="Shopping")
        assert status.percentage_used == 110.0
        assert status.remaining_paise == -100000
        assert status.is_exceeded

    def test_zero_budget(self):
        status = calculate_budget_usage(limit_paise=0, spent_paise=50000)
        assert status.is_exceeded


class TestNetWorthCalculations:
    def test_net_worth_assets_and_liabilities(self):
        accounts = [
            ("Bank", 2500000),       # 25,000 Asset
            ("Cash", 500000),        # 5,000 Asset
            ("Savings", 10000000),   # 1,00,000 Asset
            ("Credit Card", -1500000) # 15,000 Debt
        ]
        nw = calculate_net_worth(accounts)
        assert nw.total_assets_paise == 13000000
        assert nw.total_liabilities_paise == 1500000
        assert nw.net_worth_paise == 11500000

    def test_net_worth_all_debt(self):
        accounts = [("Credit Card", -500000)]
        nw = calculate_net_worth(accounts)
        assert nw.total_assets_paise == 0
        assert nw.total_liabilities_paise == 500000
        assert nw.net_worth_paise == -500000


class TestGoalMetrics:
    def test_goal_progress(self):
        metrics = calculate_goal_metrics(
            target_paise=1000000,
            saved_paise=400000,
            target_date_str="2026-12-31",
            current_date=date(2026, 6, 1)
        )
        assert metrics.target_paise == 1000000
        assert metrics.saved_paise == 400000
        assert metrics.remaining_paise == 600000
        assert metrics.percentage_completed == 40.0
        assert metrics.months_remaining == 6
        assert metrics.required_monthly_paise == 100000
        assert not metrics.is_achieved

    def test_goal_achieved(self):
        metrics = calculate_goal_metrics(
            target_paise=500000,
            saved_paise=500000,
            target_date_str="2026-10-01",
            current_date=date(2026, 6, 1)
        )
        assert metrics.is_achieved
        assert metrics.percentage_completed == 100.0
        assert metrics.remaining_paise == 0
        assert metrics.required_monthly_paise == 0
