"""
Satellite GeoJSON Generator

Generates satellite detection files in GeoJSON format.
Compatible with geojson_parser.py

Simulates realistic satellite pass behavior:
- Periodic passes over area of interest
- Variable cloud cover (affects optical detection)
- SAR sees through clouds
- Detection confidence varies by conditions
"""

import json
import random
import math
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path


@dataclass
class Satellite:
    """Satellite configuration"""
    satellite_id: str
    name: str
    sensor_type: str  # "optical" or "SAR"
    resolution_m: float
    swath_width_km: float
    revisit_hours: float


@dataclass
class DetectedVessel:
    """Vessel detected by satellite"""
    latitude: float
    longitude: float
    length_m: float
    width_m: float
    orientation_deg: float
    speed_knots: float
    has_ais: bool = True  # If False, this is a "dark ship"


# Default satellites
SATELLITES = [
    Satellite("SAT-S1A", "Sentinel-1A", "SAR", 10, 250, 6),
    Satellite("SAT-S1B", "Sentinel-1B", "SAR", 10, 250, 6),
    Satellite("SAT-S2A", "Sentinel-2A", "optical", 10, 290, 5),
    Satellite("SAT-S2B", "Sentinel-2B", "optical", 10, 290, 5),
    Satellite("SAT-PLN", "Planet-Dove", "optical", 3, 24, 1),
    Satellite("SAT-MAX", "Maxar-WV3", "optical", 0.3, 13, 12),
]


