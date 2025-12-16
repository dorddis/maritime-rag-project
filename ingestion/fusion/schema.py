"""
Fusion Schema - Data models for unified tracks

Defines the UnifiedTrack model that combines data from multiple sensors
into a single vessel track with identity and dark ship detection.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Dict, List, Literal
from enum import Enum
import uuid


class TrackStatus(str, Enum):
    """Track lifecycle status"""
    TENTATIVE = "tentative"    # New track, needs confirmation
    CONFIRMED = "confirmed"    # Track confirmed by multiple sensors
    COASTING = "coasting"      # No recent updates, using prediction
    DROPPED = "dropped"        # Track lost


class IdentitySource(str, Enum):
    """Source of vessel identity"""
    AIS = "ais"              # MMSI from AIS transponder
    DRONE_VISUAL = "drone"    # Visual identification from drone
    UNKNOWN = "unknown"       # No identity available


class SensorContribution(BaseModel):
    """Record of a sensor's contribution to a track"""
    sensor_type: Literal["ais", "radar", "satellite", "drone"]
    sensor_id: str                    # e.g., "RAD-MUM", "DRN-001", "SAT-S2A"
    last_update: datetime
    measurement_count: int = 0
    last_position: tuple              # (lat, lon)
    confidence: float = 1.0

    class Config:
        arbitrary_types_allowed = True


class UnifiedTrack(BaseModel):
    """
    Unified vessel track combining data from multiple sensors.

    This is the single source of truth for a physical vessel,
    regardless of which sensors detected it.
    """

    # Track identification
    track_id: str = Field(default_factory=lambda: f"TRK-{uuid.uuid4().hex[:8].upper()}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TrackStatus = TrackStatus.TENTATIVE

    # Position state (fused/filtered)
    latitude: float
    longitude: float
    speed_knots: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None

    # Position uncertainty (1-sigma error in meters)
    position_uncertainty_m: float = 1000.0

    # Velocity state (for prediction)
    velocity_north_ms: float = 0.0
    velocity_east_ms: float = 0.0

    # Identity (may be unknown for dark ships)
    identity_source: IdentitySource = IdentitySource.UNKNOWN
    mmsi: Optional[str] = None
    ship_name: Optional[str] = None
    vessel_type: Optional[str] = None
    vessel_length_m: Optional[float] = None

    # DARK SHIP DETECTION
    is_dark_ship: bool = False
    dark_ship_confidence: float = 0.0   # 0-1, how confident we are this is dark
    ais_last_seen: Optional[datetime] = None
    ais_gap_seconds: Optional[float] = None

    # Sensor contributions
    sensor_contributions: Dict[str, SensorContribution] = Field(default_factory=dict)
    contributing_sensors: List[str] = Field(default_factory=list)

    # Track quality metrics
    track_quality: int = 0             # 0-100
    correlation_confidence: float = 0.0 # 0-1
    update_count: int = 0

    # Alert status
    flagged_for_review: bool = False
    alert_reason: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def to_redis_dict(self) -> dict:
        """Convert to Redis hash format (all string values)"""
        return {
            "track_id": self.track_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "latitude": str(self.latitude),
            "longitude": str(self.longitude),
            "speed_knots": str(self.speed_knots or 0),
            "course": str(self.course or 0),
            "heading": str(self.heading or 0),
            "position_uncertainty_m": str(self.position_uncertainty_m),
            "velocity_north_ms": str(self.velocity_north_ms),
            "velocity_east_ms": str(self.velocity_east_ms),
            "identity_source": self.identity_source.value,
            "mmsi": self.mmsi or "",
            "ship_name": self.ship_name or "",
            "vessel_type": self.vessel_type or "",
            "vessel_length_m": str(self.vessel_length_m or 0),
            "is_dark_ship": str(self.is_dark_ship),
            "dark_ship_confidence": str(self.dark_ship_confidence),
            "ais_last_seen": self.ais_last_seen.isoformat() if self.ais_last_seen else "",
            "ais_gap_seconds": str(self.ais_gap_seconds or 0),
            "contributing_sensors": ",".join(self.contributing_sensors),
            "track_quality": str(self.track_quality),
            "correlation_confidence": str(self.correlation_confidence),
            "update_count": str(self.update_count),
            "flagged_for_review": str(self.flagged_for_review),
            "alert_reason": self.alert_reason or "",
        }

    @classmethod
    def from_redis_dict(cls, data: dict) -> "UnifiedTrack":
        """Create UnifiedTrack from Redis hash data"""
        contributing = data.get("contributing_sensors", "")
        sensors = contributing.split(",") if contributing else []

        ais_last = data.get("ais_last_seen", "")
        ais_last_dt = datetime.fromisoformat(ais_last) if ais_last else None

        return cls(
            track_id=data.get("track_id", ""),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            status=TrackStatus(data.get("status", "tentative")),
            latitude=float(data.get("latitude", 0)),
            longitude=float(data.get("longitude", 0)),
            speed_knots=float(data.get("speed_knots", 0)) or None,
            course=float(data.get("course", 0)) or None,
            heading=float(data.get("heading", 0)) or None,
            position_uncertainty_m=float(data.get("position_uncertainty_m", 1000)),
            velocity_north_ms=float(data.get("velocity_north_ms", 0)),
            velocity_east_ms=float(data.get("velocity_east_ms", 0)),
            identity_source=IdentitySource(data.get("identity_source", "unknown")),
            mmsi=data.get("mmsi") or None,
            ship_name=data.get("ship_name") or None,
            vessel_type=data.get("vessel_type") or None,
            vessel_length_m=float(data.get("vessel_length_m", 0)) or None,
            is_dark_ship=data.get("is_dark_ship", "False") == "True",
            dark_ship_confidence=float(data.get("dark_ship_confidence", 0)),
            ais_last_seen=ais_last_dt,
            ais_gap_seconds=float(data.get("ais_gap_seconds", 0)) or None,
            contributing_sensors=sensors,
            track_quality=int(data.get("track_quality", 0)),
            correlation_confidence=float(data.get("correlation_confidence", 0)),
            update_count=int(data.get("update_count", 0)),
            flagged_for_review=data.get("flagged_for_review", "False") == "True",
            alert_reason=data.get("alert_reason") or None,
        )
