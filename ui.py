"""
ui.py - Main Desktop User Interface for Ledger.

Implements a desktop personal finance application using Tkinter and ttk.
Features:
- Professional sidebar navigation with responsive content panels
- Modern Dark and Light themes with consistent typography and colors
- 8 Complete Pages: Dashboard, Transactions, Accounts, Budgets, Recurring, Goals, Reports, Settings
- Reusable, validated dialogs for Transactions, Accounts, Budgets, Recurring, Goals, and Contributions
- Zero SQL in UI code; pure interaction with FinanceService and models
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Callable, Any

from calculations import format_currency, paise_to_rupees, rupees_to_paise
from charts import LedgerCharts
from export import ExportService
from models import Account, Transaction, Budget, RecurringTransaction, FinancialGoal
from services import FinanceService


# =====================================================================
# THEME CONFIGURATION
# =====================================================================

class UITheme:
    DARK = {
        "is_dark": True,
        "bg_app": "#0F172A",       # Slate 900
        "bg_sidebar": "#111827",   # Gray 900
        "bg_card": "#1E293B",      # Slate 800
        "bg_hover": "#334155",     # Slate 700
        "border": "#334155",
        "text_primary": "#F8FAFC",
        "text_secondary": "#94A3B8",
        "text_muted": "#64748B",
        "accent": "#10B981",       # Emerald 500
        "accent_hover": "#059669",
        "accent_text": "#FFFFFF",
        "danger": "#EF4444",
        "warning": "#F59E0B",
        "info": "#3B82F6",
        "tree_bg": "#1E293B",
        "tree_fg": "#F8FAFC",
        "tree_selected": "#0F766E", # Dark teal
        "input_bg": "#0F172A",
        "input_fg": "#F8FAFC",
    }

    LIGHT = {
        "is_dark": False,
        "bg_app": "#F1F5F9",       # Slate 100
        "bg_sidebar": "#FFFFFF",
        "bg_card": "#FFFFFF",
        "bg_hover": "#E2E8F0",
        "border": "#CBD5E1",
        "text_primary": "#0F172A",
        "text_secondary": "#475569",
        "text_muted": "#94A3B8",
        "accent": "#059669",       # Emerald 600
        "accent_hover": "#047857",
        "accent_text": "#FFFFFF",
        "danger": "#DC2626",
        "warning": "#D97706",
        "info": "#2563EB",
        "tree_bg": "#FFFFFF",
        "tree_fg": "#0F172A",
        "tree_selected": "#CCFBF1", # Soft teal
        "input_bg": "#FFFFFF",
        "input_fg": "#0F172A",
    }


# =====================================================================
# BASE PAGE (POLYMORPHISM / OOP INTERFACE)
# =====================================================================

class BasePage(ttk.Frame):
    """Base class for all application pages providing consistent lifecycle hooks."""
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent)
        self.app = app
        self.service = app.service

    @property
    def theme(self) -> dict[str, Any]:
        return self.app.theme

    def refresh(self) -> None:
        """Subclasses override this to reload their data when navigated to."""
        pass


# =====================================================================
# 1. DASHBOARD PAGE
# =====================================================================

class DashboardPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self.chart_canvas1 = None
        self.chart_canvas2 = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Scrollable container for smaller screens
        self.scroll_canvas = tk.Canvas(self, bg=self.theme["bg_app"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll_canvas.yview)
        self.content_frame = tk.Frame(self.scroll_canvas, bg=self.theme["bg_app"])

        self.content_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        )
        self.canvas_window = self.scroll_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # KPI Metrics Cards Row
        self.kpi_container = tk.Frame(self.content_frame, bg=self.theme["bg_app"])
        self.kpi_container.pack(fill="x", padx=24, pady=(20, 16))

        self.kpi_cards = {}
        metrics = [
            ("net_worth", "NET WORTH", "₹0.00", self.theme["text_primary"]),
            ("total_balance", "TOTAL BALANCE", "₹0.00", self.theme["info"]),
            ("income", "MONTHLY INCOME", "₹0.00", self.theme["accent"]),
            ("expenses", "MONTHLY EXPENSES", "₹0.00", self.theme["danger"]),
            ("savings", "SAVINGS (RATE)", "₹0.00 (0%)", self.theme["accent"]),
        ]
        for idx, (key, title, default_val, val_color) in enumerate(metrics):
            card = tk.Frame(self.kpi_container, bg=self.theme["bg_card"], padx=16, pady=12,
                            highlightbackground=self.theme["border"], highlightthickness=1)
            card.grid(row=0, column=idx, padx=6, sticky="nsew")
            self.kpi_container.columnconfigure(idx, weight=1)

            lbl_title = tk.Label(card, text=title, font=("Segoe UI", 8, "bold"),
                                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"])
            lbl_title.pack(anchor="w")

            lbl_val = tk.Label(card, text=default_val, font=("Segoe UI", 14, "bold"),
                               bg=self.theme["bg_card"], fg=val_color)
            lbl_val.pack(anchor="w", pady=(6, 0))
            self.kpi_cards[key] = lbl_val

        # Main Body: 2 Columns
        body_frame = tk.Frame(self.content_frame, bg=self.theme["bg_app"])
        body_frame.pack(fill="both", expand=True, padx=24, pady=8)
        body_frame.columnconfigure(0, weight=6)
        body_frame.columnconfigure(1, weight=5)

        # Left Column: Cashflow Chart & Budgets Preview
        left_col = tk.Frame(body_frame, bg=self.theme["bg_app"])
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Cashflow Chart Container
        chart_card = tk.Frame(left_col, bg=self.theme["bg_card"], padx=14, pady=12,
                              highlightbackground=self.theme["border"], highlightthickness=1)
        chart_card.pack(fill="x", pady=(0, 16))
        tk.Label(chart_card, text="Income vs Expense (6 Months)", font=("Segoe UI", 11, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.cashflow_chart_frame = tk.Frame(chart_card, bg=self.theme["bg_card"])
        self.cashflow_chart_frame.pack(fill="both", expand=True)

        # Active Budgets Alert Box
        self.budget_box = tk.Frame(left_col, bg=self.theme["bg_card"], padx=14, pady=12,
                                   highlightbackground=self.theme["border"], highlightthickness=1)
        self.budget_box.pack(fill="x")
        tk.Label(self.budget_box, text="Current Month Budget Alerts", font=("Segoe UI", 11, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.budget_items_frame = tk.Frame(self.budget_box, bg=self.theme["bg_card"])
        self.budget_items_frame.pack(fill="x")

        # Right Column: Category Donut & Recent Transactions
        right_col = tk.Frame(body_frame, bg=self.theme["bg_app"])
        right_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Category Donut Chart Container
        donut_card = tk.Frame(right_col, bg=self.theme["bg_card"], padx=14, pady=12,
                              highlightbackground=self.theme["border"], highlightthickness=1)
        donut_card.pack(fill="x", pady=(0, 16))
        tk.Label(donut_card, text="Spending by Category", font=("Segoe UI", 11, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.donut_chart_frame = tk.Frame(donut_card, bg=self.theme["bg_card"])
        self.donut_chart_frame.pack(fill="both", expand=True)

        # Recent Transactions Mini Table
        recent_card = tk.Frame(right_col, bg=self.theme["bg_card"], padx=14, pady=12,
                               highlightbackground=self.theme["border"], highlightthickness=1)
        recent_card.pack(fill="both", expand=True)
        rec_hdr = tk.Frame(recent_card, bg=self.theme["bg_card"])
        rec_hdr.pack(fill="x", pady=(0, 8))
        tk.Label(rec_hdr, text="Recent Transactions", font=("Segoe UI", 11, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(side="left")
        view_all_btn = tk.Button(rec_hdr, text="View All →", font=("Segoe UI", 9),
                                 bg=self.theme["bg_card"], fg=self.theme["accent"],
                                 activebackground=self.theme["bg_card"], activeforeground=self.theme["accent_hover"],
                                 bd=0, cursor="hand2", command=lambda: self.app.navigate_to("Transactions"))
        view_all_btn.pack(side="right")

        self.recent_list_frame = tk.Frame(recent_card, bg=self.theme["bg_card"])
        self.recent_list_frame.pack(fill="both", expand=True)

    def _on_canvas_configure(self, event) -> None:
        self.scroll_canvas.itemconfig(self.canvas_window, width=event.width)

    def refresh(self) -> None:
        curr_month = date.today().strftime("%Y-%m")
        # 1. Update KPIs
        nw = self.service.analytics.get_net_worth()
        self.kpi_cards["net_worth"].config(text=nw.net_worth_rupees)

        # Total active account balance
        acct_balances = self.service.accounts.get_all_account_balances(include_inactive=False)
        total_bal = sum(bal for _, bal in acct_balances)
        self.kpi_cards["total_balance"].config(text=format_currency(total_bal))

        summary = self.service.analytics.get_monthly_summary(curr_month)
        self.kpi_cards["income"].config(text=summary.income_rupees)
        self.kpi_cards["expenses"].config(text=summary.expense_rupees)
        self.kpi_cards["savings"].config(text=f"{summary.net_savings_rupees} ({summary.savings_rate_formatted})")

        # 2. Render Cashflow Bar Chart
        for w in self.cashflow_chart_frame.winfo_children():
            w.destroy()
        cashflow_data = self.service.analytics.get_monthly_cashflow_history(num_months=6)
        canvas1 = LedgerCharts.draw_cashflow_bars(
            self.cashflow_chart_frame,
            cashflow_data,
            is_dark=self.theme["is_dark"],
            figsize=(5.4, 2.7)
        )
        canvas1.get_tk_widget().pack(fill="both", expand=True)

        # 3. Render Category Donut Chart
        for w in self.donut_chart_frame.winfo_children():
            w.destroy()
        start_d = f"{curr_month}-01"
        end_d = f"{curr_month}-31"
        category_spending = self.service.analytics.get_category_spending(start_d, end_d)
        canvas2 = LedgerCharts.draw_category_donut(
            self.donut_chart_frame,
            category_spending,
            is_dark=self.theme["is_dark"],
            figsize=(4.5, 2.7)
        )
        canvas2.get_tk_widget().pack(fill="both", expand=True)

        # 4. Budget Alerts
        for w in self.budget_items_frame.winfo_children():
            w.destroy()
        budgets = self.service.budgets.get_budgets_for_month(curr_month)
        if not budgets:
            tk.Label(self.budget_items_frame, text="No budgets defined for this month. Set one in the Budgets tab.",
                     bg=self.theme["bg_card"], fg=self.theme["text_muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=4)
        else:
            for budget, status in budgets[:4]:
                b_row = tk.Frame(self.budget_items_frame, bg=self.theme["bg_card"])
                b_row.pack(fill="x", pady=3)
                lbl_name = tk.Label(b_row, text=budget.category_name, font=("Segoe UI", 9, "bold"),
                                    bg=self.theme["bg_card"], fg=self.theme["text_primary"])
                lbl_name.pack(side="left")

                badge_color = self.theme["danger"] if status.is_exceeded else (self.theme["warning"] if status.is_warning else self.theme["accent"])
                badge_text = "EXCEEDED" if status.is_exceeded else (f"{status.percentage_formatted} USED" if status.is_warning else f"{status.percentage_formatted}")
                badge = tk.Label(b_row, text=badge_text, font=("Segoe UI", 8, "bold"),
                                 bg=badge_color, fg="#FFFFFF", padx=6, pady=1)
                badge.pack(side="right")

                amt_str = f"{status.spent_rupees} / {status.limit_rupees}"
                tk.Label(b_row, text=amt_str, font=("Segoe UI", 8),
                         bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(side="right", padx=8)

        # 5. Recent Transactions
        for w in self.recent_list_frame.winfo_children():
            w.destroy()
        recent_txs = self.service.transactions.get_recent_transactions(limit=6)
        if not recent_txs:
            tk.Label(self.recent_list_frame, text="No transactions recorded yet.\nClick '+ Add Transaction' to get started.",
                     bg=self.theme["bg_card"], fg=self.theme["text_muted"], font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=10)
        else:
            for tx in recent_txs:
                r_item = tk.Frame(self.recent_list_frame, bg=self.theme["bg_card"])
                r_item.pack(fill="x", pady=4)

                col_left = tk.Frame(r_item, bg=self.theme["bg_card"])
                col_left.pack(side="left", fill="x", expand=True)

                title_text = tx.merchant_name or tx.category_name or tx.note or "Transaction"
                tk.Label(col_left, text=title_text, font=("Segoe UI", 9, "bold"),
                         bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")
                sub_text = f"{tx.transaction_date} • {tx.account_name}"
                tk.Label(col_left, text=sub_text, font=("Segoe UI", 8),
                         bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(anchor="w")

                amt_fg = self.theme["accent"] if tx.is_income else (self.theme["danger"] if tx.is_expense else self.theme["text_secondary"])
                tk.Label(r_item, text=tx.formatted_amount, font=("Segoe UI", 10, "bold"),
                         bg=self.theme["bg_card"], fg=amt_fg).pack(side="right")


# =====================================================================
# 2. TRANSACTIONS PAGE
# =====================================================================

class TransactionsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self.sort_col = "transaction_date"
        self.sort_desc = True
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Action Toolbar (Top)
        toolbar = tk.Frame(container, bg=self.theme["bg_app"])
        toolbar.pack(fill="x", pady=(0, 16))

        # Title
        tk.Label(toolbar, text="Transactions", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        # Action Buttons
        btn_box = tk.Frame(toolbar, bg=self.theme["bg_app"])
        btn_box.pack(side="right")

        self.btn_export = tk.Button(btn_box, text="Export CSV", font=("Segoe UI", 9, "bold"),
                                    bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                                    activebackground=self.theme["bg_hover"], bd=1, padx=12, pady=5,
                                    cursor="hand2", command=self._export_csv)
        self.btn_export.pack(side="left", padx=4)

        self.btn_transfer = tk.Button(btn_box, text="+ Transfer", font=("Segoe UI", 9, "bold"),
                                      bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                                      activebackground=self.theme["bg_hover"], bd=1, padx=12, pady=5,
                                      cursor="hand2", command=lambda: self.app.open_transaction_dialog("transfer"))
        self.btn_transfer.pack(side="left", padx=4)

        self.btn_add = tk.Button(btn_box, text="+ Add Transaction", font=("Segoe UI", 9, "bold"),
                                 bg=self.theme["accent"], fg=self.theme["accent_text"],
                                 activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                                 cursor="hand2", command=lambda: self.app.open_transaction_dialog("expense"))
        self.btn_add.pack(side="left", padx=4)

        # Filters Bar
        filter_card = tk.Frame(container, bg=self.theme["bg_card"], padx=14, pady=10,
                               highlightbackground=self.theme["border"], highlightthickness=1)
        filter_card.pack(fill="x", pady=(0, 12))

        # Search Box
        tk.Label(filter_card, text="Search:", font=("Segoe UI", 8, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=0, sticky="w", padx=4)
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(filter_card, textvariable=self.search_var, font=("Segoe UI", 9),
                                     bg=self.theme["input_bg"], fg=self.theme["input_fg"],
                                     insertbackground=self.theme["text_primary"], bd=1, width=22)
        self.search_entry.grid(row=0, column=1, padx=6)
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        # Account Filter
        tk.Label(filter_card, text="Account:", font=("Segoe UI", 8, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=2, sticky="w", padx=4)
        self.account_var = tk.StringVar(value="All Accounts")
        self.account_combo = ttk.Combobox(filter_card, textvariable=self.account_var, state="readonly", width=18)
        self.account_combo.grid(row=0, column=3, padx=6)
        self.account_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Category Filter
        tk.Label(filter_card, text="Category:", font=("Segoe UI", 8, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=4, sticky="w", padx=4)
        self.category_var = tk.StringVar(value="All Categories")
        self.category_combo = ttk.Combobox(filter_card, textvariable=self.category_var, state="readonly", width=18)
        self.category_combo.grid(row=0, column=5, padx=6)
        self.category_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Type Filter
        tk.Label(filter_card, text="Type:", font=("Segoe UI", 8, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=6, sticky="w", padx=4)
        self.type_var = tk.StringVar(value="All")
        self.type_combo = ttk.Combobox(filter_card, textvariable=self.type_var, state="readonly", width=10,
                                       values=["All", "income", "expense", "transfer"])
        self.type_combo.grid(row=0, column=7, padx=6)
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Reset button
        btn_clear = tk.Button(filter_card, text="Reset", font=("Segoe UI", 8),
                              bg=self.theme["bg_card"], fg=self.theme["text_muted"],
                              activebackground=self.theme["bg_hover"], bd=0, cursor="hand2", command=self._reset_filters)
        btn_clear.grid(row=0, column=8, padx=8)

        # Transactions Table (Treeview)
        table_frame = tk.Frame(container, bg=self.theme["bg_card"],
                               highlightbackground=self.theme["border"], highlightthickness=1)
        table_frame.pack(fill="both", expand=True)

        columns = ("id", "date", "account", "type", "category", "merchant", "note", "amount")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("id", text="ID")
        self.tree.heading("date", text="Date ▲▼", command=lambda: self._sort_by("transaction_date"))
        self.tree.heading("account", text="Account ▲▼", command=lambda: self._sort_by("account_name"))
        self.tree.heading("type", text="Type")
        self.tree.heading("category", text="Category ▲▼", command=lambda: self._sort_by("category_name"))
        self.tree.heading("merchant", text="Merchant / Payee")
        self.tree.heading("note", text="Notes")
        self.tree.heading("amount", text="Amount (₹) ▲▼", command=lambda: self._sort_by("amount_paise"))

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("date", width=95, anchor="center")
        self.tree.column("account", width=150, anchor="w")
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("category", width=130, anchor="w")
        self.tree.column("merchant", width=140, anchor="w")
        self.tree.column("note", width=220, anchor="w")
        self.tree.column("amount", width=110, anchor="e")

        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Double click to edit, Right click to context menu
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Delete>", lambda e: self._delete_selected())

        # Table Action Buttons (Bottom)
        bottom_bar = tk.Frame(container, bg=self.theme["bg_app"])
        bottom_bar.pack(fill="x", pady=(10, 0))

        self.lbl_count = tk.Label(bottom_bar, text="0 transactions found", font=("Segoe UI", 9),
                                  bg=self.theme["bg_app"], fg=self.theme["text_muted"])
        self.lbl_count.pack(side="left")

        btn_del = tk.Button(bottom_bar, text="Delete Selected", font=("Segoe UI", 8, "bold"),
                            bg=self.theme["bg_card"], fg=self.theme["danger"],
                            activebackground=self.theme["bg_hover"], bd=1, padx=10, pady=4,
                            cursor="hand2", command=self._delete_selected)
        btn_del.pack(side="right", padx=4)

        btn_edit = tk.Button(bottom_bar, text="Edit Selected", font=("Segoe UI", 8),
                             bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                             activebackground=self.theme["bg_hover"], bd=1, padx=10, pady=4,
                             cursor="hand2", command=self._edit_selected)
        btn_edit.pack(side="right", padx=4)

    def _sort_by(self, column: str) -> None:
        if self.sort_col == column:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = column
            self.sort_desc = True
        self.refresh()

    def _reset_filters(self) -> None:
        self.search_var.set("")
        self.account_var.set("All Accounts")
        self.category_var.set("All Categories")
        self.type_var.set("All")
        self.refresh()

    def _export_csv(self) -> None:
        txs = self._get_filtered_transactions()
        if not txs:
            messagebox.showinfo("Export CSV", "No transactions match current filters.")
            return

        default_name = f"ledger_transactions_{date.today().strftime('%Y%m%d')}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=default_name,
            title="Export Transactions to CSV"
        )
        if filepath:
            ExportService.export_transactions_to_csv(txs, filepath)
            messagebox.showinfo("Export Successful", f"Exported {len(txs)} transactions to:\n{filepath}")

    def _get_filtered_transactions(self) -> list[Transaction]:
        acct_id = None
        if self.account_var.get() != "All Accounts":
            # Lookup id
            accts = self.service.accounts.get_all_accounts(include_inactive=True)
            for a in accts:
                if a.name == self.account_var.get():
                    acct_id = a.id
                    break

        cat_id = None
        if self.category_var.get() != "All Categories":
            cats = self.service.categories.get_categories(include_inactive=True)
            for c in cats:
                if c.name == self.category_var.get():
                    cat_id = c.id
                    break

        t_type = self.type_var.get()
        if t_type == "All":
            t_type = None

        search_q = self.search_var.get()
        sort_order = "DESC" if self.sort_desc else "ASC"

        return self.service.transactions.search_transactions(
            account_id=acct_id,
            category_id=cat_id,
            transaction_type=t_type,
            search_text=search_q,
            sort_by=self.sort_col,
            sort_order=sort_order,
        )

    def _edit_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Edit Transaction", "Please select a transaction to edit.")
            return
        item_id = int(self.tree.item(sel[0], "values")[0])
        tx = self.service.transactions.get_transaction(item_id)
        if not tx:
            return
        if tx.is_transfer:
            messagebox.showinfo("Transfer Notice", "Transfers are managed as linked pairs. To alter a transfer, delete it and recreate.")
            return
        TransactionDialog(self.app, initial_transaction=tx, on_save=self.refresh)

    def _delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Delete Transaction", "Please select a transaction to delete.")
            return
        item_id = int(self.tree.item(sel[0], "values")[0])
        tx = self.service.transactions.get_transaction(item_id)
        if not tx:
            return

        msg = "Are you sure you want to delete this transaction?"
        if tx.is_transfer:
            msg = "This transaction is part of a transfer pair. Deleting it will remove both sides of the transfer. Proceed?"

        if messagebox.askyesno("Confirm Deletion", msg, icon="warning"):
            self.service.transactions.delete_transaction(item_id)
            self.refresh()

    def _on_double_click(self, event) -> None:
        self._edit_selected()

    def refresh(self) -> None:
        # Populate Comboboxes
        accounts = self.service.accounts.get_all_accounts(include_inactive=True)
        self.account_combo["values"] = ["All Accounts"] + [a.name for a in accounts]

        categories = self.service.categories.get_categories(include_inactive=True)
        self.category_combo["values"] = ["All Categories"] + sorted(list({c.name for c in categories}))

        # Clear Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Configure style tags
        self.tree.tag_configure("income", foreground=self.theme["accent"])
        self.tree.tag_configure("expense", foreground=self.theme["danger"])
        self.tree.tag_configure("transfer", foreground=self.theme["text_secondary"])

        txs = self._get_filtered_transactions()
        for tx in txs:
            row_tag = tx.transaction_type
            self.tree.insert(
                "",
                "end",
                values=(
                    tx.id,
                    tx.transaction_date,
                    tx.account_name,
                    tx.transaction_type.capitalize(),
                    tx.category_name,
                    tx.merchant_name or "-",
                    tx.note,
                    tx.formatted_amount,
                ),
                tags=(row_tag,)
            )

        self.lbl_count.config(text=f"{len(txs)} transactions found")


# =====================================================================
# 3. ACCOUNTS PAGE
# =====================================================================

class AccountsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(container, bg=self.theme["bg_app"])
        hdr.pack(fill="x", pady=(0, 20))

        tk.Label(hdr, text="Accounts", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        btn_add = tk.Button(hdr, text="+ Add Account", font=("Segoe UI", 9, "bold"),
                            bg=self.theme["accent"], fg=self.theme["accent_text"],
                            activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                            cursor="hand2", command=self._add_account)
        btn_add.pack(side="right")

        # Scrollable grid of accounts
        self.canvas = tk.Canvas(container, bg=self.theme["bg_app"], highlightthickness=0)
        self.scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.cards_frame = tk.Frame(self.canvas, bg=self.theme["bg_app"])

        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.win_id = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win_id, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

    def _add_account(self) -> None:
        AccountDialog(self.app, on_save=self.refresh)

    def _edit_account(self, acct: Account) -> None:
        AccountDialog(self.app, initial_account=acct, on_save=self.refresh)

    def _toggle_active(self, acct: Account) -> None:
        action = "deactivate" if acct.is_active else "activate"
        if messagebox.askyesno("Confirm Action", f"Are you sure you want to {action} '{acct.name}'?"):
            self.service.accounts.toggle_active(acct.id)
            self.refresh()

    def refresh(self) -> None:
        for w in self.cards_frame.winfo_children():
            w.destroy()

        acct_pairs = self.service.accounts.get_all_account_balances(include_inactive=True)
        if not acct_pairs:
            tk.Label(self.cards_frame, text="No accounts yet. Click '+ Add Account' to create your first bank or cash account.",
                     font=("Segoe UI", 10), bg=self.theme["bg_app"], fg=self.theme["text_muted"]).pack(pady=20)
            return

        row, col = 0, 0
        for acct, balance in acct_pairs:
            card = tk.Frame(self.cards_frame, bg=self.theme["bg_card"], padx=18, pady=16,
                            highlightbackground=self.theme["border"], highlightthickness=1)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self.cards_frame.columnconfigure(col, weight=1)

            # Card Header: Type Badge & Status
            top_bar = tk.Frame(card, bg=self.theme["bg_card"])
            top_bar.pack(fill="x", pady=(0, 8))

            type_badge = tk.Label(top_bar, text=acct.account_type.upper(), font=("Segoe UI", 8, "bold"),
                                  bg=self.theme["bg_hover"], fg=self.theme["text_secondary"], padx=6, pady=2)
            type_badge.pack(side="left")

            if not acct.is_active:
                inact_badge = tk.Label(top_bar, text="INACTIVE", font=("Segoe UI", 8, "bold"),
                                       bg=self.theme["danger"], fg="#FFFFFF", padx=6, pady=2)
                inact_badge.pack(side="right")

            # Account Name
            tk.Label(card, text=acct.name, font=("Segoe UI", 13, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")

            # Balance Display
            bal_color = self.theme["danger"] if balance < 0 else self.theme["text_primary"]
            tk.Label(card, text=format_currency(balance), font=("Segoe UI", 16, "bold"),
                     bg=self.theme["bg_card"], fg=bal_color).pack(anchor="w", pady=(8, 2))

            # Opening Balance Note
            tk.Label(card, text=f"Opening: {acct.formatted_opening_balance}", font=("Segoe UI", 8),
                     bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(anchor="w")

            # Action Buttons Row
            actions = tk.Frame(card, bg=self.theme["bg_card"])
            actions.pack(fill="x", pady=(14, 0))

            btn_edit = tk.Button(actions, text="Edit", font=("Segoe UI", 8),
                                 bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                                 activebackground=self.theme["border"], bd=0, padx=8, pady=3,
                                 cursor="hand2", command=lambda a=acct: self._edit_account(a))
            btn_edit.pack(side="left", padx=(0, 6))

            status_text = "Deactivate" if acct.is_active else "Activate"
            btn_toggle = tk.Button(actions, text=status_text, font=("Segoe UI", 8),
                                   bg=self.theme["bg_hover"], fg=self.theme["text_secondary"],
                                   activebackground=self.theme["border"], bd=0, padx=8, pady=3,
                                   cursor="hand2", command=lambda a=acct: self._toggle_active(a))
            btn_toggle.pack(side="left")

            col += 1
            if col > 2:
                col = 0
                row += 1


# =====================================================================
# 4. BUDGETS PAGE
# =====================================================================

class BudgetsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self.current_month = date.today().strftime("%Y-%m")
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Header with Month Navigator
        hdr = tk.Frame(container, bg=self.theme["bg_app"])
        hdr.pack(fill="x", pady=(0, 16))

        tk.Label(hdr, text="Monthly Budgets", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        # Month Navigation Controls
        month_nav = tk.Frame(hdr, bg=self.theme["bg_app"])
        month_nav.pack(side="left", padx=24)

        btn_prev = tk.Button(month_nav, text="◀", font=("Segoe UI", 9),
                             bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                             bd=1, padx=8, pady=2, cursor="hand2", command=self._prev_month)
        btn_prev.pack(side="left", padx=2)

        self.lbl_month = tk.Label(month_nav, text=self.current_month, font=("Segoe UI", 11, "bold"),
                                  bg=self.theme["bg_app"], fg=self.theme["text_primary"], width=10)
        self.lbl_month.pack(side="left", padx=4)

        btn_next = tk.Button(month_nav, text="▶", font=("Segoe UI", 9),
                             bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                             bd=1, padx=8, pady=2, cursor="hand2", command=self._next_month)
        btn_next.pack(side="left", padx=2)

        btn_add = tk.Button(hdr, text="+ Set Budget", font=("Segoe UI", 9, "bold"),
                            bg=self.theme["accent"], fg=self.theme["accent_text"],
                            activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                            cursor="hand2", command=self._add_budget)
        btn_add.pack(side="right")

        # Summary Header Box
        self.summary_box = tk.Frame(container, bg=self.theme["bg_card"], padx=16, pady=12,
                                    highlightbackground=self.theme["border"], highlightthickness=1)
        self.summary_box.pack(fill="x", pady=(0, 16))

        self.lbl_summary_stat = tk.Label(self.summary_box, text="", font=("Segoe UI", 11),
                                         bg=self.theme["bg_card"], fg=self.theme["text_primary"])
        self.lbl_summary_stat.pack(anchor="w")

        # Budgets List Container
        self.canvas = tk.Canvas(container, bg=self.theme["bg_app"], highlightthickness=0)
        self.scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.budget_list_frame = tk.Frame(self.canvas, bg=self.theme["bg_app"])

        self.budget_list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.win_id = self.canvas.create_window((0, 0), window=self.budget_list_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win_id, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

    def _prev_month(self) -> None:
        y, m = map(int, self.current_month.split("-"))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
        self.current_month = f"{y:04d}-{m:02d}"
        self.refresh()

    def _next_month(self) -> None:
        y, m = map(int, self.current_month.split("-"))
        m += 1
        if m > 12:
            m = 1
            y += 1
        self.current_month = f"{y:04d}-{m:02d}"
        self.refresh()

    def _add_budget(self) -> None:
        BudgetDialog(self.app, month=self.current_month, on_save=self.refresh)

    def _delete_budget(self, budget_id: int, category_name: str) -> None:
        if messagebox.askyesno("Delete Budget", f"Remove budget limit for '{category_name}' in {self.current_month}?"):
            self.service.budgets.delete_budget(budget_id)
            self.refresh()

    def refresh(self) -> None:
        self.lbl_month.config(text=self.current_month)

        for w in self.budget_list_frame.winfo_children():
            w.destroy()

        budgets = self.service.budgets.get_budgets_for_month(self.current_month)
        if not budgets:
            self.lbl_summary_stat.config(text="No budgets defined for this month.")
            tk.Label(self.budget_list_frame, text="No budgets set for this month.\nClick '+ Set Budget' to establish monthly category limits.",
                     font=("Segoe UI", 10), bg=self.theme["bg_app"], fg=self.theme["text_muted"]).pack(pady=30)
            return

        total_budgeted = sum(b.limit_paise for b, _ in budgets)
        total_spent = sum(s.spent_paise for _, s in budgets)
        total_remaining = total_budgeted - total_spent
        self.lbl_summary_stat.config(
            text=f"Total Budgeted: {format_currency(total_budgeted)}   |   Total Spent: {format_currency(total_spent)}   |   Remaining: {format_currency(total_remaining)}"
        )

        for budget, status in budgets:
            card = tk.Frame(self.budget_list_frame, bg=self.theme["bg_card"], padx=18, pady=14,
                            highlightbackground=self.theme["border"], highlightthickness=1)
            card.pack(fill="x", pady=6)

            # Top Row: Category and Badge
            top_line = tk.Frame(card, bg=self.theme["bg_card"])
            top_line.pack(fill="x")

            tk.Label(top_line, text=budget.category_name, font=("Segoe UI", 11, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(side="left")

            badge_color = self.theme["danger"] if status.is_exceeded else (self.theme["warning"] if status.is_warning else self.theme["accent"])
            badge_text = "EXCEEDED" if status.is_exceeded else (f"{status.percentage_formatted} USED" if status.is_warning else f"{status.percentage_formatted} ON TRACK")
            tk.Label(top_line, text=badge_text, font=("Segoe UI", 8, "bold"),
                     bg=badge_color, fg="#FFFFFF", padx=6, pady=2).pack(side="right")

            # Middle Row: Progress Bar
            pct_clamped = min(100.0, status.percentage_used)
            pbar = ttk.Progressbar(card, orient="horizontal", mode="determinate", value=pct_clamped)
            pbar.pack(fill="x", pady=(10, 6))

            # Bottom Row: Numbers & Delete
            bottom_line = tk.Frame(card, bg=self.theme["bg_card"])
            bottom_line.pack(fill="x")

            stats_str = f"Spent: {status.spent_rupees} of {status.limit_rupees}  •  Remaining: {status.remaining_rupees}"
            tk.Label(bottom_line, text=stats_str, font=("Segoe UI", 9),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(side="left")

            btn_del = tk.Button(bottom_line, text="Remove", font=("Segoe UI", 8),
                                bg=self.theme["bg_card"], fg=self.theme["danger"],
                                activebackground=self.theme["bg_hover"], bd=0, cursor="hand2",
                                command=lambda b_id=budget.id, c_name=budget.category_name: self._delete_budget(b_id, c_name))
            btn_del.pack(side="right")


# =====================================================================
# 5. RECURRING TRANSACTIONS PAGE
# =====================================================================

class RecurringPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(container, bg=self.theme["bg_app"])
        hdr.pack(fill="x", pady=(0, 20))

        tk.Label(hdr, text="Recurring Transactions", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        btn_box = tk.Frame(hdr, bg=self.theme["bg_app"])
        btn_box.pack(side="right")

        self.btn_process = tk.Button(btn_box, text="⚡ Process Due Transactions", font=("Segoe UI", 9, "bold"),
                                     bg=self.theme["info"], fg="#FFFFFF",
                                     activebackground=self.theme["bg_hover"], bd=0, padx=14, pady=6,
                                     cursor="hand2", command=self._process_due)
        self.btn_process.pack(side="left", padx=6)

        btn_add = tk.Button(btn_box, text="+ Add Recurring", font=("Segoe UI", 9, "bold"),
                            bg=self.theme["accent"], fg=self.theme["accent_text"],
                            activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                            cursor="hand2", command=self._add_recurring)
        btn_add.pack(side="left")

        # Table of recurring items
        table_frame = tk.Frame(container, bg=self.theme["bg_card"],
                               highlightbackground=self.theme["border"], highlightthickness=1)
        table_frame.pack(fill="both", expand=True)

        columns = ("id", "type", "frequency", "account", "category", "merchant", "amount", "next_run", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("id", text="ID")
        self.tree.heading("type", text="Type")
        self.tree.heading("frequency", text="Frequency")
        self.tree.heading("account", text="Account")
        self.tree.heading("category", text="Category")
        self.tree.heading("merchant", text="Merchant / Payee")
        self.tree.heading("amount", text="Amount")
        self.tree.heading("next_run", text="Next Run Date")
        self.tree.heading("status", text="Status")

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("frequency", width=100, anchor="center")
        self.tree.column("account", width=160, anchor="w")
        self.tree.column("category", width=140, anchor="w")
        self.tree.column("merchant", width=150, anchor="w")
        self.tree.column("amount", width=110, anchor="e")
        self.tree.column("next_run", width=110, anchor="center")
        self.tree.column("status", width=90, anchor="center")

        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Bottom Bar: Actions
        bottom_bar = tk.Frame(container, bg=self.theme["bg_app"])
        bottom_bar.pack(fill="x", pady=(10, 0))

        self.lbl_due_info = tk.Label(bottom_bar, text="", font=("Segoe UI", 9),
                                     bg=self.theme["bg_app"], fg=self.theme["text_secondary"])
        self.lbl_due_info.pack(side="left")

        btn_del = tk.Button(bottom_bar, text="Delete Selected", font=("Segoe UI", 8, "bold"),
                            bg=self.theme["bg_card"], fg=self.theme["danger"],
                            activebackground=self.theme["bg_hover"], bd=1, padx=10, pady=4,
                            cursor="hand2", command=self._delete_selected)
        btn_del.pack(side="right")

    def _add_recurring(self) -> None:
        RecurringDialog(self.app, on_save=self.refresh)

    def _process_due(self) -> None:
        count = self.service.recurring.process_due_transactions()
        if count > 0:
            messagebox.showinfo("Transactions Processed", f"Successfully created {count} transaction(s) for due recurring schedules.")
        else:
            messagebox.showinfo("No Due Transactions", "All recurring transactions are up to date.")
        self.refresh()
        self.app.update_recurring_badge()

    def _delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Delete Recurring", "Please select an item to delete.")
            return
        rec_id = int(self.tree.item(sel[0], "values")[0])
        if messagebox.askyesno("Confirm Delete", "Delete this recurring transaction template?"):
            self.service.recurring.delete_recurring(rec_id)
            self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        items = self.service.recurring.get_all_recurring(include_inactive=True)
        due_count = 0
        today_d = date.today()

        for item in items:
            is_due = item.is_due(today_d)
            if is_due:
                due_count += 1
            status_text = "DUE NOW" if is_due else ("Active" if item.is_active else "Inactive")
            amt_formatted = f"+{format_currency(item.amount_paise)}" if item.transaction_type == "income" else f"-{format_currency(item.amount_paise)}"

            self.tree.insert(
                "",
                "end",
                values=(
                    item.id,
                    item.transaction_type.capitalize(),
                    item.frequency.capitalize(),
                    item.account_name,
                    item.category_name or "-",
                    item.merchant_name or "-",
                    amt_formatted,
                    item.next_run_date,
                    status_text,
                )
            )

        self.lbl_due_info.config(text=f"{len(items)} templates configured • {due_count} currently due for processing")


# =====================================================================
# 6. FINANCIAL GOALS PAGE
# =====================================================================

class GoalsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(container, bg=self.theme["bg_app"])
        hdr.pack(fill="x", pady=(0, 20))

        tk.Label(hdr, text="Financial Goals", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        btn_add = tk.Button(hdr, text="+ New Goal", font=("Segoe UI", 9, "bold"),
                            bg=self.theme["accent"], fg=self.theme["accent_text"],
                            activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                            cursor="hand2", command=self._add_goal)
        btn_add.pack(side="right")

        # Scrollable Goal Cards
        self.canvas = tk.Canvas(container, bg=self.theme["bg_app"], highlightthickness=0)
        self.scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.cards_frame = tk.Frame(self.canvas, bg=self.theme["bg_app"])

        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.win_id = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win_id, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

    def _add_goal(self) -> None:
        GoalDialog(self.app, on_save=self.refresh)

    def _add_contribution(self, goal: FinancialGoal) -> None:
        ContributionDialog(self.app, goal=goal, on_save=self.refresh)

    def _delete_goal(self, goal_id: int, goal_name: str) -> None:
        if messagebox.askyesno("Delete Goal", f"Are you sure you want to delete goal '{goal_name}'?"):
            self.service.goals.delete_goal(goal_id)
            self.refresh()

    def refresh(self) -> None:
        for w in self.cards_frame.winfo_children():
            w.destroy()

        goal_pairs = self.service.goals.get_all_goals(include_inactive=True)
        if not goal_pairs:
            tk.Label(self.cards_frame, text="No financial goals created yet.\nClick '+ New Goal' to begin tracking savings for milestones.",
                     font=("Segoe UI", 10), bg=self.theme["bg_app"], fg=self.theme["text_muted"]).pack(pady=30)
            return

        for goal, metrics in goal_pairs:
            card = tk.Frame(self.cards_frame, bg=self.theme["bg_card"], padx=20, pady=16,
                            highlightbackground=self.theme["border"], highlightthickness=1)
            card.pack(fill="x", pady=8)

            # Top: Title & Status Badge
            top = tk.Frame(card, bg=self.theme["bg_card"])
            top.pack(fill="x")

            tk.Label(top, text=goal.name, font=("Segoe UI", 12, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(side="left")

            badge_text = "ACHIEVED" if metrics.is_achieved else f"{metrics.percentage_formatted} SAVED"
            badge_color = self.theme["accent"] if metrics.is_achieved else self.theme["info"]
            tk.Label(top, text=badge_text, font=("Segoe UI", 8, "bold"),
                     bg=badge_color, fg="#FFFFFF", padx=8, pady=2).pack(side="right")

            # Progress Bar
            pbar = ttk.Progressbar(card, orient="horizontal", mode="determinate", value=metrics.percentage_completed)
            pbar.pack(fill="x", pady=(10, 8))

            # Amounts Summary Line
            nums_line = tk.Frame(card, bg=self.theme["bg_card"])
            nums_line.pack(fill="x")

            amt_info = f"Saved: {metrics.saved_rupees}  •  Target: {metrics.target_rupees}  •  Remaining: {metrics.remaining_rupees}"
            tk.Label(nums_line, text=amt_info, font=("Segoe UI", 9, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(side="left")

            # Target Date & Required Monthly Savings
            detail_line = tk.Frame(card, bg=self.theme["bg_card"])
            detail_line.pack(fill="x", pady=(6, 10))

            detail_text = f"Target Date: {goal.target_date} ({metrics.months_remaining} months remaining)"
            if not metrics.is_achieved and metrics.required_monthly_paise > 0:
                detail_text += f"   |   Recommended Monthly Savings: {metrics.required_monthly_rupees}/mo"
            tk.Label(detail_line, text=detail_text, font=("Segoe UI", 8),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(side="left")

            # Action Buttons Row
            actions = tk.Frame(card, bg=self.theme["bg_card"])
            actions.pack(fill="x")

            btn_contrib = tk.Button(actions, text="+ Add Contribution", font=("Segoe UI", 8, "bold"),
                                    bg=self.theme["accent"], fg="#FFFFFF",
                                    activebackground=self.theme["accent_hover"], bd=0, padx=10, pady=4,
                                    cursor="hand2", command=lambda g=goal: self._add_contribution(g))
            btn_contrib.pack(side="left", padx=(0, 8))

            btn_del = tk.Button(actions, text="Delete", font=("Segoe UI", 8),
                                bg=self.theme["bg_card"], fg=self.theme["danger"],
                                activebackground=self.theme["bg_hover"], bd=0, cursor="hand2",
                                command=lambda g_id=goal.id, g_name=goal.name: self._delete_goal(g_id, g_name))
            btn_del.pack(side="right")


# =====================================================================
# 7. REPORTS PAGE
# =====================================================================

class ReportsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self.chart_frame1 = None
        self.chart_frame2 = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Scrollable container
        self.canvas = tk.Canvas(self, bg=self.theme["bg_app"], highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=self.theme["bg_app"], padx=24, pady=20)

        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win_id, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        # Header
        hdr = tk.Frame(self.content, bg=self.theme["bg_app"])
        hdr.pack(fill="x", pady=(0, 16))

        tk.Label(hdr, text="Financial Analytics & Reports", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(side="left")

        self.btn_pdf = tk.Button(hdr, text="📄 Export PDF Report", font=("Segoe UI", 9, "bold"),
                                 bg=self.theme["accent"], fg=self.theme["accent_text"],
                                 activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                                 cursor="hand2", command=self._export_pdf)
        self.btn_pdf.pack(side="right")

        # Period Filter
        filter_bar = tk.Frame(self.content, bg=self.theme["bg_card"], padx=14, pady=10,
                              highlightbackground=self.theme["border"], highlightthickness=1)
        filter_bar.pack(fill="x", pady=(0, 16))

        tk.Label(filter_bar, text="Reporting Period:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(side="left", padx=(0, 10))

        self.period_var = tk.StringVar(value="Current Month")
        self.period_combo = ttk.Combobox(filter_bar, textvariable=self.period_var, state="readonly", width=18,
                                         values=["Current Month", "Last Month", "Last 3 Months", "Year to Date"])
        self.period_combo.pack(side="left", padx=4)
        self.period_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # KPI Summary Row
        self.kpis_frame = tk.Frame(self.content, bg=self.theme["bg_app"])
        self.kpis_frame.pack(fill="x", pady=(0, 16))
        self.kpi_labels = {}
        for idx, (key, title, color) in enumerate([
            ("income", "TOTAL INCOME", self.theme["accent"]),
            ("expense", "TOTAL EXPENSES", self.theme["danger"]),
            ("savings", "NET SAVINGS", self.theme["info"]),
            ("rate", "SAVINGS RATE", self.theme["accent"]),
        ]):
            card = tk.Frame(self.kpis_frame, bg=self.theme["bg_card"], padx=16, pady=12,
                            highlightbackground=self.theme["border"], highlightthickness=1)
            card.grid(row=0, column=idx, padx=6, sticky="nsew")
            self.kpis_frame.columnconfigure(idx, weight=1)

            tk.Label(card, text=title, font=("Segoe UI", 8, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w")
            lbl_val = tk.Label(card, text="₹0.00", font=("Segoe UI", 13, "bold"),
                               bg=self.theme["bg_card"], fg=color)
            lbl_val.pack(anchor="w", pady=(4, 0))
            self.kpi_labels[key] = lbl_val

        # Charts Row (Side by side)
        charts_row = tk.Frame(self.content, bg=self.theme["bg_app"])
        charts_row.pack(fill="x", pady=(0, 16))
        charts_row.columnconfigure(0, weight=6)
        charts_row.columnconfigure(1, weight=5)

        card_c1 = tk.Frame(charts_row, bg=self.theme["bg_card"], padx=14, pady=12,
                           highlightbackground=self.theme["border"], highlightthickness=1)
        card_c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(card_c1, text="Monthly Cashflow History", font=("Segoe UI", 10, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.chart_frame1 = tk.Frame(card_c1, bg=self.theme["bg_card"])
        self.chart_frame1.pack(fill="both", expand=True)

        card_c2 = tk.Frame(charts_row, bg=self.theme["bg_card"], padx=14, pady=12,
                           highlightbackground=self.theme["border"], highlightthickness=1)
        card_c2.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(card_c2, text="Category Spending Share", font=("Segoe UI", 10, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.chart_frame2 = tk.Frame(card_c2, bg=self.theme["bg_card"])
        self.chart_frame2.pack(fill="both", expand=True)

        # Net Savings Trend Chart
        trend_card = tk.Frame(self.content, bg=self.theme["bg_card"], padx=14, pady=12,
                              highlightbackground=self.theme["border"], highlightthickness=1)
        trend_card.pack(fill="x", pady=(0, 16))
        tk.Label(trend_card, text="Net Savings Trend", font=("Segoe UI", 10, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 8))
        self.trend_frame = tk.Frame(trend_card, bg=self.theme["bg_card"])
        self.trend_frame.pack(fill="both", expand=True)

    def _get_date_range(self) -> tuple[str, str, str]:
        today = date.today()
        period = self.period_var.get()
        if period == "Last Month":
            first = today.replace(day=1) - timedelta(days=1)
            start_d = first.replace(day=1).isoformat()
            end_d = first.isoformat()
            label = first.strftime("%B %Y")
        elif period == "Last 3 Months":
            start_d = (today - timedelta(days=90)).isoformat()
            end_d = today.isoformat()
            label = "Last 3 Months"
        elif period == "Year to Date":
            start_d = f"{today.year}-01-01"
            end_d = today.isoformat()
            label = f"YTD {today.year}"
        else:  # Current Month
            start_d = f"{today.year:04d}-{today.month:02d}-01"
            end_d = today.isoformat()
            label = today.strftime("%B %Y")
        return start_d, end_d, label

    def _export_pdf(self) -> None:
        start_d, end_d, period_label = self._get_date_range()
        curr_month = date.today().strftime("%Y-%m")
        summary = self.service.analytics.get_monthly_summary(curr_month)
        net_worth = self.service.analytics.get_net_worth()
        cat_spending = self.service.analytics.get_category_spending(start_d, end_d)
        recent_txs = self.service.transactions.search_transactions(limit=15)

        default_file = f"Ledger_Report_{date.today().strftime('%Y%m%d')}.pdf"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")],
            initialfile=default_file,
            title="Export PDF Financial Report"
        )
        if filepath:
            ExportService.generate_pdf_report(
                filepath=filepath,
                period_label=period_label,
                summary=summary,
                net_worth=net_worth,
                category_spending=cat_spending,
                recent_transactions=recent_txs,
            )
            messagebox.showinfo("Report Exported", f"Successfully generated PDF report at:\n{filepath}")

    def refresh(self) -> None:
        start_d, end_d, _ = self._get_date_range()
        curr_month = start_d[:7]

        summary = self.service.analytics.get_monthly_summary(curr_month)
        self.kpi_labels["income"].config(text=summary.income_rupees)
        self.kpi_labels["expense"].config(text=summary.expense_rupees)
        self.kpi_labels["savings"].config(text=summary.net_savings_rupees)
        self.kpi_labels["rate"].config(text=summary.savings_rate_formatted)

        # 1. Bar Chart
        for w in self.chart_frame1.winfo_children():
            w.destroy()
        cashflow_data = self.service.analytics.get_monthly_cashflow_history(num_months=6)
        c1 = LedgerCharts.draw_cashflow_bars(self.chart_frame1, cashflow_data, is_dark=self.theme["is_dark"], figsize=(5.2, 2.7))
        c1.get_tk_widget().pack(fill="both", expand=True)

        # 2. Donut Chart
        for w in self.chart_frame2.winfo_children():
            w.destroy()
        cat_spending = self.service.analytics.get_category_spending(start_d, end_d)
        c2 = LedgerCharts.draw_category_donut(self.chart_frame2, cat_spending, is_dark=self.theme["is_dark"], figsize=(4.4, 2.7))
        c2.get_tk_widget().pack(fill="both", expand=True)

        # 3. Trend Line Chart
        for w in self.trend_frame.winfo_children():
            w.destroy()
        c3 = LedgerCharts.draw_trend_line(self.trend_frame, cashflow_data, is_dark=self.theme["is_dark"], figsize=(9.5, 2.4))
        c3.get_tk_widget().pack(fill="both", expand=True)


# =====================================================================
# 8. SETTINGS PAGE
# =====================================================================

class SettingsPage(BasePage):
    def __init__(self, parent: ttk.Frame, app: "LedgerApp"):
        super().__init__(parent, app)
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=self.theme["bg_app"], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Header
        tk.Label(container, text="Settings & Database Maintenance", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_app"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 20))

        # 1. Theme Configuration Card
        card_theme = tk.Frame(container, bg=self.theme["bg_card"], padx=18, pady=16,
                              highlightbackground=self.theme["border"], highlightthickness=1)
        card_theme.pack(fill="x", pady=(0, 16))

        tk.Label(card_theme, text="Appearance & Visual Style", font=("Segoe UI", 12, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")
        tk.Label(card_theme, text="Toggle between Dark Slate and Clean Light themes.", font=("Segoe UI", 9),
                 bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(anchor="w", pady=(2, 10))

        theme_btn_text = "Switch to Light Theme" if self.theme["is_dark"] else "Switch to Dark Theme"
        btn_theme = tk.Button(card_theme, text=theme_btn_text, font=("Segoe UI", 9, "bold"),
                              bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                              activebackground=self.theme["border"], bd=0, padx=14, pady=6,
                              cursor="hand2", command=self.app.toggle_theme)
        btn_theme.pack(anchor="w")

        # 2. Database Backup Card
        card_backup = tk.Frame(container, bg=self.theme["bg_card"], padx=18, pady=16,
                               highlightbackground=self.theme["border"], highlightthickness=1)
        card_backup.pack(fill="x", pady=(0, 16))

        tk.Label(card_backup, text="Database Backup", font=("Segoe UI", 12, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")
        tk.Label(card_backup, text="Create an atomic snapshot copy of your SQLite database without stopping the application.",
                 font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(anchor="w", pady=(2, 10))

        btn_backup = tk.Button(card_backup, text="💾 Backup Database Now", font=("Segoe UI", 9, "bold"),
                               bg=self.theme["info"], fg="#FFFFFF",
                               activebackground=self.theme["bg_hover"], bd=0, padx=14, pady=6,
                               cursor="hand2", command=self._backup_db)
        btn_backup.pack(anchor="w")

        # 3. Demonstration & Testing Data Card
        card_demo = tk.Frame(container, bg=self.theme["bg_card"], padx=18, pady=16,
                             highlightbackground=self.theme["border"], highlightthickness=1)
        card_demo.pack(fill="x", pady=(0, 16))

        tk.Label(card_demo, text="Demo Data Management", font=("Segoe UI", 12, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")
        tk.Label(card_demo, text="Populate rich fictional financial accounts, transactions, budgets, and goals for demonstration or viva.",
                 font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(anchor="w", pady=(2, 10))

        demo_btns = tk.Frame(card_demo, bg=self.theme["bg_card"])
        demo_btns.pack(anchor="w")

        btn_load = tk.Button(demo_btns, text="✨ Load Demo Dataset", font=("Segoe UI", 9, "bold"),
                             bg=self.theme["accent"], fg=self.theme["accent_text"],
                             activebackground=self.theme["accent_hover"], bd=0, padx=14, pady=6,
                             cursor="hand2", command=self._load_demo)
        btn_load.pack(side="left", padx=(0, 10))

        btn_clear = tk.Button(demo_btns, text="⚠️ Clear All Data", font=("Segoe UI", 9, "bold"),
                              bg=self.theme["bg_card"], fg=self.theme["danger"],
                              activebackground=self.theme["bg_hover"], bd=1, padx=14, pady=5,
                              cursor="hand2", command=self._clear_data)
        btn_clear.pack(side="left")

        # 4. System Diagnostics Card
        self.card_info = tk.Frame(container, bg=self.theme["bg_card"], padx=18, pady=16,
                                  highlightbackground=self.theme["border"], highlightthickness=1)
        self.card_info.pack(fill="x")

        tk.Label(self.card_info, text="Database & System Information", font=("Segoe UI", 12, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w")
        self.lbl_db_stats = tk.Label(self.card_info, text="", font=("Segoe UI", 9),
                                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"], justify="left")
        self.lbl_db_stats.pack(anchor="w", pady=(6, 0))

    def _backup_db(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ledger_backup_{timestamp}.db"
        dest = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db")],
            initialfile=default_name,
            title="Save Database Backup"
        )
        if dest:
            self.service.db.backup(dest)
            messagebox.showinfo("Backup Successful", f"Database backed up successfully to:\n{dest}")

    def _load_demo(self) -> None:
        if messagebox.askyesno("Load Demo Data", "This will insert realistic sample accounts, transactions, budgets, and goals.\nProceed?"):
            self.service.demo.load_demo_data()
            messagebox.showinfo("Demo Data Loaded", "Sample financial data loaded successfully!")
            self.app.refresh_current_page()
            self.app.update_recurring_badge()
            self.refresh()

    def _clear_data(self) -> None:
        if messagebox.askyesno("Confirm Clear Data", "Are you sure you want to permanently delete ALL accounts, transactions, budgets, and goals?\n(Category list will be preserved).", icon="warning"):
            self.service.demo.clear_all_data()
            messagebox.showinfo("Data Cleared", "All transactional data has been cleared.")
            self.app.refresh_current_page()
            self.app.update_recurring_badge()
            self.refresh()

    def refresh(self) -> None:
        db_path = self.service.db.db_path
        abs_path = os.path.abspath(db_path)
        size_kb = os.path.getsize(abs_path) / 1024 if os.path.exists(abs_path) else 0

        acct_count = len(self.service.accounts.get_all_accounts(include_inactive=True))
        tx_count = len(self.service.transactions.search_transactions())
        goal_count = len(self.service.goals.get_all_goals(include_inactive=True))

        info_text = (
            f"Database File: {abs_path}\n"
            f"Database Size: {size_kb:.1f} KB\n"
            f"Active Records: {acct_count} Accounts • {tx_count} Transactions • {goal_count} Goals\n"
            f"Software Stack: Python 3.12+ • Tkinter/ttk • SQLite (WAL Mode) • Matplotlib"
        )
        self.lbl_db_stats.config(text=info_text)


# =====================================================================
# MODAL DIALOGS
# =====================================================================

class TransactionDialog(tk.Toplevel):
    """Modal dialog for creating and editing Transactions (Income, Expense, Transfer)."""
    def __init__(self, app: "LedgerApp", initial_type: str = "expense",
                 initial_transaction: Optional[Transaction] = None, on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.initial_tx = initial_transaction
        self.on_save = on_save

        self.title("Edit Transaction" if self.initial_tx else "New Transaction")
        self.geometry("480x640")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        # Keyboard shortcuts: Esc to cancel
        self.bind("<Escape>", lambda e: self.destroy())

        self._build_ui(initial_type)

    def _build_ui(self, initial_type: str) -> None:
        pad_frame = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        pad_frame.pack(fill="both", expand=True)

        # Dialog Title
        tk.Label(pad_frame, text="Transaction Details", font=("Segoe UI", 14, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        # Transaction Type Selector
        type_frame = tk.Frame(pad_frame, bg=self.theme["bg_card"])
        type_frame.pack(fill="x", pady=(0, 14))

        self.type_var = tk.StringVar(value=self.initial_tx.transaction_type if self.initial_tx else initial_type)
        for t_val, t_lbl in [("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer")]:
            rb = tk.Radiobutton(type_frame, text=t_lbl, value=t_val, variable=self.type_var,
                                font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_primary"],
                                selectcolor=self.theme["bg_hover"], activebackground=self.theme["bg_card"],
                                command=self._on_type_change)
            rb.pack(side="left", padx=(0, 16))
            if self.initial_tx:
                rb.config(state="disabled")

        # Bottom Buttons (pack first to guarantee visibility)
        btn_box = tk.Frame(pad_frame, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        btn_cancel = tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9),
                               bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                               bd=0, padx=14, pady=6, cursor="hand2", command=self.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = tk.Button(btn_box, text="Save Transaction", font=("Segoe UI", 9, "bold"),
                             bg=self.theme["accent"], fg="#FFFFFF",
                             bd=0, padx=16, pady=6, cursor="hand2", command=self._submit)
        btn_save.pack(side="right")

        # Error display label
        self.lbl_error = tk.Label(pad_frame, text="", font=("Segoe UI", 9),
                                  bg=self.theme["bg_card"], fg=self.theme["danger"], wraplength=420)
        self.lbl_error.pack(fill="x", side="bottom", pady=(4, 8))

        # Form Fields Container (fills remaining space)
        self.form_container = tk.Frame(pad_frame, bg=self.theme["bg_card"])
        self.form_container.pack(fill="both", expand=True)

        self._render_form_fields()

    def _on_type_change(self) -> None:
        self._render_form_fields()

    def _render_form_fields(self) -> None:
        for w in self.form_container.winfo_children():
            w.destroy()

        t_type = self.type_var.get()
        accounts = self.service.accounts.get_all_accounts(include_inactive=False)
        acct_names = [a.name for a in accounts]

        # 1. Amount
        tk.Label(self.form_container, text="Amount (₹):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_amount = tk.Entry(self.form_container, font=("Segoe UI", 11),
                                     bg=self.theme["input_bg"], fg=self.theme["input_fg"],
                                     insertbackground=self.theme["text_primary"], bd=1)
        self.entry_amount.pack(fill="x", pady=(0, 8))
        if self.initial_tx:
            self.entry_amount.insert(0, str(paise_to_rupees(self.initial_tx.amount_paise)))

        # 2. Date
        tk.Label(self.form_container, text="Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_date = tk.Entry(self.form_container, font=("Segoe UI", 10),
                                   bg=self.theme["input_bg"], fg=self.theme["input_fg"],
                                   insertbackground=self.theme["text_primary"], bd=1)
        self.entry_date.pack(fill="x", pady=(0, 8))
        self.entry_date.insert(0, self.initial_tx.transaction_date if self.initial_tx else date.today().isoformat())

        if t_type == "transfer":
            # Transfer Fields: Source Account & Destination Account
            tk.Label(self.form_container, text="From Account:", font=("Segoe UI", 9, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
            self.combo_source = ttk.Combobox(self.form_container, values=acct_names, state="readonly")
            self.combo_source.pack(fill="x", pady=(0, 8))
            if acct_names:
                self.combo_source.current(0)

            tk.Label(self.form_container, text="To Account:", font=("Segoe UI", 9, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
            self.combo_dest = ttk.Combobox(self.form_container, values=acct_names, state="readonly")
            self.combo_dest.pack(fill="x", pady=(0, 8))
            if len(acct_names) > 1:
                self.combo_dest.current(1)
        else:
            # Income/Expense Fields: Account, Category, Merchant
            tk.Label(self.form_container, text="Account:", font=("Segoe UI", 9, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
            self.combo_account = ttk.Combobox(self.form_container, values=acct_names, state="readonly")
            self.combo_account.pack(fill="x", pady=(0, 8))
            if self.initial_tx:
                self.combo_account.set(self.initial_tx.account_name)
            elif acct_names:
                self.combo_account.current(0)

            categories = self.service.categories.get_categories(category_type=t_type, include_inactive=False)
            cat_names = [c.name for c in categories]
            tk.Label(self.form_container, text="Category:", font=("Segoe UI", 9, "bold"),
                     bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
            self.combo_category = ttk.Combobox(self.form_container, values=cat_names)
            self.combo_category.pack(fill="x", pady=(0, 8))
            if self.initial_tx:
                self.combo_category.set(self.initial_tx.category_name)
            elif cat_names:
                self.combo_category.current(0)

            tk.Label(self.form_container, text="Payee / Merchant:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
            self.entry_merchant = tk.Entry(self.form_container, font=("Segoe UI", 10),
                                           bg=self.theme["input_bg"], fg=self.theme["input_fg"],
                                           insertbackground=self.theme["text_primary"], bd=1)
            self.entry_merchant.pack(fill="x", pady=(0, 8))
            if self.initial_tx:
                self.entry_merchant.insert(0, self.initial_tx.merchant_name)

        # Notes (Common)
        tk.Label(self.form_container, text="Notes / Memo:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_note = tk.Entry(self.form_container, font=("Segoe UI", 10),
                                   bg=self.theme["input_bg"], fg=self.theme["input_fg"],
                                   insertbackground=self.theme["text_primary"], bd=1)
        self.entry_note.pack(fill="x", pady=(0, 4))
        if self.initial_tx:
            self.entry_note.insert(0, self.initial_tx.note)

    def _submit(self) -> None:
        self.lbl_error.config(text="")
        # 1. Validate Amount
        amt_raw = self.entry_amount.get().strip()
        try:
            amt_paise = rupees_to_paise(amt_raw)
            if amt_paise <= 0:
                raise ValueError("Amount must be greater than zero.")
        except Exception:
            self.lbl_error.config(text="Please enter a valid positive numerical amount.")
            return

        # 2. Validate Date
        date_str = self.entry_date.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.lbl_error.config(text="Invalid date format. Use YYYY-MM-DD.")
            return

        t_type = self.type_var.get()
        note = self.entry_note.get().strip()

        try:
            if t_type == "transfer":
                src_name = self.combo_source.get()
                dst_name = self.combo_dest.get()
                if not src_name or not dst_name:
                    self.lbl_error.config(text="Please select both source and destination accounts.")
                    return
                if src_name == dst_name:
                    self.lbl_error.config(text="Source and destination accounts must be different.")
                    return

                # Lookup account IDs
                accts = self.service.accounts.get_all_accounts(include_inactive=True)
                src_id = next(a.id for a in accts if a.name == src_name)
                dst_id = next(a.id for a in accts if a.name == dst_name)

                self.service.transactions.create_transfer(src_id, dst_id, amt_paise, date_str, note)
            else:
                acct_name = self.combo_account.get()
                if not acct_name:
                    self.lbl_error.config(text="Please select an account.")
                    return
                accts = self.service.accounts.get_all_accounts(include_inactive=True)
                acct_id = next(a.id for a in accts if a.name == acct_name)

                cat_name = self.combo_category.get().strip()
                cat_id = None
                if cat_name:
                    cat_id = self.service.categories.get_or_create_category(cat_name, t_type)

                merchant_name = self.entry_merchant.get().strip()

                if self.initial_tx:
                    self.service.transactions.update_transaction(
                        transaction_id=self.initial_tx.id,
                        account_id=acct_id,
                        amount_paise=amt_paise,
                        transaction_date=date_str,
                        category_id=cat_id,
                        merchant_name=merchant_name,
                        note=note,
                    )
                else:
                    self.service.transactions.create_income_or_expense(
                        account_id=acct_id,
                        amount_paise=amt_paise,
                        transaction_type=t_type,
                        transaction_date=date_str,
                        category_id=cat_id,
                        merchant_name=merchant_name,
                        note=note,
                    )

            if self.on_save:
                self.on_save()
            self.destroy()

        except Exception as exc:
            self.lbl_error.config(text=f"Error saving: {str(exc)}")


class AccountDialog(tk.Toplevel):
    """Modal dialog for creating and editing Accounts."""
    def __init__(self, app: "LedgerApp", initial_account: Optional[Account] = None, on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.initial_acct = initial_account
        self.on_save = on_save

        self.title("Edit Account" if self.initial_acct else "Add New Account")
        self.geometry("420x360")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        f = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Account Information", font=("Segoe UI", 13, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        tk.Label(f, text="Account Name:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_name = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_name.pack(fill="x", pady=(0, 8))
        if self.initial_acct:
            self.entry_name.insert(0, self.initial_acct.name)

        tk.Label(f, text="Account Type:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.combo_type = ttk.Combobox(f, state="readonly", values=["Bank", "Cash", "Credit Card", "Savings", "Other"])
        self.combo_type.pack(fill="x", pady=(0, 8))
        if self.initial_acct:
            self.combo_type.set(self.initial_acct.account_type)
        else:
            self.combo_type.current(0)

        tk.Label(f, text="Opening Balance (₹):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_open = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_open.pack(fill="x", pady=(0, 10))
        if self.initial_acct:
            self.entry_open.insert(0, str(paise_to_rupees(self.initial_acct.opening_balance_paise)))
        else:
            self.entry_open.insert(0, "0.00")

        self.lbl_error = tk.Label(f, text="", font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["danger"])
        self.lbl_error.pack(fill="x", pady=4)

        btn_box = tk.Frame(f, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                  bd=0, padx=12, pady=5, cursor="hand2", command=self.destroy).pack(side="right", padx=(6, 0))

        tk.Button(btn_box, text="Save Account", font=("Segoe UI", 9, "bold"), bg=self.theme["accent"], fg="#FFFFFF",
                  bd=0, padx=14, pady=5, cursor="hand2", command=self._submit).pack(side="right")

    def _submit(self) -> None:
        name = self.entry_name.get().strip()
        if not name:
            self.lbl_error.config(text="Account name is required.")
            return

        acct_type = self.combo_type.get()
        try:
            open_paise = rupees_to_paise(self.entry_open.get().strip())
        except Exception:
            self.lbl_error.config(text="Please enter a valid opening balance number.")
            return

        try:
            if self.initial_acct:
                self.service.accounts.update_account(self.initial_acct.id, name, acct_type, open_paise)
            else:
                self.service.accounts.create_account(name, acct_type, open_paise)

            if self.on_save:
                self.on_save()
            self.destroy()
        except Exception as exc:
            self.lbl_error.config(text=f"Error saving: {str(exc)}")


class BudgetDialog(tk.Toplevel):
    """Modal dialog for defining category budgets."""
    def __init__(self, app: "LedgerApp", month: str, on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.month = month
        self.on_save = on_save

        self.title("Set Category Budget")
        self.geometry("380x320")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        f = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text=f"Budget for {self.month}", font=("Segoe UI", 13, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        categories = self.service.categories.get_categories(category_type="expense", include_inactive=False)
        cat_names = [c.name for c in categories]

        tk.Label(f, text="Expense Category:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.combo_cat = ttk.Combobox(f, values=cat_names, state="readonly")
        self.combo_cat.pack(fill="x", pady=(0, 10))
        if cat_names:
            self.combo_cat.current(0)

        tk.Label(f, text="Monthly Limit (₹):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_limit = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_limit.pack(fill="x", pady=(0, 12))

        self.lbl_error = tk.Label(f, text="", font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["danger"])
        self.lbl_error.pack(fill="x", pady=4)

        btn_box = tk.Frame(f, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                  bd=0, padx=12, pady=5, cursor="hand2", command=self.destroy).pack(side="right", padx=(6, 0))

        tk.Button(btn_box, text="Save Budget", font=("Segoe UI", 9, "bold"), bg=self.theme["accent"], fg="#FFFFFF",
                  bd=0, padx=14, pady=5, cursor="hand2", command=self._submit).pack(side="right")

    def _submit(self) -> None:
        cat_name = self.combo_cat.get()
        if not cat_name:
            self.lbl_error.config(text="Please select an expense category.")
            return

        try:
            limit_paise = rupees_to_paise(self.entry_limit.get().strip())
            if limit_paise < 0:
                raise ValueError()
        except Exception:
            self.lbl_error.config(text="Please enter a valid positive limit.")
            return

        cats = self.service.categories.get_categories(category_type="expense")
        cat_id = next(c.id for c in cats if c.name == cat_name)

        self.service.budgets.set_budget(self.month, cat_id, limit_paise)
        if self.on_save:
            self.on_save()
        self.destroy()


class RecurringDialog(tk.Toplevel):
    """Modal dialog for creating Recurring Transaction schedules."""
    def __init__(self, app: "LedgerApp", on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.on_save = on_save

        self.title("New Recurring Schedule")
        self.geometry("450x520")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        f = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Recurring Transaction Template", font=("Segoe UI", 13, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        # Type & Frequency Row
        row1 = tk.Frame(f, bg=self.theme["bg_card"])
        row1.pack(fill="x", pady=(0, 8))

        tk.Label(row1, text="Type:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=0, sticky="w")
        self.combo_type = ttk.Combobox(row1, values=["expense", "income"], state="readonly", width=12)
        self.combo_type.grid(row=0, column=1, padx=(6, 16))
        self.combo_type.current(0)
        self.combo_type.bind("<<ComboboxSelected>>", self._on_type_change)

        tk.Label(row1, text="Frequency:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).grid(row=0, column=2, sticky="w")
        self.combo_freq = ttk.Combobox(row1, values=["daily", "weekly", "monthly", "yearly"], state="readonly", width=12)
        self.combo_freq.grid(row=0, column=3, padx=(6, 0))
        self.combo_freq.set("monthly")

        # Amount
        tk.Label(f, text="Amount (₹):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_amount = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_amount.pack(fill="x", pady=(0, 8))

        # Account
        accounts = self.service.accounts.get_all_accounts(include_inactive=False)
        acct_names = [a.name for a in accounts]
        tk.Label(f, text="Account:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.combo_account = ttk.Combobox(f, values=acct_names, state="readonly")
        self.combo_account.pack(fill="x", pady=(0, 8))
        if acct_names:
            self.combo_account.current(0)

        # Category
        tk.Label(f, text="Category:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.combo_cat = ttk.Combobox(f)
        self.combo_cat.pack(fill="x", pady=(0, 8))
        self._update_categories()

        # Merchant
        tk.Label(f, text="Merchant / Payee:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_merchant = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_merchant.pack(fill="x", pady=(0, 8))

        # Next Run Date
        tk.Label(f, text="Next Run Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_date = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_date.pack(fill="x", pady=(0, 8))
        self.entry_date.insert(0, date.today().isoformat())

        self.lbl_error = tk.Label(f, text="", font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["danger"])
        self.lbl_error.pack(fill="x", pady=4)

        # Buttons
        btn_box = tk.Frame(f, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                  bd=0, padx=12, pady=5, cursor="hand2", command=self.destroy).pack(side="right", padx=(6, 0))

        tk.Button(btn_box, text="Create Schedule", font=("Segoe UI", 9, "bold"), bg=self.theme["accent"], fg="#FFFFFF",
                  bd=0, padx=14, pady=5, cursor="hand2", command=self._submit).pack(side="right")

    def _on_type_change(self, event=None) -> None:
        self._update_categories()

    def _update_categories(self) -> None:
        t_type = self.combo_type.get()
        cats = self.service.categories.get_categories(category_type=t_type)
        names = [c.name for c in cats]
        self.combo_cat["values"] = names
        if names:
            self.combo_cat.current(0)

    def _submit(self) -> None:
        try:
            amt_paise = rupees_to_paise(self.entry_amount.get().strip())
            if amt_paise <= 0:
                raise ValueError()
        except Exception:
            self.lbl_error.config(text="Please enter a valid positive numerical amount.")
            return

        date_str = self.entry_date.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.lbl_error.config(text="Date format must be YYYY-MM-DD.")
            return

        acct_name = self.combo_account.get()
        if not acct_name:
            self.lbl_error.config(text="Account is required.")
            return
        accts = self.service.accounts.get_all_accounts(include_inactive=True)
        acct_id = next(a.id for a in accts if a.name == acct_name)

        t_type = self.combo_type.get()
        freq = self.combo_freq.get()
        cat_name = self.combo_cat.get().strip()
        cat_id = self.service.categories.get_or_create_category(cat_name, t_type) if cat_name else None
        merchant = self.entry_merchant.get().strip()

        self.service.recurring.create_recurring(
            account_id=acct_id,
            amount_paise=amt_paise,
            transaction_type=t_type,
            frequency=freq,
            next_run_date=date_str,
            category_id=cat_id,
            merchant_name=merchant,
        )
        if self.on_save:
            self.on_save()
        self.destroy()


class GoalDialog(tk.Toplevel):
    """Modal dialog for creating and editing Financial Goals."""
    def __init__(self, app: "LedgerApp", on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.on_save = on_save

        self.title("New Financial Goal")
        self.geometry("380x320")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        f = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Goal Information", font=("Segoe UI", 13, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        tk.Label(f, text="Goal Name:", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_name = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_name.pack(fill="x", pady=(0, 8))

        tk.Label(f, text="Target Amount (₹):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_target = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_target.pack(fill="x", pady=(0, 8))

        tk.Label(f, text="Target Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_date = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_date.pack(fill="x", pady=(0, 10))
        next_yr = f"{date.today().year + 1:04d}-12-31"
        self.entry_date.insert(0, next_yr)

        self.lbl_error = tk.Label(f, text="", font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["danger"])
        self.lbl_error.pack(fill="x", pady=4)

        btn_box = tk.Frame(f, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                  bd=0, padx=12, pady=5, cursor="hand2", command=self.destroy).pack(side="right", padx=(6, 0))

        tk.Button(btn_box, text="Create Goal", font=("Segoe UI", 9, "bold"), bg=self.theme["accent"], fg="#FFFFFF",
                  bd=0, padx=14, pady=5, cursor="hand2", command=self._submit).pack(side="right")

    def _submit(self) -> None:
        name = self.entry_name.get().strip()
        if not name:
            self.lbl_error.config(text="Goal name is required.")
            return

        try:
            target_paise = rupees_to_paise(self.entry_target.get().strip())
            if target_paise <= 0:
                raise ValueError()
        except Exception:
            self.lbl_error.config(text="Please enter a valid positive target amount.")
            return

        target_date = self.entry_date.get().strip()
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            self.lbl_error.config(text="Target date format must be YYYY-MM-DD.")
            return

        try:
            self.service.goals.create_goal(name, target_paise, target_date)
            if self.on_save:
                self.on_save()
            self.destroy()
        except Exception as exc:
            self.lbl_error.config(text=f"Error saving goal: {str(exc)}")


class ContributionDialog(tk.Toplevel):
    """Modal dialog for logging savings contributions towards a goal."""
    def __init__(self, app: "LedgerApp", goal: FinancialGoal, on_save: Optional[Callable[[], None]] = None):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.theme = app.theme
        self.goal = goal
        self.on_save = on_save

        self.title(f"Contribute to {goal.name}")
        self.geometry("380x280")
        self.resizable(False, False)
        self.configure(bg=self.theme["bg_card"])
        self.transient(app.root)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        f = tk.Frame(self, bg=self.theme["bg_card"], padx=24, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text=f"Add Savings: {self.goal.name}", font=("Segoe UI", 12, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_primary"]).pack(anchor="w", pady=(0, 14))

        tk.Label(f, text="Contribution Amount (₹):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_amt = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_amt.pack(fill="x", pady=(0, 8))

        tk.Label(f, text="Notes (optional):", font=("Segoe UI", 9, "bold"),
                 bg=self.theme["bg_card"], fg=self.theme["text_secondary"]).pack(anchor="w", pady=(4, 2))
        self.entry_note = tk.Entry(f, font=("Segoe UI", 10), bg=self.theme["input_bg"], fg=self.theme["input_fg"], bd=1)
        self.entry_note.pack(fill="x", pady=(0, 10))

        self.lbl_error = tk.Label(f, text="", font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["danger"])
        self.lbl_error.pack(fill="x", pady=4)

        btn_box = tk.Frame(f, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", side="bottom")

        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                  bd=0, padx=12, pady=5, cursor="hand2", command=self.destroy).pack(side="right", padx=(6, 0))

        tk.Button(btn_box, text="Add Savings", font=("Segoe UI", 9, "bold"), bg=self.theme["accent"], fg="#FFFFFF",
                  bd=0, padx=14, pady=5, cursor="hand2", command=self._submit).pack(side="right")

    def _submit(self) -> None:
        try:
            amt_paise = rupees_to_paise(self.entry_amt.get().strip())
            if amt_paise <= 0:
                raise ValueError()
        except Exception:
            self.lbl_error.config(text="Please enter a valid positive amount.")
            return

        note = self.entry_note.get().strip()
        self.service.goals.add_contribution(self.goal.id, amt_paise, date.today().isoformat(), note)
        if self.on_save:
            self.on_save()
        self.destroy()


# =====================================================================
# MAIN APPLICATION SHELL
# =====================================================================

class LedgerApp:
    def __init__(self, root: tk.Tk, service: FinanceService):
        self.root = root
        self.service = service
        self.is_dark_theme = True
        self.theme = UITheme.DARK

        self.root.title("Ledger — Personal Finance Management System")
        self.root.geometry("1280x820")
        self.root.minsize(1024, 650)
        self.root.configure(bg=self.theme["bg_app"])

        # Configure TTK Styles
        self._apply_ttk_styles()

        # Keyboard shortcuts
        self.root.bind("<Control-n>", lambda e: self.open_transaction_dialog("expense"))
        self.root.bind("<Control-N>", lambda e: self.open_transaction_dialog("expense"))
        self.root.bind("<Control-f>", lambda e: self._shortcut_focus_search())
        self.root.bind("<Control-F>", lambda e: self._shortcut_focus_search())

        self._build_layout()

        # Auto-process due recurring items on startup quietly
        due_processed = self.service.recurring.process_due_transactions()
        if due_processed > 0:
            print(f"Processed {due_processed} due recurring transaction(s) on startup.")

        # Show initial page
        self.navigate_to("Dashboard")
        self.update_recurring_badge()

    def _apply_ttk_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        # Treeview styling
        style.configure(
            "Treeview",
            background=self.theme["tree_bg"],
            foreground=self.theme["tree_fg"],
            fieldbackground=self.theme["tree_bg"],
            rowheight=28,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", self.theme["tree_selected"])],
            foreground=[("selected", self.theme["text_primary"])],
        )
        style.configure(
            "Treeview.Heading",
            background=self.theme["bg_card"],
            foreground=self.theme["text_secondary"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Treeview.Heading",
            background=[("active", self.theme["bg_hover"])],
            foreground=[("active", self.theme["text_primary"])],
        )

        # Progressbar styling
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=self.theme["bg_hover"],
            background=self.theme["accent"],
            bordercolor=self.theme["bg_hover"],
            lightcolor=self.theme["accent"],
            darkcolor=self.theme["accent"],
        )

    def _build_layout(self) -> None:
        # Main Shell Container (Left Sidebar + Right Content Area)
        self.shell = tk.Frame(self.root, bg=self.theme["bg_app"])
        self.shell.pack(fill="both", expand=True)

        # 1. Left Sidebar
        self.sidebar = tk.Frame(self.shell, bg=self.theme["bg_sidebar"], width=230,
                                highlightbackground=self.theme["border"], highlightthickness=1)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Sidebar App Branding
        brand_frame = tk.Frame(self.sidebar, bg=self.theme["bg_sidebar"], padx=18, pady=22)
        brand_frame.pack(fill="x")

        tk.Label(brand_frame, text="LEDGER", font=("Segoe UI", 16, "bold"),
                 bg=self.theme["bg_sidebar"], fg=self.theme["accent"]).pack(anchor="w")
        tk.Label(brand_frame, text="Personal Finance System", font=("Segoe UI", 8),
                 bg=self.theme["bg_sidebar"], fg=self.theme["text_muted"]).pack(anchor="w")

        # Sidebar Navigation Menu Buttons
        self.nav_buttons = {}
        self.nav_items = [
            ("Dashboard", "📊 Dashboard"),
            ("Transactions", "💳 Transactions"),
            ("Accounts", "🏦 Accounts"),
            ("Budgets", "🎯 Budgets"),
            ("Recurring", "🔄 Recurring"),
            ("Goals", "🏆 Goals"),
            ("Reports", "📈 Reports"),
            ("Settings", "⚙️ Settings"),
        ]

        menu_frame = tk.Frame(self.sidebar, bg=self.theme["bg_sidebar"], padx=10, pady=10)
        menu_frame.pack(fill="x")

        for key, label in self.nav_items:
            btn = tk.Button(
                menu_frame,
                text=f"  {label}",
                font=("Segoe UI", 10),
                anchor="w",
                bg=self.theme["bg_sidebar"],
                fg=self.theme["text_secondary"],
                activebackground=self.theme["bg_hover"],
                activeforeground=self.theme["text_primary"],
                bd=0,
                padx=12,
                pady=9,
                cursor="hand2",
                command=lambda k=key: self.navigate_to(k),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Sidebar Footer: Quick Stats
        sb_footer = tk.Frame(self.sidebar, bg=self.theme["bg_sidebar"], padx=16, pady=16)
        sb_footer.pack(side="bottom", fill="x")
        self.lbl_sidebar_due = tk.Label(sb_footer, text="", font=("Segoe UI", 8, "bold"),
                                        bg=self.theme["bg_hover"], fg=self.theme["text_primary"],
                                        padx=8, pady=4, cursor="hand2")
        self.lbl_sidebar_due.bind("<Button-1>", lambda e: self.navigate_to("Recurring"))

        # 2. Right Main Panel (Header + Page Frame)
        self.main_panel = tk.Frame(self.shell, bg=self.theme["bg_app"])
        self.main_panel.pack(side="right", fill="both", expand=True)

        # Top Bar / Header
        self.header = tk.Frame(self.main_panel, bg=self.theme["bg_card"], height=56, padx=24,
                               highlightbackground=self.theme["border"], highlightthickness=1)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.lbl_header_title = tk.Label(self.header, text="Dashboard", font=("Segoe UI", 12, "bold"),
                                         bg=self.theme["bg_card"], fg=self.theme["text_primary"])
        self.lbl_header_title.pack(side="left")

        # Top Quick Actions
        hdr_actions = tk.Frame(self.header, bg=self.theme["bg_card"])
        hdr_actions.pack(side="right")

        today_str = datetime.now().strftime("%A, %d %B %Y")
        tk.Label(hdr_actions, text=today_str, font=("Segoe UI", 9),
                 bg=self.theme["bg_card"], fg=self.theme["text_muted"]).pack(side="left", padx=16)

        btn_quick_add = tk.Button(hdr_actions, text="+ Quick Add", font=("Segoe UI", 8, "bold"),
                                  bg=self.theme["accent"], fg="#FFFFFF",
                                  activebackground=self.theme["accent_hover"], bd=0, padx=12, pady=5,
                                  cursor="hand2", command=lambda: self.open_transaction_dialog("expense"))
        btn_quick_add.pack(side="left")

        # Page Display Container
        self.pages_container = tk.Frame(self.main_panel, bg=self.theme["bg_app"])
        self.pages_container.pack(fill="both", expand=True)

        # Initialize all 8 Page instances
        self.pages: dict[str, BasePage] = {
            "Dashboard": DashboardPage(self.pages_container, self),
            "Transactions": TransactionsPage(self.pages_container, self),
            "Accounts": AccountsPage(self.pages_container, self),
            "Budgets": BudgetsPage(self.pages_container, self),
            "Recurring": RecurringPage(self.pages_container, self),
            "Goals": GoalsPage(self.pages_container, self),
            "Reports": ReportsPage(self.pages_container, self),
            "Settings": SettingsPage(self.pages_container, self),
        }

        self.current_page_name = "Dashboard"

    def navigate_to(self, page_name: str) -> None:
        if page_name not in self.pages:
            return

        # Update sidebar highlight
        for key, btn in self.nav_buttons.items():
            if key == page_name:
                btn.config(bg=self.theme["bg_hover"], fg=self.theme["accent"], font=("Segoe UI", 10, "bold"))
            else:
                btn.config(bg=self.theme["bg_sidebar"], fg=self.theme["text_secondary"], font=("Segoe UI", 10))

        # Hide current page, show new page
        for p in self.pages.values():
            p.pack_forget()

        self.current_page_name = page_name
        self.lbl_header_title.config(text=page_name)

        active_page = self.pages[page_name]
        active_page.pack(fill="both", expand=True)
        active_page.refresh()

    def refresh_current_page(self) -> None:
        if self.current_page_name in self.pages:
            self.pages[self.current_page_name].refresh()

    def update_recurring_badge(self) -> None:
        due_items = [r for r in self.service.recurring.get_all_recurring() if r.is_due()]
        if due_items:
            self.lbl_sidebar_due.config(text=f"⚡ {len(due_items)} Recurring Due", fg=self.theme["warning"])
            self.lbl_sidebar_due.pack(fill="x")
        else:
            self.lbl_sidebar_due.pack_forget()

    def open_transaction_dialog(self, default_type: str = "expense") -> None:
        TransactionDialog(self, initial_type=default_type, on_save=self._on_transaction_saved)

    def _on_transaction_saved(self) -> None:
        self.refresh_current_page()
        self.update_recurring_badge()

    def _shortcut_focus_search(self) -> None:
        self.navigate_to("Transactions")
        tx_page = self.pages.get("Transactions")
        if tx_page and hasattr(tx_page, "search_entry"):
            tx_page.search_entry.focus_set()

    def toggle_theme(self) -> None:
        self.is_dark_theme = not self.is_dark_theme
        self.theme = UITheme.DARK if self.is_dark_theme else UITheme.LIGHT

        # Re-apply styles and rebuild layout
        self.shell.destroy()
        self.root.configure(bg=self.theme["bg_app"])
        self._apply_ttk_styles()
        self._build_layout()
        self.navigate_to(self.current_page_name)