class SatelliteGeoJSONGenerator:
    """
    Generate satellite detection GeoJSON files.

    Simulates satellite passes with realistic detection characteristics.
    """

    def __init__(
        self,
        satellites: Optional[List[Satellite]] = None,
        output_dir: str = "./data/satellite"
    ):
        self.satellites = satellites or SATELLITES
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pass_count = 0
        self.detection_count = 0

    def generate_vessels(
        self,
        num_vessels: int = 50,
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
        spread_deg: float = 2.0
    ) -> List[DetectedVessel]:
        """Generate random vessels in the area of interest.

        If center_lat/lon provided, clusters vessels around that point.
        """
        vessels = []

        for _ in range(num_vessels):
            if center_lat is not None and center_lon is not None:
                # Cluster vessels near swath center for guaranteed detection
                lat = center_lat + random.uniform(-spread_deg, spread_deg)
                lon = center_lon + random.uniform(-spread_deg, spread_deg)
            else:
                # Random across Indian Ocean
                lat = random.uniform(5, 25)
                lon = random.uniform(65, 100)

            vessel = DetectedVessel(
                latitude=lat,
                longitude=lon,
                length_m=random.uniform(50, 400),
                width_m=random.uniform(10, 60),
                orientation_deg=random.uniform(0, 360),
                speed_knots=random.uniform(0, 20),
                has_ais=random.random() > 0.15  # 15% are dark ships
            )
            vessels.append(vessel)

        return vessels

    def generate_pass(
        self,
        satellite: Optional[Satellite] = None,
        vessels: Optional[List[DetectedVessel]] = None,
        cloud_cover_percent: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> Dict:
        """
        Generate a single satellite pass as GeoJSON FeatureCollection.

        Returns GeoJSON dict with metadata and features.
        """
        sat = satellite or random.choice(self.satellites)
        ts = timestamp or datetime.now(timezone.utc)
        cloud_cover = cloud_cover_percent if cloud_cover_percent is not None else random.uniform(0, 50)

        # Generate pass ID
        self.pass_count += 1
        pass_id = f"PASS-{sat.satellite_id}-{ts.strftime('%Y%m%d-%H%M%S')}"

        # Determine swath center (random point in Indian Ocean)
        swath_center_lat = random.uniform(8, 22)
        swath_center_lon = random.uniform(70, 95)
        swath_half_width_deg = sat.swath_width_km / 111  # ~111 km per degree

        # Generate vessels clustered near swath center if not provided
        if vessels is None:
            vessels = self.generate_vessels(
                random.randint(30, 80),
                center_lat=swath_center_lat,
                center_lon=swath_center_lon,
                spread_deg=swath_half_width_deg * 0.8
            )

        # Build metadata
        metadata = {
            "pass_id": pass_id,
            "satellite": sat.name,
            "satellite_id": sat.satellite_id,
            "sensor_type": sat.sensor_type,
            "acquisition_time": ts.isoformat(),
            "swath_center_lat": swath_center_lat,
            "swath_center_lon": swath_center_lon,
            "swath_width_km": sat.swath_width_km,
            "resolution_m": sat.resolution_m,
            "cloud_cover_percent": cloud_cover,
            "processing_level": "L2A",
            "detections_count": 0  # Updated later
        }

        # Generate detections
        features = []
        detection_num = 0

        for vessel in vessels:
            # Check if vessel is in swath
            if abs(vessel.latitude - swath_center_lat) > swath_half_width_deg:
                continue
            if abs(vessel.longitude - swath_center_lon) > swath_half_width_deg * 1.5:
                continue

            # Determine detection probability
            if sat.sensor_type == "SAR":
                # SAR not affected by clouds
                detection_prob = 0.92
            else:
                # Optical affected by cloud cover
                detection_prob = 0.88 * (1 - cloud_cover / 100)

            # Smaller vessels harder to detect
            if vessel.length_m < 100:
                detection_prob *= 0.8
            elif vessel.length_m < 50:
                detection_prob *= 0.6

            if random.random() > detection_prob:
                continue

            # Generate detection
            detection_num += 1
            self.detection_count += 1

            # Add position noise based on resolution
            noise_deg = sat.resolution_m / 111000  # Convert meters to degrees
            lat_noisy = vessel.latitude + random.uniform(-noise_deg, noise_deg)
            lon_noisy = vessel.longitude + random.uniform(-noise_deg, noise_deg)

            # Estimate length with some error
            length_error = random.uniform(-0.1, 0.1) * vessel.length_m
            estimated_length = max(20, vessel.length_m + length_error)

            # Confidence based on conditions
            confidence = detection_prob * random.uniform(0.85, 1.0)

            # Determine detection method based on satellite
            if sat.sensor_type == "SAR":
                detection_method = "sar_ship_detector_cfar"
            else:
                detection_method = "optical_vessel_detection_cnn"

            feature = {
                "type": "Feature",
                "id": f"{pass_id}-{detection_num:03d}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon_noisy, 6), round(lat_noisy, 6)]
                },
                "properties": {
                    "detection_id": f"{pass_id}-{detection_num:03d}",
                    "timestamp": ts.isoformat(),
                    "confidence": round(confidence, 3),
                    "vessel_length_m": round(estimated_length, 1),
                    "vessel_width_m": round(vessel.width_m + random.uniform(-5, 5), 1) if vessel.width_m else None,
                    "orientation_deg": round(vessel.orientation_deg + random.uniform(-10, 10), 1),
                    "detection_method": detection_method,
                    "is_dark_ship": not vessel.has_ais,
                    "pixel_count": int(estimated_length * vessel.width_m / (sat.resolution_m ** 2)),
                    "mean_reflectance": round(random.uniform(0.3, 0.7), 3) if sat.sensor_type == "optical" else None,
                    "sigma0_db": round(random.uniform(-15, -5), 2) if sat.sensor_type == "SAR" else None,
                }
            }

            features.append(feature)

        # Update metadata
        metadata["detections_count"] = len(features)

        return {
            "type": "FeatureCollection",
            "metadata": metadata,
            "features": features
        }

    def save_pass(
        self,
        geojson: Dict,
        filename: Optional[str] = None
    ) -> Path:
        """Save GeoJSON to file"""
        if filename is None:
            pass_id = geojson["metadata"]["pass_id"]
            filename = f"{pass_id}.geojson"

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2)

        return filepath

    def generate_and_save(
        self,
        satellite: Optional[Satellite] = None,
        vessels: Optional[List[DetectedVessel]] = None,
        **kwargs
    ) -> Path:
        """Generate pass and save to file"""
        geojson = self.generate_pass(satellite=satellite, vessels=vessels, **kwargs)
        return self.save_pass(geojson)

    def generate_csv(
        self,
        satellite: Optional[Satellite] = None,
        vessels: Optional[List[DetectedVessel]] = None,
        filename: Optional[str] = None,
        **kwargs
    ) -> Path:
        """Generate satellite detections in CSV format"""
        geojson = self.generate_pass(satellite=satellite, vessels=vessels, **kwargs)

        if filename is None:
            pass_id = geojson["metadata"]["pass_id"]
            filename = f"{pass_id}.csv"

        filepath = self.output_dir / filename
        meta = geojson["metadata"]

        with open(filepath, 'w', encoding='utf-8') as f:
            # Write header
            f.write("pass_id,satellite,detection_id,timestamp,latitude,longitude,"
                   "confidence,length_m,width_m,orientation,is_dark_ship,detection_method\n")

            # Write detections
            for feature in geojson["features"]:
                props = feature["properties"]
                coords = feature["geometry"]["coordinates"]

                f.write(f"{meta['pass_id']},{meta['satellite']},{props['detection_id']},"
                       f"{props['timestamp']},{coords[1]},{coords[0]},"
                       f"{props['confidence']},{props['vessel_length_m'] or ''},"
                       f"{props['vessel_width_m'] or ''},{props['orientation_deg'] or ''},"
                       f"{props['is_dark_ship']},{props['detection_method']}\n")

        return filepath

    def simulate_day(
        self,
        hours: int = 24,
        vessels: Optional[List[DetectedVessel]] = None
    ) -> List[Path]:
        """
        Simulate a day's worth of satellite passes.

        Returns list of generated files.
        """
        vessels = vessels or self.generate_vessels(100)
        files = []
        start_time = datetime.now(timezone.utc)

        for sat in self.satellites:
            # Calculate number of passes in the time period
            num_passes = int(hours / sat.revisit_hours)

            for i in range(num_passes):
                pass_time = start_time + timedelta(hours=i * sat.revisit_hours)
                pass_time += timedelta(minutes=random.randint(-30, 30))  # Add some variation

                # Move vessels between passes
                for v in vessels:
                    # Simple movement based on speed
                    hours_elapsed = sat.revisit_hours
                    distance_nm = v.speed_knots * hours_elapsed
                    distance_deg = distance_nm / 60
                    rad_orient = math.radians(v.orientation_deg)
                    v.latitude += distance_deg * math.cos(rad_orient) * 0.1
                    v.longitude += distance_deg * math.sin(rad_orient) * 0.1
                    v.latitude = max(5, min(25, v.latitude))
                    v.longitude = max(65, min(100, v.longitude))

                # Generate pass
                filepath = self.generate_and_save(
                    satellite=sat,
                    vessels=vessels,
                    timestamp=pass_time
                )
                files.append(filepath)

        return files

    def get_stats(self) -> dict:
        """Get generator statistics"""
        return {
            "satellites": len(self.satellites),
            "passes_generated": self.pass_count,
            "detections_generated": self.detection_count,
            "output_dir": str(self.output_dir),
        }


