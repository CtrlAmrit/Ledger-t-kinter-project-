"""
test_transactions.py - Integration and service tests for Ledger database operations.
"""

from datetime import date
from pathlib import Path
import pytest

from database import Database
from services import (
    FinanceService,
    AccountService,
    CategoryService,
    TransactionService,
    BudgetService,
    RecurringService,
    GoalService,
)


@pytest.fixture
def service(tmp_path):
    """Provides a fresh FinanceService backed by a clean temporary database."""
    db_file = tmp_path / "test_ledger.db"
    return FinanceService(str(db_file))


class TestAccountOperations:
    def test_create_and_fetch_account(self, service: FinanceService):
        acct_id = service.accounts.create_account("HDFC Bank", "Bank", 500000)
        account = service.accounts.get_account(acct_id)
        assert account is not None
        assert account.name == "HDFC Bank"
        assert account.account_type == "Bank"
        assert account.opening_balance_paise == 500000
        assert account.is_active

    def test_account_toggle_active(self, service: FinanceService):
        acct_id = service.accounts.create_account("Old Bank", "Bank", 0)
        assert service.accounts.get_account(acct_id).is_active
        is_active = service.accounts.toggle_active(acct_id)
        assert not is_active
        assert not service.accounts.get_account(acct_id).is_active

    def test_unique_account_name(self, service: FinanceService):
        service.accounts.create_account("Unique Name", "Bank", 0)
        with pytest.raises(Exception):
            service.accounts.create_account("unique name", "Cash", 0)


class TestTransactionsAndBalances:
    def test_income_and_expense_balances(self, service: FinanceService):
        acct_id = service.accounts.create_account("Main Checking", "Bank", 100000)  # ₹1,000

        # Add Income ₹2,000
        service.transactions.create_income_or_expense(
            account_id=acct_id,
            amount_paise=200000,
            transaction_type="income",
            transaction_date="2026-06-01",
            note="Bonus",
        )
        assert service.accounts.get_account_balance(acct_id) == 300000  # ₹3,000

        # Add Expense ₹500
        service.transactions.create_income_or_expense(
            account_id=acct_id,
            amount_paise=50000,
            transaction_type="expense",
            transaction_date="2026-06-02",
            note="Groceries",
        )
        assert service.accounts.get_account_balance(acct_id) == 250000  # ₹2,500


class TestTransfers:
    def test_atomic_transfer_balances_and_net_worth(self, service: FinanceService):
        src_id = service.accounts.create_account("Bank", "Bank", 1000000)  # ₹10,000
        dst_id = service.accounts.create_account("Cash", "Cash", 200000)   # ₹2,000

        # Initial Net worth: ₹12,000
        nw_before = service.analytics.get_net_worth()
        assert nw_before.net_worth_paise == 1200000

        # Transfer ₹3,000 from Bank to Cash
        group_id = service.transactions.create_transfer(
            source_account_id=src_id,
            destination_account_id=dst_id,
            amount_paise=300000,
            transaction_date="2026-06-05",
            note="ATM",
        )
        assert group_id is not None

        # Check balances
        assert service.accounts.get_account_balance(src_id) == 700000  # ₹7,000
        assert service.accounts.get_account_balance(dst_id) == 500000  # ₹5,000

        # Transfer does NOT affect net worth
        nw_after = service.analytics.get_net_worth()
        assert nw_after.net_worth_paise == 1200000

        # Transfer does NOT affect income or expenses
        summary = service.analytics.get_monthly_summary("2026-06")
        assert summary.income_paise == 0
        assert summary.expense_paise == 0

    def test_transfer_to_same_account_fails(self, service: FinanceService):
        acct_id = service.accounts.create_account("Same Account", "Bank", 500000)
        with pytest.raises(ValueError):
            service.transactions.create_transfer(
                source_account_id=acct_id,
                destination_account_id=acct_id,
                amount_paise=10000,
                transaction_date="2026-06-01",
            )

    def test_delete_transfer_removes_both_sides(self, service: FinanceService):
        src_id = service.accounts.create_account("Source", "Bank", 1000000)
        dst_id = service.accounts.create_account("Dest", "Cash", 0)

        service.transactions.create_transfer(src_id, dst_id, 400000, "2026-06-01", "Trip")
        trans_list = service.transactions.search_transactions(account_id=src_id)
        assert len(trans_list) == 1
        transfer_tx = trans_list[0]

        # Delete from source side
        service.transactions.delete_transaction(transfer_tx.id)

        # Both sides should now be gone
        assert len(service.transactions.search_transactions(account_id=src_id)) == 0
        assert len(service.transactions.search_transactions(account_id=dst_id)) == 0
        # Balances restored
        assert service.accounts.get_account_balance(src_id) == 1000000
        assert service.accounts.get_account_balance(dst_id) == 0


