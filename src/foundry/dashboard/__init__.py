"""Foundry dashboard: a read-only, self-contained HTML view over the ledger
(report section 15.3, the RSI-specific governance and evolution view of 15.6).

Two pure stages -- projection then presentation -- so the page can never
introduce a fact the evidence does not contain:

    from foundry.dashboard import build_dashboard_model, render_html
    model = build_dashboard_model(ledger, registry, root_name="demo")
    html = render_html(model)
"""

from .model import DashboardModel
from .project import build_dashboard_model
from .render import render_html

__all__ = ["DashboardModel", "build_dashboard_model", "render_html"]
