"""
Fusion Configuration

Sensor characteristics, correlation gates, and dark ship detection thresholds.
"""

from dataclasses import dataclass


@dataclass
class SensorCharacteristics:
    """Sensor accuracy and capabilities"""
    position_error_m: float       # 1-sigma position error in meters
    speed_error_knots: float      # 1-sigma speed error
    update_rate_hz: float         # Typical update rate
    has_identity: bool            # Can identify vessel (MMSI/name)
    sees_dark_ships: bool         # Can detect AIS-off vessels


# Sensor configurations matching existing ingesters
SENSOR_CONFIG = {
    "ais": SensorCharacteristics(
        position_error_m=10,
        speed_error_knots=0.5,
        update_rate_hz=0.2,     # Every 2-10 seconds
        has_identity=True,       # Has MMSI
        sees_dark_ships=False    # Cannot see AIS-off ships
    ),
    "radar": SensorCharacteristics(
        position_error_m=500,
        speed_error_knots=1.0,
        update_rate_hz=1.0,
        has_identity=False,      # Only track_id, no MMSI
        sees_dark_ships=True     # Detects all ships
    ),
    "satellite": SensorCharacteristics(
        position_error_m=2000,
        speed_error_knots=2.0,
        update_rate_hz=0.001,    # Periodic passes
        has_identity=False,
        sees_dark_ships=True     # And flags them with is_dark_ship
    ),
    "drone": SensorCharacteristics(
        position_error_m=50,
        speed_error_knots=1.0,
        update_rate_hz=2.0,
        has_identity=True,       # Visual identification
        sees_dark_ships=True     # Best dark ship detector
    ),
}


@dataclass
class CorrelationGates:
    """Gating thresholds for sensor-to-track correlation"""

    # Spatial gate (based on combined sensor uncertainties)
    max_distance_m: float = 10000     # Maximum gate distance (10km)
    min_distance_m: float = 500       # Minimum gate (prevents too-tight gates)
    sigma_multiplier: float = 4.0     # 4-sigma gate (more permissive)

    # Temporal gate
    max_time_delta_s: float = 120.0   # Max time between correlated detections

    # Velocity gate (kinematic consistency)
    max_speed_change_knots: float = 15.0
    max_course_change_deg: float = 120.0

    # Track confirmation thresholds
    tentative_to_confirmed_updates: int = 3
    coasting_timeout_s: float = 300.0  # 5 minutes
    drop_timeout_s: float = 600.0      # 10 minutes

    # Track uncertainty bounds
    min_position_uncertainty_m: float = 100.0   # Never shrink below this
    max_position_uncertainty_m: float = 5000.0  # Cap uncertainty

    # New track penalty (higher = prefer correlating to existing tracks)
    new_track_cost: float = 0.85      # Was 0.5 - now much harder to create new tracks


@dataclass
class DarkShipDetectionConfig:
    """Configuration for dark ship detection"""

    # AIS gap threshold (time without AIS after last seen)
    ais_gap_threshold_s: float = 900.0  # 15 minutes

    # Minimum correlation with non-AIS sensors to flag as dark
    min_radar_correlations: int = 3
    min_satellite_detections: int = 1
    min_drone_detections: int = 1

    # Confidence thresholds
    dark_ship_high_confidence: float = 0.8
    dark_ship_alert_threshold: float = 0.6

    # Confidence contributions per sensor type
    radar_confidence_boost: float = 0.2
    satellite_confidence_boost: float = 0.1
    drone_confidence_boost: float = 0.3  # Drone visual is strong evidence
