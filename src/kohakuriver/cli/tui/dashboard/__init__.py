"""
Textual-based TUI Dashboard for KohakuRiver cluster management.

Cross-platform TUI with:
- Dashboard overview
- Node/Task/VPS/Docker list views
- Modal dialogs for creating tasks/VPS
- Detail screens
"""

from kohakuriver.cli.tui.dashboard.app import DashboardApp

__all__ = ["DashboardApp"]
