"""
Drone CV JSON Generator

Generates mock drone computer vision detection output.
Simulates post-YOLO processing output format.

This represents what would come out of an onboard CV pipeline
after detecting vessels from drone imagery.
"""

import json
import random
import math
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path


@dataclass
class Drone:
    """Drone configuration"""
    drone_id: str
    name: str
    altitude_m: float
    fov_degrees: float  # Field of view
    camera_resolution: tuple  # (width, height)
    speed_knots: float


@dataclass
class DronePosition:
    """Drone's current position"""
    latitude: float
    longitude: float
    altitude_m: float
    heading: float


# Default drones
DRONES = [
    Drone("DRN-001", "Surveillance-Alpha", 500, 60, (4096, 2160), 50),
    Drone("DRN-002", "Surveillance-Beta", 300, 45, (1920, 1080), 40),
    Drone("DRN-003", "Patrol-Gamma", 800, 75, (4096, 2160), 60),
]


class DroneCVGenerator:
    """
    Generate drone CV detection JSON output.

    Simulates YOLO/object detection pipeline output format.
    """

    OBJECT_CLASSES = [
        "vessel", "cargo_ship", "tanker", "fishing_boat",
        "speedboat", "yacht", "unknown_vessel"
    ]

    def __init__(
        self,
        drones: Optional[List[Drone]] = None,
        output_dir: str = "./data/drone"
    ):
        self.drones = drones or DRONES
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frame_count = 0
        self.detection_count = 0

    def _pixel_to_geo(
        self,
        drone_pos: DronePosition,
        drone: Drone,
        x: int,
        y: int
    ) -> tuple:
        """
        Convert pixel coordinates to approximate geo coordinates.

        Very simplified projection - in reality would need camera matrix, etc.
        """
        # Calculate ground coverage based on altitude and FOV
        fov_rad = math.radians(drone.fov_degrees)
        ground_width_m = 2 * drone_pos.altitude_m * math.tan(fov_rad / 2)
        ground_height_m = ground_width_m * drone.camera_resolution[1] / drone.camera_resolution[0]

        # Pixel offset from center
        center_x = drone.camera_resolution[0] / 2
        center_y = drone.camera_resolution[1] / 2
        offset_x = (x - center_x) / drone.camera_resolution[0] * ground_width_m
        offset_y = (y - center_y) / drone.camera_resolution[1] * ground_height_m

        # Convert to degrees (very rough)
        meters_per_degree = 111000
        lat_offset = offset_y / meters_per_degree
        lon_offset = offset_x / (meters_per_degree * math.cos(math.radians(drone_pos.latitude)))

        # Apply heading rotation (simplified)
        heading_rad = math.radians(drone_pos.heading)
        rotated_lat = lat_offset * math.cos(heading_rad) - lon_offset * math.sin(heading_rad)
        rotated_lon = lat_offset * math.sin(heading_rad) + lon_offset * math.cos(heading_rad)

        return (
            drone_pos.latitude + rotated_lat,
            drone_pos.longitude + rotated_lon
        )

    def generate_frame(
        self,
        drone: Optional[Drone] = None,
        drone_pos: Optional[DronePosition] = None,
        num_detections: Optional[int] = None,
        timestamp: Optional[datetime] = None
    ) -> Dict:
        """
        Generate a single frame's CV detection output.

        Returns JSON-serializable dict.
        """
        drone = drone or random.choice(self.drones)
        ts = timestamp or datetime.now(timezone.utc)
        num_det = num_detections if num_detections is not None else random.randint(0, 8)

        # Generate drone position if not provided
        if drone_pos is None:
            drone_pos = DronePosition(
                latitude=random.uniform(8, 22),
                longitude=random.uniform(70, 95),
                altitude_m=drone.altitude_m + random.uniform(-50, 50),
                heading=random.uniform(0, 360)
            )

        self.frame_count += 1
        frame_id = f"{drone.drone_id}-F{self.frame_count:06d}"

        # Generate detections
        detections = []
        for i in range(num_det):
            self.detection_count += 1

            # Random bounding box position
            x = random.randint(100, drone.camera_resolution[0] - 200)
            y = random.randint(100, drone.camera_resolution[1] - 200)
            w = random.randint(30, 200)
            h = random.randint(20, 100)

            # Convert to geo
            center_x = x + w // 2
            center_y = y + h // 2
            lat, lon = self._pixel_to_geo(drone_pos, drone, center_x, center_y)

            # Estimate vessel size from bbox (very rough)
            ground_width_m = 2 * drone_pos.altitude_m * math.tan(math.radians(drone.fov_degrees / 2))
            pixels_per_meter = drone.camera_resolution[0] / ground_width_m
            estimated_length = w / pixels_per_meter
            estimated_width = h / pixels_per_meter

            detection = {
                "detection_id": f"{frame_id}-D{i+1:02d}",
                "class": random.choice(self.OBJECT_CLASSES),
                "confidence": round(random.uniform(0.6, 0.99), 3),
                "bbox": {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h
                },
                "geo_position": {
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6)
                },
                "estimated_dimensions": {
                    "length_m": round(estimated_length, 1),
                    "width_m": round(estimated_width, 1)
                },
                "tracking_id": f"T{random.randint(1, 50):03d}" if random.random() > 0.3 else None
            }

            detections.append(detection)

        return {
            "frame_id": frame_id,
            "timestamp": ts.isoformat(),
            "drone": {
                "drone_id": drone.drone_id,
                "name": drone.name,
                "position": {
                    "latitude": round(drone_pos.latitude, 6),
                    "longitude": round(drone_pos.longitude, 6),
                    "altitude_m": round(drone_pos.altitude_m, 1),
                    "heading": round(drone_pos.heading, 1)
                }
            },
            "image": {
                "width": drone.camera_resolution[0],
                "height": drone.camera_resolution[1],
                "format": "jpeg",
                "path": f"/images/{frame_id}.jpg"
            },
            "model": {
                "name": "maritime-yolo-v8",
                "version": "1.2.0",
                "inference_time_ms": random.randint(50, 200)
            },
            "detections_count": len(detections),
            "detections": detections
        }

    def save_frame(
        self,
        frame_data: Dict,
        filename: Optional[str] = None
    ) -> Path:
        """Save frame data to JSON file"""
        if filename is None:
            filename = f"{frame_data['frame_id']}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(frame_data, f, indent=2)

        return filepath

    def generate_and_save(
        self,
        drone: Optional[Drone] = None,
        **kwargs
    ) -> Path:
        """Generate frame and save to file"""
        frame_data = self.generate_frame(drone=drone, **kwargs)
        return self.save_frame(frame_data)

    def generate_patrol(
        self,
        drone: Optional[Drone] = None,
        duration_minutes: int = 30,
        frame_interval_seconds: int = 5
    ) -> List[Dict]:
        """
        Generate a full patrol worth of frames.

        Returns list of frame data dicts.
        """
        drone = drone or random.choice(self.drones)

        # Starting position
        pos = DronePosition(
            latitude=random.uniform(8, 22),
            longitude=random.uniform(70, 95),
            altitude_m=drone.altitude_m,
            heading=random.uniform(0, 360)
        )

        start_time = datetime.now(timezone.utc)
        frames = []

        num_frames = (duration_minutes * 60) // frame_interval_seconds

        for i in range(num_frames):
            # Update timestamp
            ts = start_time + timedelta(seconds=i * frame_interval_seconds)

            # Move drone
            distance_nm = (drone.speed_knots * frame_interval_seconds) / 3600
            distance_deg = distance_nm / 60
            pos.latitude += distance_deg * math.cos(math.radians(pos.heading))
            pos.longitude += distance_deg * math.sin(math.radians(pos.heading)) / math.cos(math.radians(pos.latitude))

            # Occasional heading change
            if random.random() < 0.1:
                pos.heading = (pos.heading + random.uniform(-30, 30)) % 360

            # Generate frame
            frame = self.generate_frame(
                drone=drone,
                drone_pos=pos,
                timestamp=ts
            )
            frames.append(frame)

        return frames

    def get_stats(self) -> dict:
        """Get generator statistics"""
        return {
            "drones": len(self.drones),
            "frames_generated": self.frame_count,
            "detections_generated": self.detection_count,
            "output_dir": str(self.output_dir),
        }


# Demo/test
if __name__ == "__main__":
    generator = DroneCVGenerator(output_dir="./data/drone")

    print("Drone CV JSON Generator Demo")
    print("=" * 60)

    # Generate a single frame
    frame = generator.generate_frame(num_detections=5)

    print(f"\nFrame: {frame['frame_id']}")
    print(f"Drone: {frame['drone']['name']} at "
          f"({frame['drone']['position']['latitude']:.4f}, "
          f"{frame['drone']['position']['longitude']:.4f})")
    print(f"Altitude: {frame['drone']['position']['altitude_m']}m")
    print(f"Detections: {frame['detections_count']}")

    print("\nDetections:")
    for det in frame['detections']:
        print(f"  {det['detection_id']}: {det['class']} "
              f"(conf: {det['confidence']:.2f}) at "
              f"({det['geo_position']['latitude']:.4f}, "
              f"{det['geo_position']['longitude']:.4f})")

    # Save to file
    filepath = generator.save_frame(frame)
    print(f"\nSaved to: {filepath}")

    print(f"\nStats: {generator.get_stats()}")
