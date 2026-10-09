"""
test_ui.py - Automated Headless Smoke & Navigation Tests for Ledger Tkinter UI.
"""

import tkinter as tk
import pytest

from services import FinanceService
from ui import LedgerApp, TransactionDialog, AccountDialog, BudgetDialog, RecurringDialog, GoalDialog


@pytest.fixture
def test_app(tmp_path):
    db_file = str(tmp_path / "test_ui.db")
    service = FinanceService(db_file)
    service.demo.load_demo_data()

    root = tk.Tk()
    root.withdraw()  # Hide window during automated test
    app = LedgerApp(root, service)
    yield app
    try:
        root.destroy()
    except Exception:
        pass


class TestUIFlows:
    def test_page_navigation_and_refresh(self, test_app: LedgerApp):
        """Verify all 8 pages mount and refresh without error."""
        pages = [
            "Dashboard",
            "Transactions",
            "Accounts",
            "Budgets",
            "Recurring",
            "Goals",
            "Reports",
            "Settings",
        ]
        for page_name in pages:
            test_app.navigate_to(page_name)
            assert test_app.current_page_name == page_name
            # Force pending Tk events
            test_app.root.update_idletasks()

    def test_theme_toggle(self, test_app: LedgerApp):
        """Verify dark/light theme switching reconstructs cleanly."""
        assert test_app.is_dark_theme is True
        test_app.toggle_theme()
        assert test_app.is_dark_theme is False
        test_app.root.update_idletasks()

        test_app.toggle_theme()
        assert test_app.is_dark_theme is True
        test_app.root.update_idletasks()

    def test_dialogs_instantiation(self, test_app: LedgerApp):
        """Verify modal dialogs can be constructed and destroyed without error."""
        d1 = TransactionDialog(test_app, initial_type="expense")
        d1.destroy()

        d2 = TransactionDialog(test_app, initial_type="transfer")
        d2.destroy()

        d3 = AccountDialog(test_app)
        d3.destroy()

        d4 = BudgetDialog(test_app, month="2026-06")
        d4.destroy()

        d5 = RecurringDialog(test_app)
        d5.destroy()

        d6 = GoalDialog(test_app)
        d6.destroy()
