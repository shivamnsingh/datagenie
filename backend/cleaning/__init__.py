"""cleaning package — thin adapter over services.cleaning_service

This package exposes the existing cleaning functions under a
`backend.cleaning` namespace so higher-level code can import from
`backend.cleaning` instead of reaching into `services`.
"""
from services.cleaning_service import preview_cleaning, apply_cleaning

__all__ = ["preview_cleaning", "apply_cleaning"]
