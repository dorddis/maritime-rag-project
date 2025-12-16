"""
Shared components for unified maritime simulation.
"""

from .fleet_manager import FleetManager, Ship
from .world_simulator import WorldSimulator

__all__ = ['FleetManager', 'Ship', 'WorldSimulator']
