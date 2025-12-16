"""
Satellite GeoJSON/CSV Parser

Parses satellite detection files in GeoJSON and CSV formats.
Demonstrates understanding of:
- GeoJSON FeatureCollection structure
- Batch metadata handling (pass ID, satellite, acquisition time)
- Multi-format support (GeoJSON + CSV)
- Data provenance tracking

GeoJSON Format:
{
  "type": "FeatureCollection",
  "metadata": {
    "pass_id": "PASS-S2A-20251215-1430",
    "satellite": "Sentinel-2A",
    "acquisition_time": "2025-12-15T14:30:00Z",
    ...
  },
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [lon, lat]},
      "properties": {...}
    }
  ]
}
"""

import json
import csv
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SatellitePassMetadata:
    """Metadata for a satellite pass/acquisition"""
    pass_id: str
    satellite: str
    sensor_type: str  # optical, SAR
    acquisition_time: datetime
    swath_width_km: Optional[float] = None
    resolution_m: Optional[float] = None
    cloud_cover_percent: Optional[float] = None
    processing_level: Optional[str] = None
    detections_count: int = 0


@dataclass
class SatelliteDetection:
    """Single vessel detection from satellite imagery"""
    detection_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    confidence: float
    vessel_length_m: Optional[float] = None
    vessel_width_m: Optional[float] = None
    orientation_deg: Optional[float] = None
    detection_method: Optional[str] = None
    is_dark_ship: bool = False  # No AIS correlation
    pass_id: Optional[str] = None
    satellite: Optional[str] = None
    sensor_type: Optional[str] = None


