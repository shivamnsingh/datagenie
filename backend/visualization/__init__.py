"""visualization package — chart suggestion & utilities

Re-exports the visual suggestion function from `services.sql_service` so
frontends or routers can import the policy from `backend.visualization`.
"""
from services.sql_service import _suggest_viz as suggest_viz

__all__ = ["suggest_viz"]
