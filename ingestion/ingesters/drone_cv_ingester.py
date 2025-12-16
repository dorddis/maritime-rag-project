"""
Drone CV Ingester

Standalone process that:
- Reads from shared fleet (unified simulation) OR file directory
- Simulates drone patrol operations in specific zones
- Highest accuracy and detail - visual identification
- CAN SEE AND IDENTIFY dark ships (read hull markings)
- Limited range (patrol zones ~20-30nm radius)
- Publishes to Redis stream 'drone:detections'

In unified mode, this ingester simulates maritime patrol drones that
operate in specific coastal/strategic zones and can visually identify
vessels including those with AIS transponders disabled.

Usage:
    python -m ingestion.ingesters.drone_cv_ingester --source unified
    python -m ingestion.ingesters.drone_cv_ingester --watch-dir ./data/drone
"""

import argparse
import asyncio
import logging
import math
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set, List, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingestion.parsers.drone_cv_parser import DroneCVParser
from ingestion.generators.drone_generator import DroneCVGenerator
from ingestion.schema import DroneDetection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - DRONE_INGESTER - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Drone Patrol Zones (strategic locations in Indian Ocean)
PATROL_ZONES = [
    {"id": "DRN-001", "name": "Mumbai Approach", "lat": 18.8, "lon": 72.5, "radius_nm": 25, "active_prob": 0.7},
    {"id": "DRN-002", "name": "Lakshadweep", "lat": 10.5, "lon": 72.6, "radius_nm": 30, "active_prob": 0.5},
    {"id": "DRN-003", "name": "Andaman Passage", "lat": 12.0, "lon": 92.7, "radius_nm": 35, "active_prob": 0.6},
    {"id": "DRN-004", "name": "Gulf of Kutch", "lat": 22.5, "lon": 69.0, "radius_nm": 20, "active_prob": 0.8},
    {"id": "DRN-005", "name": "Colombo Approach", "lat": 7.0, "lon": 79.5, "radius_nm": 20, "active_prob": 0.6},
]