class SatelliteGeoJSONParser:
    """
    Parser for satellite detection data in GeoJSON and CSV formats.

    Supports:
    - GeoJSON FeatureCollection with batch metadata
    - CSV with header row
    - Automatic format detection by file extension
    """

    # Known satellites and their characteristics
    SATELLITES = {
        "Sentinel-1A": {"type": "SAR", "resolution": 10, "swath": 250},
        "Sentinel-1B": {"type": "SAR", "resolution": 10, "swath": 250},
        "Sentinel-2A": {"type": "optical", "resolution": 10, "swath": 290},
        "Sentinel-2B": {"type": "optical", "resolution": 10, "swath": 290},
        "Planet-Dove": {"type": "optical", "resolution": 3, "swath": 24},
        "Maxar-WV3": {"type": "optical", "resolution": 0.3, "swath": 13},
    }

    def __init__(self):
        self.files_parsed = 0
        self.detections_parsed = 0

    def parse_file(self, filepath: str) -> Tuple[Optional[SatellitePassMetadata], List[SatelliteDetection]]:
        """
        Parse a satellite detection file.

        Automatically detects format by extension.
        Returns: (metadata, list of detections)
        """
        path = Path(filepath)

        if path.suffix.lower() == '.geojson' or path.suffix.lower() == '.json':
            return self.parse_geojson(filepath)
        elif path.suffix.lower() == '.csv':
            return self.parse_csv(filepath)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def parse_geojson(self, filepath: str) -> Tuple[Optional[SatellitePassMetadata], List[SatelliteDetection]]:
        """
        Parse GeoJSON FeatureCollection with batch metadata.

        Expected structure:
        {
          "type": "FeatureCollection",
          "metadata": {...},
          "features": [...]
        }
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if data.get("type") != "FeatureCollection":
            raise ValueError("Invalid GeoJSON: expected FeatureCollection")

        # Parse batch metadata
        meta_raw = data.get("metadata", {})
        metadata = self._parse_metadata(meta_raw)

        # Parse features
        features = data.get("features", [])
        detections = []

        for feature in features:
            detection = self._parse_feature(feature, metadata)
            if detection:
                detections.append(detection)

        # Update metadata with actual count
        if metadata:
            metadata.detections_count = len(detections)

        self.files_parsed += 1
        self.detections_parsed += len(detections)

        return metadata, detections

    def parse_csv(self, filepath: str) -> Tuple[Optional[SatellitePassMetadata], List[SatelliteDetection]]:
        """
        Parse CSV satellite detection file.

        Expected columns:
        pass_id, satellite, detection_id, timestamp, latitude, longitude,
        confidence, length_m, width_m, orientation, is_dark_ship, detection_method
        """
        detections = []
        metadata = None
        pass_id = None
        satellite = None

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                detection = self._parse_csv_row(row)
                if detection:
                    detections.append(detection)

                    # Extract metadata from first row
                    if pass_id is None:
                        pass_id = row.get('pass_id')
                        satellite = row.get('satellite')

        # Create metadata from first row info
        if pass_id and satellite:
            sat_info = self.SATELLITES.get(satellite, {})
            metadata = SatellitePassMetadata(
                pass_id=pass_id,
                satellite=satellite,
                sensor_type=sat_info.get('type', 'unknown'),
                acquisition_time=detections[0].timestamp if detections else datetime.now(timezone.utc),
                resolution_m=sat_info.get('resolution'),
                swath_width_km=sat_info.get('swath'),
                detections_count=len(detections)
            )

        self.files_parsed += 1
        self.detections_parsed += len(detections)

        return metadata, detections

    def _parse_metadata(self, meta: Dict) -> Optional[SatellitePassMetadata]:
        """Parse batch metadata from GeoJSON"""
        if not meta:
            return None

        try:
            acq_time_str = meta.get('acquisition_time', '')
            acq_time = datetime.fromisoformat(acq_time_str.replace('Z', '+00:00')) if acq_time_str else datetime.now(timezone.utc)

            return SatellitePassMetadata(
                pass_id=meta.get('pass_id', f"PASS-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                satellite=meta.get('satellite', 'unknown'),
                sensor_type=meta.get('sensor_type', 'unknown'),
                acquisition_time=acq_time,
                swath_width_km=meta.get('swath_width_km'),
                resolution_m=meta.get('resolution_m'),
                cloud_cover_percent=meta.get('cloud_cover_percent'),
                processing_level=meta.get('processing_level'),
                detections_count=meta.get('detections_count', 0)
            )
        except Exception:
            return None

    def _parse_feature(self, feature: Dict, metadata: Optional[SatellitePassMetadata]) -> Optional[SatelliteDetection]:
        """Parse a single GeoJSON feature to detection"""
        try:
            props = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            # Get coordinates (GeoJSON is [lon, lat])
            coords = geometry.get('coordinates', [0, 0])
            if len(coords) < 2:
                return None

            lon, lat = coords[0], coords[1]

            # Parse timestamp
            ts_str = props.get('timestamp', '')
            timestamp = datetime.fromisoformat(ts_str.replace('Z', '+00:00')) if ts_str else datetime.now(timezone.utc)

            return SatelliteDetection(
                detection_id=props.get('detection_id', feature.get('id', f"DET-{self.detections_parsed}")),
                timestamp=timestamp,
                latitude=lat,
                longitude=lon,
                confidence=float(props.get('confidence', 0.5)),
                vessel_length_m=props.get('vessel_length_m'),
                vessel_width_m=props.get('vessel_width_m'),
                orientation_deg=props.get('orientation_deg'),
                detection_method=props.get('detection_method'),
                is_dark_ship=props.get('is_dark_ship', False),
                pass_id=metadata.pass_id if metadata else None,
                satellite=metadata.satellite if metadata else None,
                sensor_type=metadata.sensor_type if metadata else None,
            )
        except Exception:
            return None

    def _parse_csv_row(self, row: Dict) -> Optional[SatelliteDetection]:
        """Parse a CSV row to detection"""
        try:
            ts_str = row.get('timestamp', '')
            timestamp = datetime.fromisoformat(ts_str.replace('Z', '+00:00')) if ts_str else datetime.now(timezone.utc)

            is_dark = row.get('is_dark_ship', 'false').lower() in ('true', '1', 'yes')

            return SatelliteDetection(
                detection_id=row.get('detection_id', f"DET-{self.detections_parsed}"),
                timestamp=timestamp,
                latitude=float(row.get('latitude', 0)),
                longitude=float(row.get('longitude', 0)),
                confidence=float(row.get('confidence', 0.5)),
                vessel_length_m=float(row['length_m']) if row.get('length_m') else None,
                vessel_width_m=float(row['width_m']) if row.get('width_m') else None,
                orientation_deg=float(row['orientation']) if row.get('orientation') else None,
                detection_method=row.get('detection_method'),
                is_dark_ship=is_dark,
                pass_id=row.get('pass_id'),
                satellite=row.get('satellite'),
            )
        except Exception:
            return None

    def detection_to_dict(self, detection: SatelliteDetection) -> Dict:
        """Convert detection to dictionary for Redis"""
        return {
            "detection_id": detection.detection_id,
            "timestamp": detection.timestamp.isoformat(),
            "latitude": str(detection.latitude),
            "longitude": str(detection.longitude),
            "confidence": str(detection.confidence),
            "vessel_length_m": str(detection.vessel_length_m or 0),
            "vessel_width_m": str(detection.vessel_width_m or 0),
            "orientation_deg": str(detection.orientation_deg or 0),
            "detection_method": detection.detection_method or "unknown",
            "is_dark_ship": str(detection.is_dark_ship),
            "pass_id": detection.pass_id or "",
            "satellite": detection.satellite or "",
            "sensor_type": detection.sensor_type or "",
        }

    def get_stats(self) -> Dict:
        """Get parser statistics"""
        return {
            "files_parsed": self.files_parsed,
            "detections_parsed": self.detections_parsed,
        }


# Demo/test
if __name__ == "__main__":
    import tempfile
    import os

    parser = SatelliteGeoJSONParser()

    print("Satellite GeoJSON Parser Demo")
    print("="*60)

    # Create test GeoJSON
    test_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "pass_id": "PASS-S2A-20251215-1430",
            "satellite": "Sentinel-2A",
            "sensor_type": "optical",
            "acquisition_time": "2025-12-15T14:30:00Z",
            "swath_width_km": 290,
            "resolution_m": 10,
            "cloud_cover_percent": 15,
            "processing_level": "L2A"
        },
        "features": [
            {
                "type": "Feature",
                "id": "SAT-S2A-001",
                "geometry": {
                    "type": "Point",
                    "coordinates": [72.8354, 18.9388]
                },
                "properties": {
                    "detection_id": "SAT-S2A-001",
                    "timestamp": "2025-12-15T14:30:00Z",
                    "confidence": 0.87,
                    "vessel_length_m": 185,
                    "vessel_width_m": 32,
                    "orientation_deg": 245,
                    "detection_method": "vessel_detection_cnn",
                    "is_dark_ship": False
                }
            },
            {
                "type": "Feature",
                "id": "SAT-S2A-002",
                "geometry": {
                    "type": "Point",
                    "coordinates": [72.9000, 18.8500]
                },
                "properties": {
                    "detection_id": "SAT-S2A-002",
                    "timestamp": "2025-12-15T14:30:15Z",
                    "confidence": 0.92,
                    "vessel_length_m": 95,
                    "detection_method": "vessel_detection_cnn",
                    "is_dark_ship": True
                }
            }
        ]
    }

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
        json.dump(test_geojson, f)
        temp_path = f.name

    try:
        metadata, detections = parser.parse_geojson(temp_path)

        print(f"\nMetadata:")
        print(f"  Pass ID: {metadata.pass_id}")
        print(f"  Satellite: {metadata.satellite}")
        print(f"  Acquisition: {metadata.acquisition_time}")
        print(f"  Detections: {metadata.detections_count}")

        print(f"\nDetections:")
        for det in detections:
            dark_marker = " [DARK SHIP]" if det.is_dark_ship else ""
            print(f"  {det.detection_id}: {det.latitude:.4f}, {det.longitude:.4f} "
                  f"(conf: {det.confidence}, len: {det.vessel_length_m}m){dark_marker}")

        print(f"\nParser stats: {parser.get_stats()}")

    finally:
        os.unlink(temp_path)
