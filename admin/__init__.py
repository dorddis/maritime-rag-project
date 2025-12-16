"""
Admin Dashboard

FastAPI-based control panel for maritime data ingesters.
"""

from .ingester_manager import get_manager, IngesterManager, INGESTERS

__all__ = ['get_manager', 'IngesterManager', 'INGESTERS']
