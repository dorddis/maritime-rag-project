"""
Unified Schema for Maritime Data
Normalizes data from multiple sources (AIS, Weather, Satellite)
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal, Any
from enum import Enum
import uuid


class DataSource(str, Enum):
    AIS = "ais"
    WEATHER = "weather"
    SATELLITE = "satellite"
    RADAR = "radar"


class MaritimePosition(BaseModel):
    """Unified position record from any source"""

    # Core fields
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: DataSource
    timestamp: datetime
    latitude: float
    longitude: float

    # Vessel identification (nullable for non-AIS sources)
    mmsi: Optional[int] = None
    ship_name: Optional[str] = None
    ship_type: Optional[str] = None
    imo: Optional[int] = None

    # Movement data
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    course: Optional[float] = None
    nav_status: Optional[int] = None

    # Source-specific metadata
    confidence: Optional[float] = None  # For satellite detections
    vessel_length_m: Optional[float] = None
    raw_payload: Optional[dict] = None

    # Processing metadata
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = False

    def to_redis_dict(self) -> dict:
        """Convert to dict for Redis storage"""
        return {
            "id": self.id,
            "source": self.source.value,
            "timestamp": self.timestamp.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "mmsi": self.mmsi or "",
            "ship_name": self.ship_name or "",
            "speed_knots": self.speed_knots or 0,
            "heading": self.heading or 0,
            "ingested_at": self.ingested_at.isoformat(),
        }


class WeatherObservation(BaseModel):
    """Weather data for a location"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    latitude: float
    longitude: float

    temperature_c: Optional[float] = None
    wind_speed_knots: Optional[float] = None
    wind_direction: Optional[float] = None
    wave_height_m: Optional[float] = None
    visibility_nm: Optional[float] = None
    weather_code: Optional[int] = None

    source: str = "open-meteo"
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class SatelliteDetection(BaseModel):
    """Satellite/radar detection record"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    detection_id: str
    timestamp: datetime
    latitude: float
    longitude: float

    confidence: float
    vessel_length_m: Optional[float] = None
    source_satellite: str

    # Correlation with AIS
    correlated_mmsi: Optional[int] = None
    is_dark_ship: bool = False  # True if no AIS correlation

    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class RadarContact(BaseModel):
    """Radar track contact from coastal/naval radar"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    track_id: str  # Radar-assigned track ID (e.g., "TRK-00000001")
    station_id: str  # Radar station identifier (e.g., "RAD-MUM")
    timestamp: datetime

    # Position
    latitude: float
    longitude: float

    # Kinematics
    speed_knots: Optional[float] = None
    course: Optional[float] = None

    # Radar-specific measurements
    rcs_dbsm: Optional[float] = None  # Radar cross section in dBsm
    range_nm: Optional[float] = None  # Range from station in nautical miles
    bearing: Optional[float] = None  # Bearing from station in degrees
    quality: int = 0  # Track quality (0-100)

    # Correlation with AIS (filled by fusion)
    correlated_mmsi: Optional[int] = None

    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    def to_redis_dict(self) -> dict:
        """Convert to dict for Redis storage"""
        return {
            "id": self.id,
            "track_id": self.track_id,
            "station_id": self.station_id,
            "timestamp": self.timestamp.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed_knots": self.speed_knots or 0,
            "course": self.course or 0,
            "rcs_dbsm": self.rcs_dbsm or 0,
            "range_nm": self.range_nm or 0,
            "bearing": self.bearing or 0,
            "quality": self.quality,
            "correlated_mmsi": self.correlated_mmsi or "",
            "ingested_at": self.ingested_at.isoformat(),
        }


class DroneDetection(BaseModel):
    """Detection from drone/UAV computer vision"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    detection_id: str  # Unique detection identifier
    drone_id: str  # Drone identifier
    timestamp: datetime

    # Position (from drone GPS + offset)
    latitude: float
    longitude: float

    # CV detection properties
    confidence: float  # Detection confidence (0-1)
    object_class: str  # e.g., "vessel", "boat", "ship"
    bounding_box: Optional[dict] = None  # {"x": 0, "y": 0, "w": 100, "h": 50}

    # Estimated vessel properties (from CV)
    estimated_length_m: Optional[float] = None
    estimated_width_m: Optional[float] = None
    estimated_heading: Optional[float] = None

    # Image reference
    frame_id: Optional[str] = None
    image_path: Optional[str] = None

    # Correlation
    correlated_mmsi: Optional[int] = None

    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    def to_redis_dict(self) -> dict:
        """Convert to dict for Redis storage"""
        return {
            "id": self.id,
            "detection_id": self.detection_id,
            "drone_id": self.drone_id,
            "timestamp": self.timestamp.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": self.confidence,
            "object_class": self.object_class,
            "estimated_length_m": self.estimated_length_m or 0,
            "correlated_mmsi": self.correlated_mmsi or "",
            "ingested_at": self.ingested_at.isoformat(),
        }


class AnomalyAlert(BaseModel):
    """Detected anomaly"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    anomaly_type: Literal["speed_spike", "ais_gap", "zone_violation", "dark_ship", "spoofing"]
    severity: Literal["low", "medium", "high", "critical"]

    # Location
    latitude: float
    longitude: float

    # Vessel (if known)
    mmsi: Optional[int] = None
    ship_name: Optional[str] = None

    # Details
    description: str
    evidence: dict = Field(default_factory=dict)

    # Status
    acknowledged: bool = False
    resolved: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
