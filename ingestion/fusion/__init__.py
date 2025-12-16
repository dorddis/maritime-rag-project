"""
Sensor Fusion Module

Correlates detections from multiple sensors (AIS, Radar, Satellite, Drone)
to create unified vessel tracks and detect dark ships.
"""

from .schema import UnifiedTrack, SensorContribution, TrackStatus, IdentitySource
from .config import SENSOR_CONFIG, CorrelationGates, DarkShipDetectionConfig
from .correlation import CorrelationEngine
from .track_manager import TrackManager

__all__ = [
    "UnifiedTrack",
    "SensorContribution",
    "TrackStatus",
    "IdentitySource",
    "SENSOR_CONFIG",
    "CorrelationGates",
    "DarkShipDetectionConfig",
    "CorrelationEngine",
    "TrackManager",
]