# Demo/test
if __name__ == "__main__":
    generator = SatelliteGeoJSONGenerator(output_dir="./data/satellite")

    print("Satellite GeoJSON Generator Demo")
    print("="*60)

    # Generate a single pass
    vessels = generator.generate_vessels(50)
    geojson = generator.generate_pass(vessels=vessels)

    print(f"\nPass: {geojson['metadata']['pass_id']}")
    print(f"Satellite: {geojson['metadata']['satellite']}")
    print(f"Sensor: {geojson['metadata']['sensor_type']}")
    print(f"Detections: {geojson['metadata']['detections_count']}")

    # Show some detections
    print("\nSample detections:")
    for feat in geojson['features'][:5]:
        props = feat['properties']
        coords = feat['geometry']['coordinates']
        dark = " [DARK]" if props['is_dark_ship'] else ""
        print(f"  {props['detection_id']}: {coords[1]:.4f}, {coords[0]:.4f} "
              f"(conf: {props['confidence']:.2f}, len: {props['vessel_length_m']}m){dark}")

    # Save to file
    filepath = generator.save_pass(geojson)
    print(f"\nSaved to: {filepath}")

    # Also generate CSV
    csv_path = generator.generate_csv(vessels=vessels)
    print(f"CSV saved to: {csv_path}")

    print(f"\nStats: {generator.get_stats()}")
