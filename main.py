"""
main.py - Application Entry Point for Ledger.

Personal Finance Management Desktop System.
Initializes database connections, configures high-DPI scaling,
and starts the Tkinter event loop.
"""

from __future__ import annotations
import argparse
import os
import sys
import tkinter as tk

from services import FinanceService
from ui import LedgerApp


def enable_windows_high_dpi() -> None:
    """Enables DPI awareness on Windows to prevent blurry text and widgets."""
    if sys.platform == "win32":
        try:
            from ctypes import windll
            # Per-monitor DPI aware (PROCESS_PER_MONITOR_DPI_AWARE)
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Ledger - Personal Finance Management System")
    parser.add_argument("--db", type=str, default="ledger.db", help="Path to SQLite database file")
    parser.add_argument("--demo", action="store_true", help="Automatically load demo data if database is empty")
    args = parser.parse_args()

    enable_windows_high_dpi()

    # Initialize Service Layer & Database
    service = FinanceService(db_path=args.db)

    # If --demo flag passed or user opted into sample data on fresh run
    if args.demo:
        accounts = service.accounts.get_all_accounts(include_inactive=True)
        if not accounts:
            print("Seeding initial demo dataset...")
            service.demo.load_demo_data()

    # Launch GUI
    root = tk.Tk()
    app = LedgerApp(root, service)

    # Handle clean window close
    def on_closing():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
