"""
charts.py - Matplotlib Data Visualizations for Ledger.

Embeds styled, high-DPI Matplotlib charts inside Tkinter frames.
Supports both modern dark and light color palettes.
"""

from __future__ import annotations
from typing import Sequence, Any, Optional

import matplotlib
# Use TkAgg when rendering inside Tkinter UI
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from calculations import paise_to_rupees


class ChartTheme:
    """Color palette definitions for charts."""
    DARK = {
        "bg": "#1E293B",
        "plot_bg": "#1E293B",
        "text": "#E2E8F0",
        "subtext": "#94A3B8",
        "grid": "#334155",
        "income": "#10B981",     # Emerald
        "expense": "#EF4444",    # Rose/Red
        "savings": "#3B82F6",    # Sky/Blue
        "palette": ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#14B8A6"],
    }
    LIGHT = {
        "bg": "#FFFFFF",
        "plot_bg": "#FFFFFF",
        "text": "#0F172A",
        "subtext": "#64748B",
        "grid": "#E2E8F0",
        "income": "#059669",
        "expense": "#DC2626",
        "savings": "#2563EB",
        "palette": ["#059669", "#2563EB", "#D97706", "#7C3AED", "#DB2777", "#0D9488"],
    }


class LedgerCharts:
    @staticmethod
    def draw_cashflow_bars(
        parent_frame: Any,
        data: list[dict[str, Any]],
        is_dark: bool = True,
        figsize: tuple[float, float] = (5.5, 3.2),
    ) -> FigureCanvasTkAgg:
        """
        Renders a monthly Income vs Expense comparison bar chart.
        """
        theme = ChartTheme.DARK if is_dark else ChartTheme.LIGHT

        fig, ax = plt.subplots(figsize=figsize, dpi=100)
        fig.patch.set_facecolor(theme["bg"])
        ax.set_facecolor(theme["plot_bg"])

        if not data:
            ax.text(0.5, 0.5, "No transaction data available", color=theme["subtext"],
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
        else:
            labels = [d["label"] for d in data]
            incomes = [float(paise_to_rupees(d["income_paise"])) for d in data]
            expenses = [float(paise_to_rupees(d["expense_paise"])) for d in data]

            x = list(range(len(labels)))
            width = 0.35

            ax.bar([i - width / 2 for i in x], incomes, width=width, label="Income",
                   color=theme["income"], alpha=0.9, edgecolor="none")
            ax.bar([i + width / 2 for i in x], expenses, width=width, label="Expense",
                   color=theme["expense"], alpha=0.9, edgecolor="none")

            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=8, color=theme["text"])
            ax.tick_params(axis="y", labelsize=8, colors=theme["subtext"])
            ax.tick_params(axis="x", colors=theme["text"], length=0)
            ax.yaxis.grid(True, linestyle="--", alpha=0.5, color=theme["grid"])
            ax.set_axisbelow(True)

            for spine in ax.spines.values():
                spine.set_color(theme["grid"])
                spine.set_linewidth(0.8)

            leg = ax.legend(frameon=False, fontsize=8, labelcolor=theme["text"])

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        return canvas

    @staticmethod
    def draw_category_donut(
        parent_frame: Any,
        categories: list[tuple[str, int]],
        is_dark: bool = True,
        figsize: tuple[float, float] = (4.5, 3.2),
    ) -> FigureCanvasTkAgg:
        """
        Renders an expense distribution donut chart.
        """
        theme = ChartTheme.DARK if is_dark else ChartTheme.LIGHT

        fig, ax = plt.subplots(figsize=figsize, dpi=100)
        fig.patch.set_facecolor(theme["bg"])
        ax.set_facecolor(theme["plot_bg"])

        if not categories:
            ax.text(0.5, 0.5, "No expense categories recorded", color=theme["subtext"],
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
        else:
            top_cats = categories[:6]
            labels = [c[0] for c in top_cats]
            values = [float(paise_to_rupees(c[1])) for c in top_cats]
            colors = theme["palette"][:len(values)]

            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                autopct="%1.0f%%",
                pctdistance=0.75,
                colors=colors,
                startangle=140,
                wedgeprops=dict(width=0.45, edgecolor=theme["bg"], linewidth=1.5),
                textprops=dict(fontsize=8, color=theme["text"]),
            )
            for at in autotexts:
                at.set_fontsize(7)
                at.set_color("#FFFFFF")
                at.set_weight("bold")

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        return canvas

    @staticmethod
    def draw_trend_line(
        parent_frame: Any,
        data: list[dict[str, Any]],
        is_dark: bool = True,
        figsize: tuple[float, float] = (5.5, 3.0),
    ) -> FigureCanvasTkAgg:
        """
        Renders a monthly savings/spending trend line chart.
        """
        theme = ChartTheme.DARK if is_dark else ChartTheme.LIGHT

        fig, ax = plt.subplots(figsize=figsize, dpi=100)
        fig.patch.set_facecolor(theme["bg"])
        ax.set_facecolor(theme["plot_bg"])

        if not data:
            ax.text(0.5, 0.5, "No trend data available", color=theme["subtext"],
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
        else:
            labels = [d["label"] for d in data]
            savings = [float(paise_to_rupees(d["savings_paise"])) for d in data]
            x = list(range(len(labels)))

            ax.plot(x, savings, marker="o", color=theme["savings"], linewidth=2, markersize=5, label="Net Savings")
            ax.fill_between(x, savings, color=theme["savings"], alpha=0.15)

            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=8, color=theme["text"])
            ax.tick_params(axis="y", labelsize=8, colors=theme["subtext"])
            ax.yaxis.grid(True, linestyle="--", alpha=0.5, color=theme["grid"])
            ax.axhline(0, color=theme["grid"], linestyle="-", linewidth=1)

            for spine in ax.spines.values():
                spine.set_color(theme["grid"])
                spine.set_linewidth(0.8)

            ax.legend(frameon=False, fontsize=8, labelcolor=theme["text"])

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        return canvas
