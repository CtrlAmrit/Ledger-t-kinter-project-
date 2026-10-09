"""
export.py - Data Export & Backup Capabilities for Ledger.

Provides:
- Filtered transactions export to CSV
- Comprehensive Monthly Financial Report generation to PDF via Matplotlib PdfPages
- Safe, timestamped SQLite database backups
"""

from __future__ import annotations
import csv
from datetime import datetime
import os
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for background PDF generation
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from calculations import format_currency, paise_to_rupees, MonthlySummary, NetWorthSummary
from models import Transaction


class ExportService:
    @staticmethod
    def export_transactions_to_csv(transactions: Sequence[Transaction], filepath: str) -> str:
        """
        Export a list of transactions to a UTF-8 encoded CSV file.
        """
        parent_dir = os.path.dirname(os.path.abspath(filepath))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        fieldnames = [
            "ID",
            "Date",
            "Account",
            "Type",
            "Category",
            "Merchant / Payee",
            "Amount (Rupees)",
            "Notes",
            "Transfer Group ID",
        ]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for tx in transactions:
                # Format signed amount in rupees
                if tx.is_income:
                    amt_str = f"+{paise_to_rupees(tx.amount_paise):.2f}"
                elif tx.is_expense:
                    amt_str = f"-{paise_to_rupees(tx.amount_paise):.2f}"
                else:
                    amt_str = f"{paise_to_rupees(tx.amount_paise):.2f}"

                writer.writerow({
                    "ID": tx.id,
                    "Date": tx.transaction_date,
                    "Account": tx.account_name,
                    "Type": tx.transaction_type.capitalize(),
                    "Category": tx.category_name,
                    "Merchant / Payee": tx.merchant_name,
                    "Amount (Rupees)": amt_str,
                    "Notes": tx.note,
                    "Transfer Group ID": tx.transfer_group_id or "",
                })

        return filepath

    @staticmethod
    def generate_pdf_report(
        filepath: str,
        period_label: str,
        summary: MonthlySummary,
        net_worth: NetWorthSummary,
        category_spending: list[tuple[str, int]],
        recent_transactions: Sequence[Transaction],
    ) -> str:
        """
        Generates a clean, professional, publication-quality PDF financial report
        using Matplotlib's PdfPages.
        """
        parent_dir = os.path.dirname(os.path.abspath(filepath))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with PdfPages(filepath) as pdf:
            # PAGE 1: Executive Overview & Charts
            fig = plt.figure(figsize=(8.5, 11), dpi=150)
            fig.patch.set_facecolor("#FFFFFF")

            # Header Banner
            fig.text(0.08, 0.94, "LEDGER PERSONAL FINANCE", fontsize=18, fontweight="bold", color="#0F172A")
            fig.text(0.08, 0.915, f"Financial Summary Report — {period_label}", fontsize=12, color="#475569")
            fig.text(0.08, 0.895, f"Generated on {datetime.now().strftime('%d %B %Y, %I:%M %p')}", fontsize=9, color="#94A3B8")

            # Horizontal Rule
            ax_line = fig.add_axes([0.08, 0.88, 0.84, 0.002])
            ax_line.patch.set_facecolor("#059669")
            ax_line.axis("off")

            # KPI Summary Grid (4 cards)
            kpis = [
                ("Total Income", summary.income_rupees, "#059669"),
                ("Total Expenses", summary.expense_rupees, "#DC2626"),
                ("Net Savings", summary.net_savings_rupees, "#2563EB" if summary.net_savings_paise >= 0 else "#DC2626"),
                ("Savings Rate", summary.savings_rate_formatted, "#0D9488"),
            ]

            card_width = 0.19
            gap = 0.026
            start_x = 0.08
            for i, (title, val, color) in enumerate(kpis):
                cx = start_x + i * (card_width + gap)
                ax_kpi = fig.add_axes([cx, 0.77, card_width, 0.09])
                ax_kpi.set_facecolor("#F8FAFC")
                for spine in ax_kpi.spines.values():
                    spine.set_color("#E2E8F0")
                    spine.set_linewidth(1)
                ax_kpi.set_xticks([])
                ax_kpi.set_yticks([])
                ax_kpi.text(0.5, 0.68, title.upper(), ha="center", va="center", fontsize=8, color="#64748B", fontweight="bold")
                ax_kpi.text(0.5, 0.32, val, ha="center", va="center", fontsize=11, color=color, fontweight="bold")

            # Section: Cashflow Comparison Bar Chart
            ax_bar = fig.add_axes([0.08, 0.46, 0.39, 0.25])
            ax_bar.set_facecolor("#FFFFFF")
            bar_categories = ["Income", "Expense", "Savings"]
            bar_values = [
                float(paise_to_rupees(summary.income_paise)),
                float(paise_to_rupees(summary.expense_paise)),
                max(0.0, float(paise_to_rupees(summary.net_savings_paise))),
            ]
            colors = ["#10B981", "#EF4444", "#3B82F6"]
            bars = ax_bar.bar(bar_categories, bar_values, color=colors, width=0.55, edgecolor="#E2E8F0")
            ax_bar.set_title("Cashflow Breakdown (₹)", fontsize=10, fontweight="bold", pad=10, color="#1E293B")
            ax_bar.spines["top"].set_visible(False)
            ax_bar.spines["right"].set_visible(False)
            ax_bar.spines["left"].set_color("#CBD5E1")
            ax_bar.spines["bottom"].set_color("#CBD5E1")
            ax_bar.tick_params(colors="#64748B", labelsize=8)

            # Section: Category Spending Breakdown (Donut Chart)
            ax_donut = fig.add_axes([0.53, 0.46, 0.39, 0.25])
            ax_donut.set_facecolor("#FFFFFF")
            if category_spending:
                top_cats = category_spending[:5]
                labels = [c[0] for c in top_cats]
                values = [float(paise_to_rupees(c[1])) for c in top_cats]
                donut_colors = ["#059669", "#0284C7", "#D97706", "#7C3AED", "#DB2777"][:len(values)]
                wedges, texts, autotexts = ax_donut.pie(
                    values,
                    labels=labels,
                    autopct="%1.0f%%",
                    colors=donut_colors,
                    startangle=140,
                    wedgeprops=dict(width=0.4, edgecolor="#FFFFFF", linewidth=1.5),
                    textprops=dict(fontsize=7, color="#334155"),
                )
                for at in autotexts:
                    at.set_fontsize(7)
                    at.set_color("#FFFFFF")
                    at.set_weight("bold")
                ax_donut.set_title("Top Spending Categories", fontsize=10, fontweight="bold", pad=10, color="#1E293B")
            else:
                ax_donut.text(0.5, 0.5, "No expense data for this period", ha="center", va="center", color="#94A3B8")
                ax_donut.axis("off")

            # Section: Net Worth Position Callout
            ax_nw = fig.add_axes([0.08, 0.34, 0.84, 0.08])
            ax_nw.set_facecolor("#F1F5F9")
            for spine in ax_nw.spines.values():
                spine.set_color("#CBD5E1")
            ax_nw.set_xticks([])
            ax_nw.set_yticks([])
            ax_nw.text(0.04, 0.5, f"CURRENT NET WORTH: {net_worth.net_worth_rupees}", fontsize=11, fontweight="bold", color="#0F172A", va="center")
            ax_nw.text(0.58, 0.5, f"Assets: {net_worth.total_assets_rupees}  |  Liabilities: {net_worth.total_liabilities_rupees}", fontsize=9, color="#475569", va="center")

            # Section: Category Summary Table
            ax_table = fig.add_axes([0.08, 0.08, 0.84, 0.22])
            ax_table.axis("off")
            ax_table.set_title("Category Spending Detail", fontsize=10, fontweight="bold", loc="left", color="#1E293B")

            table_data = [["Category", "Amount Spent", "% of Total"]]
            total_exp = summary.expense_paise or 1
            for cat_name, cat_paise in category_spending[:8]:
                pct = (cat_paise / total_exp) * 100.0
                table_data.append([cat_name, format_currency(cat_paise), f"{pct:.1f}%"])

            if len(table_data) == 1:
                table_data.append(["No expense data recorded", "₹0.00", "0.0%"])

            tab = ax_table.table(
                cellText=table_data,
                cellLoc="left",
                loc="upper center",
                colWidths=[0.45, 0.30, 0.25],
            )
            tab.auto_set_font_size(False)
            tab.set_fontsize(8)
            tab.scale(1, 1.4)

            # Style header row
            for col_idx in range(3):
                cell = tab[(0, col_idx)]
                cell.set_facecolor("#E2E8F0")
                cell.set_text_props(weight="bold", color="#1E293B")

            pdf.savefig(fig)
            plt.close(fig)

        return filepath