# Object classes for CV detection
OBJECT_CLASSES = [
    "vessel", "cargo_ship", "tanker", "container_ship", "fishing_boat",
    "speedboat", "yacht", "naval_vessel", "unknown_vessel"
]


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in nautical miles between two points"""
    R = 3440.065  # Earth radius in nautical miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class DroneCVIngester:
    """
    Ingests drone CV detection data simulating patrol drone operations.

    Sensor Characteristics:
    - HIGHEST ACCURACY: ~50m position error (best of all sensors)
    - VISUAL IDENTIFICATION: Can read hull markings, identify vessel type
    - CAN SEE DARK SHIPS: Visual detection doesn't rely on transponders
    - SMALL PATROL ZONES: Each drone covers ~20-35nm radius
    - DETAILED METADATA: Bounding boxes, confidence scores, vessel dimensions

    In unified mode, simulates patrol drones operating in specific
    strategic zones that can visually identify vessels.
    """

    STREAM_NAME = "drone:detections"
    STATUS_KEY = "ingester:drone:status"

    # Drone sensor characteristics
    POSITION_ERROR_M = 50  # ~50m accuracy (best of all sensors)
    DETECTION_PROB = 0.95  # Very high detection rate when in range
    LENGTH_ERROR_M = 5  # ±5m vessel dimension estimation (very accurate)
    IMAGE_CAPTURE_PROB = 0.8  # 80% chance of image capture per detection

    def __init__(
        self,
        redis_client=None,
        source: str = "unified",
        watch_dir: Optional[str] = None,
        rate_hz: float = 0.5
    ):
        self.redis = redis_client
        self.source = source
        self.watch_dir = Path(watch_dir) if watch_dir else None
        self.rate_hz = rate_hz
        self.parser = DroneCVParser()
        self.generator: Optional[DroneCVGenerator] = None
        self.fleet_manager = None
        self.running = False

        # Frame counter for unified mode
        self.frame_counter = 0

        # Track processed files (for watch mode)
        self.processed_files: Set[str] = set()

        # Stats
        self.frames_processed = 0
        self.detections_published = 0
        self.dark_ships_identified = 0
        self.active_zones = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None

    async def _init_fleet_manager(self):
        """Initialize fleet manager for unified source"""
        if self.source == "unified" and self.redis is not None:
            from ingestion.shared.fleet_manager import FleetManager
            self.fleet_manager = FleetManager(self.redis)
            logger.info("Initialized fleet manager for unified simulation")
            logger.info(f"Active patrol zones: {len(PATROL_ZONES)}")
            for zone in PATROL_ZONES:
                logger.info(f"  {zone['id']} ({zone['name']}): "
                           f"radius={zone['radius_nm']}nm, active={zone['active_prob']:.0%}")

    def _init_generator(self):
        """Initialize mock generator"""
        if self.source == "mock":
            output_dir = self.watch_dir or "./data/drone"
            self.generator = DroneCVGenerator(output_dir=str(output_dir))
            logger.info(f"Initialized mock generator, output to {output_dir}")

    def _add_position_error(self, lat: float, lon: float) -> Tuple[float, float]:
        """Add realistic drone position error (~50m - very accurate)"""
        error_deg = self.POSITION_ERROR_M / 111000  # ~111km per degree
        return (
            lat + random.uniform(-error_deg, error_deg),
            lon + random.uniform(-error_deg, error_deg)
        )

    def _map_vessel_type_to_class(self, vessel_type: str) -> str:
        """Map vessel type to CV detection class"""
        type_mapping = {
            "cargo": "cargo_ship",
            "tanker": "tanker",
            "container": "container_ship",
            "fishing": "fishing_boat",
            "passenger": "vessel",
            "naval": "naval_vessel",
            "tug": "vessel",
            "unknown": "unknown_vessel",
        }
        return type_mapping.get(vessel_type, "vessel")

    def _generate_bounding_box(self, length_m: float, width_m: float) -> dict:
        """Generate realistic CV bounding box based on vessel dimensions"""
        # Simulate camera frame coordinates (normalized 0-1)
        # Position varies based on where ship is in frame
        x = random.uniform(0.1, 0.7)
        y = random.uniform(0.1, 0.7)

        # Box size roughly proportional to vessel size (scaled)
        # Larger ships = larger bounding boxes
        w = min(0.4, 0.05 + length_m / 2000)
        h = min(0.3, 0.03 + width_m / 500)

        return {
            "x": round(x, 3),
            "y": round(y, 3),
            "w": round(w, 3),
            "h": round(h, 3)
        }

    async def _process_unified(self):
        """Process ships from shared fleet within patrol zones"""
        if self.fleet_manager is None:
            return

        self.frame_counter += 1
        ships = await self.fleet_manager.get_all_ships()
        self.active_zones = 0

        for zone in PATROL_ZONES:
            # Check if drone is active in this zone (random patrol schedule)
            if random.random() > zone["active_prob"]:
                continue

            self.active_zones += 1
            zone_detections = 0
            zone_dark = 0

            # Generate frame ID for this zone
            frame_id = f"{zone['id']}-F{self.frame_counter:06d}"

            for ship in ships:
                # Calculate distance from zone center
                distance = haversine_distance(
                    zone["lat"], zone["lon"],
                    ship.latitude, ship.longitude
                )

                # Out of range - drone cannot see this ship
                if distance > zone["radius_nm"]:
                    continue

                # Detection probability check
                if random.random() > self.DETECTION_PROB:
                    continue

                # Add position error (drone is very accurate)
                lat, lon = self._add_position_error(ship.latitude, ship.longitude)

                # Estimate vessel dimensions (very accurate)
                estimated_length = ship.length_m + random.uniform(-self.LENGTH_ERROR_M, self.LENGTH_ERROR_M)
                estimated_width = ship.width_m + random.uniform(-self.LENGTH_ERROR_M/2, self.LENGTH_ERROR_M/2)

                # DRONE CAN SEE AND IDENTIFY DARK SHIPS
                is_dark = not ship.ais_enabled

                # Drone can read hull markings - provide visual_name
                # For dark ships, this is the only way to identify them
                visual_name = ship.name if random.random() < 0.9 else "UNREADABLE"

                # Create detection
                detection = DroneDetection(
                    detection_id=f"{frame_id}-{ship.mmsi[-4:]}",
                    drone_id=zone["id"],
                    timestamp=datetime.now(timezone.utc),
                    latitude=lat,
                    longitude=lon,
                    confidence=self.DETECTION_PROB * random.uniform(0.9, 1.0),
                    object_class=self._map_vessel_type_to_class(ship.vessel_type),
                    bounding_box=self._generate_bounding_box(ship.length_m, ship.width_m),
                    estimated_length_m=max(10, estimated_length),
                    estimated_width_m=max(3, estimated_width),
                    frame_id=frame_id
                )

                # Add extra metadata for dark ship identification
                if hasattr(detection, 'raw_payload'):
                    detection.raw_payload = {
                        "visual_name": visual_name,
                        "is_dark_ship": is_dark,
                        "mmsi_if_ais_on": ship.mmsi if ship.ais_enabled else None,
                        "patrol_zone": zone["name"],
                        "image_captured": random.random() < self.IMAGE_CAPTURE_PROB,
                    }

                await self._publish_detection(detection)
                zone_detections += 1

                if is_dark:
                    zone_dark += 1
                    self.dark_ships_identified += 1

            if zone_detections > 0:
                logger.debug(f"Zone {zone['id']}: {zone_detections} detections, "
                           f"{zone_dark} dark ships")

    def _scan_directory(self) -> list:
        """Scan watch directory for new JSON files"""
        if not self.watch_dir or not self.watch_dir.exists():
            return []

        new_files = []
        for filepath in self.watch_dir.glob('*.json'):
            if str(filepath) not in self.processed_files:
                new_files.append(filepath)

        return sorted(new_files, key=lambda x: x.stat().st_mtime)

    def _process_frame(self, frame_data: dict) -> list:
        """Parse frame and return list of DroneDetection"""
        detections = []

        try:
            metadata, parsed = self.parser.parse_frame(frame_data)

            for det in parsed:
                detection = DroneDetection(
                    detection_id=det.detection_id,
                    drone_id=metadata.drone_id,
                    timestamp=metadata.timestamp,
                    latitude=det.latitude,
                    longitude=det.longitude,
                    confidence=det.confidence,
                    object_class=det.object_class,
                    bounding_box={
                        "x": det.bbox_x,
                        "y": det.bbox_y,
                        "w": det.bbox_width,
                        "h": det.bbox_height
                    },
                    estimated_length_m=det.estimated_length_m,
                    estimated_width_m=det.estimated_width_m,
                    frame_id=metadata.frame_id
                )
                detections.append(detection)

            logger.debug(f"Parsed frame {metadata.frame_id}: {len(detections)} detections")

        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            self.errors += 1

        return detections

    async def _publish_detection(self, detection: DroneDetection):
        """Publish detection to Redis stream"""
        if self.redis is None:
            logger.debug(f"Would publish: {detection.detection_id}, "
                        f"class={detection.object_class}, "
                        f"conf={detection.confidence:.2f}")
            return

        try:
            await self.redis.xadd(
                self.STREAM_NAME,
                detection.to_redis_dict(),
                maxlen=10000
            )
            self.detections_published += 1
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")
            self.errors += 1

    async def _update_status(self):
        """Update status in Redis for admin dashboard"""
        if self.redis is None:
            return

        status = {
            "running": str(self.running),
            "source": self.source,
            "watch_dir": str(self.watch_dir) if self.watch_dir else "",
            "frames_processed": self.frames_processed,
            "detections_published": self.detections_published,
            "dark_ships_identified": self.dark_ships_identified,
            "active_zones": self.active_zones,
            "total_zones": len(PATROL_ZONES),
            "errors": self.errors,
            "rate_hz": self.rate_hz,
            "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds()
                if self.start_time else 0,
            "last_update": datetime.now(timezone.utc).isoformat()
        }

        try:
            await self.redis.hset(self.STATUS_KEY, mapping=status)
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    async def run_once(self):
        """Process one cycle"""
        if self.source == "unified":
            await self._process_unified()
            self.frames_processed += 1
        elif self.source == "mock":
            # Generate a new frame
            if self.generator is None:
                self._init_generator()

            frame_data = self.generator.generate_frame()
            detections = self._process_frame(frame_data)

            for detection in detections:
                await self._publish_detection(detection)

            self.frames_processed += 1

        else:
            # Watch mode - scan for new files
            new_files = self._scan_directory()

            for filepath in new_files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        import json
                        frame_data = json.load(f)

                    detections = self._process_frame(frame_data)

                    for detection in detections:
                        await self._publish_detection(detection)

                    self.processed_files.add(str(filepath))
                    self.frames_processed += 1

                except Exception as e:
                    logger.error(f"Error processing {filepath}: {e}")
                    self.errors += 1

    async def run(self):
        """Main run loop"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        # Initialize fleet manager for unified mode
        await self._init_fleet_manager()

        if self.source == "unified":
            mode = f"UNIFIED ({len(PATROL_ZONES)} patrol zones)"
        elif self.source == "mock":
            mode = "mock generation"
        else:
            mode = f"watching {self.watch_dir}"
        logger.info(f"Starting Drone CV Ingester ({mode}, rate={self.rate_hz}Hz)")

        try:
            while self.running:
                batch_start = time.time()

                await self.run_once()
                await self._update_status()

                # Rate limiting
                elapsed = time.time() - batch_start
                sleep_time = max(0, (1.0 / self.rate_hz) - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Log stats periodically
                if self.frames_processed % 10 == 0 and self.frames_processed > 0:
                    logger.info(
                        f"Stats: frames={self.frames_processed}, "
                        f"detections={self.detections_published}, "
                        f"dark_ships={self.dark_ships_identified}, "
                        f"active_zones={self.active_zones}"
                    )

        except asyncio.CancelledError:
            logger.info("Ingester cancelled")
        except Exception as e:
            logger.error(f"Ingester error: {e}")
            raise
        finally:
            self.running = False
            await self._update_status()
            logger.info("Ingester stopped")

    def stop(self):
        """Stop the ingester"""
        self.running = False


async def main():
    parser = argparse.ArgumentParser(description="Drone CV Ingester")
    parser.add_argument(
        "--source",
        default="unified",
        help="Data source: 'unified' (shared fleet), 'mock', or 'watch' for file monitoring"
    )
    parser.add_argument(
        "--watch-dir",
        default="./data/drone",
        help="Directory to watch for new JSON files"
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.5,
        help="Processing rate in Hz"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis connection URL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without Redis connection"
    )

    args = parser.parse_args()

    # Create watch directory if needed (for watch/mock modes)
    if args.source in ["watch", "mock"]:
        watch_path = Path(args.watch_dir)
        watch_path.mkdir(parents=True, exist_ok=True)

    # Connect to Redis
    redis_client = None
    if not args.dry_run:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(args.redis_url)
            await redis_client.ping()
            logger.info(f"Connected to Redis at {args.redis_url}")
        except ImportError:
            logger.warning("redis package not installed, running in dry-run mode")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}, running in dry-run mode")

    # Create and run ingester
    ingester = DroneCVIngester(
        redis_client=redis_client,
        source=args.source,
        watch_dir=args.watch_dir,
        rate_hz=args.rate
    )

    try:
        await ingester.run()
    finally:
        if redis_client:
            await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
