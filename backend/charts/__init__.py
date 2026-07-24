"""charts package — build chart configuration objects from VizSuggestion

This module transforms a `VizSuggestion` into a frontend-friendly config
dictionary (type, axes, title, and extra options). Kept minimal to avoid
opinionated rendering code here.
"""
from typing import Dict, Any


def build_chart_config(viz_suggestion) -> Dict[str, Any]:
    if viz_suggestion is None:
        return {"type": "table"}

    cfg = {"type": viz_suggestion.chart_type, "title": viz_suggestion.title}
    if getattr(viz_suggestion, "x_col", None):
        cfg["x"] = viz_suggestion.x_col
    if getattr(viz_suggestion, "y_col", None):
        cfg["y"] = viz_suggestion.y_col
    cfg["reason"] = getattr(viz_suggestion, "reason", "")
    return cfg

__all__ = ["build_chart_config"]
