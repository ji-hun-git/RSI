"""Deployment / canary / rollback controller (report sections 10.4, 13.6).

Event-sourced projection over the governance ledger: activation and
rollback state is rebuilt purely from ``governance.canary``,
``governance.promotion`` and ``governance.rollback`` events.
"""

from .controller import (
    MODE_CANARY,
    MODE_SCOPED_PRODUCTION,
    DeploymentController,
    DeploymentState,
    GovernanceError,
    rebuild_state,
)

__all__ = [
    "MODE_CANARY",
    "MODE_SCOPED_PRODUCTION",
    "DeploymentController",
    "DeploymentState",
    "GovernanceError",
    "rebuild_state",
]