class TestBudgets:
    def test_budget_spending_and_transfers_excluded(self, service: FinanceService):
        acct_id = service.accounts.create_account("Bank", "Bank", 5000000)
        cat_id = service.categories.get_or_create_category("Dining", "expense")

        # Set budget ₹5,000 for month
        service.budgets.set_budget("2026-07", cat_id, 500000)

        # Add expense of ₹2,500
        service.transactions.create_income_or_expense(
            account_id=acct_id,
            amount_paise=250000,
            transaction_type="expense",
            transaction_date="2026-07-10",
            category_id=cat_id,
            note="Dinner",
        )

        budgets = service.budgets.get_budgets_for_month("2026-07")
        assert len(budgets) == 1
        budget, status = budgets[0]
        assert status.limit_paise == 500000
        assert status.spent_paise == 250000
        assert status.remaining_paise == 250000
        assert status.percentage_used == 50.0
        assert not status.is_warning
        assert not status.is_exceeded


class TestRecurringTransactions:
    def test_process_due_recurring_and_prevent_duplicate(self, service: FinanceService):
        acct_id = service.accounts.create_account("Bank", "Bank", 1000000)
        cat_id = service.categories.get_or_create_category("Broadband", "expense")

        # Create recurring transaction due today
        today_str = date.today().isoformat()
        rec_id = service.recurring.create_recurring(
            account_id=acct_id,
            amount_paise=99900,  # ₹999
            transaction_type="expense",
            frequency="monthly",
            next_run_date=today_str,
            category_id=cat_id,
            merchant_name="ACT Fibernet",
            note="WiFi",
        )

        # Process due transactions
        created = service.recurring.process_due_transactions()
        assert created == 1
        assert service.accounts.get_account_balance(acct_id) == 1000000 - 99900

        # Processing again immediately should NOT create duplicate transactions
        created_again = service.recurring.process_due_transactions()
        assert created_again == 0

        # Next run date should have advanced to next month
        all_rec = service.recurring.get_all_recurring()
        assert len(all_rec) == 1
        assert all_rec[0].next_run_date > today_str


class TestDemoData:
    def test_load_and_clear_demo_data(self, service: FinanceService):
        service.demo.load_demo_data()

        accounts = service.accounts.get_all_accounts()
        assert len(accounts) >= 4

        transactions = service.transactions.search_transactions()
        assert len(transactions) > 10

        goals = service.goals.get_all_goals()
        assert len(goals) >= 2

        # Clear demo data
        service.demo.clear_all_data()
        assert len(service.accounts.get_all_accounts()) == 0
        assert len(service.transactions.search_transactions()) == 0
        assert len(service.goals.get_all_goals()) == 0


class TestExport:
    def test_export_csv_and_pdf(self, service: FinanceService, tmp_path):
        service.demo.load_demo_data()
        transactions = service.transactions.search_transactions()
        assert len(transactions) > 0

        # Test CSV export
        from export import ExportService
        csv_file = str(tmp_path / "transactions.csv")
        out_csv = ExportService.export_transactions_to_csv(transactions, csv_file)
        assert Path(out_csv).exists()
        assert Path(out_csv).stat().st_size > 100

        # Test PDF export
        curr_month = date.today().strftime("%Y-%m")
        summary = service.analytics.get_monthly_summary(curr_month)
        net_worth = service.analytics.get_net_worth()
        category_spending = service.analytics.get_category_spending(f"{curr_month}-01", f"{curr_month}-31")

        pdf_file = str(tmp_path / "report.pdf")
        out_pdf = ExportService.generate_pdf_report(
            filepath=pdf_file,
            period_label="Current Month",
            summary=summary,
            net_worth=net_worth,
            category_spending=category_spending,
            recent_transactions=transactions[:10],
        )
        assert Path(out_pdf).exists()
        assert Path(out_pdf).stat().st_size > 1000
