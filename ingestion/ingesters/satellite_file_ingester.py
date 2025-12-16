"""
Satellite File Ingester

Standalone process that:
- Reads from shared fleet (unified simulation) OR file directory
- Simulates satellite passes over the maritime area
- SEES ALL SHIPS including dark ships (key differentiator!)
- Lower accuracy than AIS/Radar (~2km position error)
- Periodic passes (not continuous like AIS/Radar)
- Publishes to Redis stream 'satellite:detections'

In unified mode, this ingester simulates periodic satellite passes that
scan areas of the ocean. Unlike AIS, satellites can detect ships with
their transponders off (dark ships).

Usage:
    python -m ingestion.ingesters.satellite_file_ingester --source unified
    python -m ingestion.ingesters.satellite_file_ingester --watch-dir ./data/satellite
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

from ingestion.parsers.geojson_parser import SatelliteGeoJSONParser
from ingestion.generators.satellite_generator import SatelliteGeoJSONGenerator
from ingestion.schema import SatelliteDetection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SATELLITE_INGESTER - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Simulated Satellites
SATELLITES = [
    {"id": "SAT-S2A", "name": "Sentinel-2A", "type": "optical", "swath_km": 290, "revisit_cycles": 50},
    {"id": "SAT-S1A", "name": "Sentinel-1A", "type": "SAR", "swath_km": 250, "revisit_cycles": 60},
    {"id": "SAT-PL1", "name": "Planet-1", "type": "optical", "swath_km": 24, "revisit_cycles": 30},
    {"id": "SAT-IRS", "name": "ISRO-SAT", "type": "optical", "swath_km": 140, "revisit_cycles": 45},
]

# Simulation area bounds (Indian Ocean)
LAT_MIN, LAT_MAX = 5.0, 25.0
LON_MIN, LON_MAX = 65.0, 100.0


class SatelliteFileIngester:
    """
    Ingests satellite detection data simulating satellite passes.

    Sensor Characteristics:
    - SEES ALL SHIPS: Both AIS-enabled and dark ships
    - Periodic passes: Not continuous, each satellite has revisit time
    - Lower accuracy: ~2km position error (much worse than AIS)
    - SAR vs Optical: SAR works through clouds, optical doesn't
    - Length estimation: Can estimate vessel size (±20m error)
    - Can flag dark ships: Key for maritime surveillance

    In unified mode, simulates satellites passing over the ocean
    and detecting ships in their swath coverage area.
    """

    STREAM_NAME = "satellite:detections"
    STATUS_KEY = "ingester:satellite:status"

    # Satellite sensor characteristics
    POSITION_ERROR_M = 2000  # ~2km accuracy (much worse than AIS/Radar)
    OPTICAL_DETECTION_PROB = 0.85  # Optical in clear weather
    SAR_DETECTION_PROB = 0.95  # SAR sees through clouds
    CLOUD_COVER = 0.3  # 30% average cloud cover
    LENGTH_ERROR_M = 20  # ±20m vessel length estimation

    def __init__(
        self,
        redis_client=None,
        source: str = "unified",
        watch_dir: Optional[str] = None,
        rate_hz: float = 0.1,  # Satellite passes are less frequent
        cloud_cover: float = 0.3
    ):
        self.redis = redis_client
        self.source = source
        self.watch_dir = Path(watch_dir) if watch_dir else None
        self.rate_hz = rate_hz
        self.cloud_cover = cloud_cover
        self.parser = SatelliteGeoJSONParser()
        self.generator: Optional[SatelliteGeoJSONGenerator] = None
        self.fleet_manager = None
        self.running = False

        # Track satellite pass cycles
        self.cycle_count = 0
        self.pass_count = 0

        # Track processed files (for watch mode)
        self.processed_files: Set[str] = set()

        # Stats
        self.files_processed = 0
        self.detections_published = 0
        self.dark_ships_detected = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None

    async def _init_fleet_manager(self):
        """Initialize fleet manager for unified source"""
        if self.source == "unified" and self.redis is not None:
            from ingestion.shared.fleet_manager import FleetManager
            self.fleet_manager = FleetManager(self.redis)
            logger.info("Initialized fleet manager for unified simulation")
            logger.info(f"Active satellites: {len(SATELLITES)}")
            for sat in SATELLITES:
                logger.info(f"  {sat['id']} ({sat['name']}): {sat['type']}, "
                           f"swath={sat['swath_km']}km, revisit={sat['revisit_cycles']} cycles")

    def _init_generator(self):
        """Initialize mock generator"""
        if self.source == "mock":
            output_dir = self.watch_dir or "./data/satellite"
            self.generator = SatelliteGeoJSONGenerator(output_dir=str(output_dir))
            logger.info(f"Initialized mock generator, output to {output_dir}")

    def _add_position_error(self, lat: float, lon: float) -> Tuple[float, float]:
        """Add realistic satellite position error (~2km)"""
        error_deg = self.POSITION_ERROR_M / 111000  # ~111km per degree
        return (
            lat + random.uniform(-error_deg, error_deg),
            lon + random.uniform(-error_deg, error_deg)
        )

    def _generate_swath(self, satellite: dict) -> dict:
        """
        Generate a random swath area for a satellite pass.
        Swath is a rectangular strip across the simulation area.
        """
        swath_deg = satellite["swath_km"] / 111  # Convert km to degrees

        # Random pass direction (north-south or diagonal)
        if random.random() < 0.7:
            # North-south pass
            center_lon = random.uniform(LON_MIN + swath_deg, LON_MAX - swath_deg)
            return {
                "lat_min": LAT_MIN,
                "lat_max": LAT_MAX,
                "lon_min": center_lon - swath_deg / 2,
                "lon_max": center_lon + swath_deg / 2
            }
        else:
            # East-west pass
            center_lat = random.uniform(LAT_MIN + swath_deg, LAT_MAX - swath_deg)
            return {
                "lat_min": center_lat - swath_deg / 2,
                "lat_max": center_lat + swath_deg / 2,
                "lon_min": LON_MIN,
                "lon_max": LON_MAX
            }

    def _is_in_swath(self, lat: float, lon: float, swath: dict) -> bool:
        """Check if a position is within the satellite swath"""
        return (swath["lat_min"] <= lat <= swath["lat_max"] and
                swath["lon_min"] <= lon <= swath["lon_max"])

    def _calculate_detection_prob(self, satellite: dict) -> float:
        """Calculate detection probability based on satellite type and cloud cover"""
        if satellite["type"] == "SAR":
            # SAR sees through clouds
            return self.SAR_DETECTION_PROB
        else:
            # Optical is affected by cloud cover
            return self.OPTICAL_DETECTION_PROB * (1 - self.cloud_cover)

    async def _process_unified(self):
        """Process ships from shared fleet during satellite passes"""
        if self.fleet_manager is None:
            return

        self.cycle_count += 1

        # Check each satellite for pass timing
        for satellite in SATELLITES:
            # Only trigger pass every N cycles (simulates revisit time)
            if self.cycle_count % satellite["revisit_cycles"] != 0:
                continue

            self.pass_count += 1
            pass_id = f"{satellite['id']}-PASS-{self.pass_count:04d}"

            # Generate swath for this pass
            swath = self._generate_swath(satellite)
            detection_prob = self._calculate_detection_prob(satellite)

            logger.info(f"Satellite {satellite['id']} pass started: {pass_id}")
            logger.info(f"  Swath: lat=[{swath['lat_min']:.2f},{swath['lat_max']:.2f}], "
                       f"lon=[{swath['lon_min']:.2f},{swath['lon_max']:.2f}]")

            # Get all ships
            ships = await self.fleet_manager.get_all_ships()
            pass_detections = 0
            pass_dark_ships = 0

            for ship in ships:
                # Check if ship is in swath
                if not self._is_in_swath(ship.latitude, ship.longitude, swath):
                    continue

                # Detection probability check
                if random.random() > detection_prob:
                    continue

                # Add position error
                lat, lon = self._add_position_error(ship.latitude, ship.longitude)

                # Estimate vessel length (with error)
                estimated_length = ship.length_m + random.uniform(-self.LENGTH_ERROR_M, self.LENGTH_ERROR_M)
                estimated_length = max(10, estimated_length)  # Minimum 10m

                # SATELLITE CAN SEE DARK SHIPS - this is the key differentiator!
                is_dark = not ship.ais_enabled

                # Create detection
                detection = SatelliteDetection(
                    detection_id=f"{pass_id}-{ship.mmsi[-4:]}",
                    timestamp=datetime.now(timezone.utc),
                    latitude=lat,
                    longitude=lon,
                    confidence=detection_prob * random.uniform(0.85, 1.0),
                    vessel_length_m=estimated_length,
                    source_satellite=satellite["name"],
                    is_dark_ship=is_dark
                )

                await self._publish_detection(detection)
                pass_detections += 1

                if is_dark:
                    pass_dark_ships += 1
                    self.dark_ships_detected += 1

            logger.info(f"  Pass complete: {pass_detections} detections, "
                       f"{pass_dark_ships} dark ships identified")

    def _scan_directory(self) -> list:
        """Scan watch directory for new files"""
        if not self.watch_dir or not self.watch_dir.exists():
            return []

        new_files = []
        for pattern in ['*.geojson', '*.json', '*.csv']:
            for filepath in self.watch_dir.glob(pattern):
                if str(filepath) not in self.processed_files:
                    new_files.append(filepath)

        return sorted(new_files, key=lambda x: x.stat().st_mtime)

    def _process_file(self, filepath: Path) -> list:
        """Parse file and return list of SatelliteDetection"""
        detections = []

        try:
            if filepath.suffix == '.csv':
                metadata, parsed = self.parser.parse_csv(str(filepath))
            else:
                metadata, parsed = self.parser.parse_file(str(filepath))

            # Handle both dict and dataclass metadata
            if hasattr(metadata, 'satellite'):
                satellite_name = metadata.satellite
                pass_id = metadata.pass_id
            else:
                satellite_name = metadata.get('satellite', 'unknown')
                pass_id = metadata.get('pass_id', filepath.stem)

            for det in parsed:
                detection = SatelliteDetection(
                    detection_id=det.detection_id,
                    timestamp=det.timestamp,
                    latitude=det.latitude,
                    longitude=det.longitude,
                    confidence=det.confidence,
                    vessel_length_m=det.vessel_length_m,
                    source_satellite=satellite_name,
                    is_dark_ship=det.is_dark_ship
                )
                detections.append(detection)

                if det.is_dark_ship:
                    self.dark_ships_detected += 1

            logger.info(f"Parsed {filepath.name}: {len(detections)} detections, "
                       f"{sum(1 for d in parsed if d.is_dark_ship)} dark ships")

        except Exception as e:
            logger.error(f"Error processing file {filepath}: {e}")
            self.errors += 1

        return detections

    async def _publish_detection(self, detection: SatelliteDetection):
        """Publish detection to Redis stream"""
        if self.redis is None:
            logger.debug(f"Would publish: {detection.detection_id}, "
                        f"Pos=({detection.latitude:.4f}, {detection.longitude:.4f}), "
                        f"dark={detection.is_dark_ship}")
            return

        try:
            data = {
                "id": detection.id,
                "detection_id": detection.detection_id,
                "timestamp": detection.timestamp.isoformat(),
                "latitude": detection.latitude,
                "longitude": detection.longitude,
                "confidence": detection.confidence,
                "vessel_length_m": detection.vessel_length_m or 0,
                "source_satellite": detection.source_satellite,
                "is_dark_ship": str(detection.is_dark_ship),
                "ingested_at": detection.ingested_at.isoformat()
            }

            await self.redis.xadd(
                self.STREAM_NAME,
                data,
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
            "files_processed": self.files_processed,
            "pass_count": self.pass_count,
            "cycle_count": self.cycle_count,
            "active_satellites": len(SATELLITES),
            "cloud_cover": self.cloud_cover,
            "detections_published": self.detections_published,
            "dark_ships_detected": self.dark_ships_detected,
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
        elif self.source == "mock":
            # Generate a new satellite pass
            if self.generator is None:
                self._init_generator()

            filepath = self.generator.generate_and_save()
            logger.info(f"Generated mock pass: {filepath}")

            # Process the generated file
            detections = self._process_file(filepath)
            for detection in detections:
                await self._publish_detection(detection)

            self.processed_files.add(str(filepath))
            self.files_processed += 1

        else:
            # Watch mode - scan for new files
            new_files = self._scan_directory()

            for filepath in new_files:
                detections = self._process_file(filepath)

                for detection in detections:
                    await self._publish_detection(detection)

                self.processed_files.add(str(filepath))
                self.files_processed += 1

    async def run(self):
        """Main run loop"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        # Initialize fleet manager for unified mode
        await self._init_fleet_manager()

        if self.source == "unified":
            mode = f"UNIFIED ({len(SATELLITES)} satellites, cloud={self.cloud_cover:.0%})"
        elif self.source == "mock":
            mode = "mock generation"
        else:
            mode = f"watching {self.watch_dir}"
        logger.info(f"Starting Satellite File Ingester ({mode}, rate={self.rate_hz}Hz)")

        try:
            while self.running:
                batch_start = time.time()

                await self.run_once()
                await self._update_status()

                # Rate limiting (satellite passes are slower)
                elapsed = time.time() - batch_start
                sleep_time = max(0, (1.0 / self.rate_hz) - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Log stats periodically
                if self.files_processed % 5 == 0 and self.files_processed > 0:
                    logger.info(
                        f"Stats: files={self.files_processed}, "
                        f"detections={self.detections_published}, "
                        f"dark_ships={self.dark_ships_detected}, "
                        f"errors={self.errors}"
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
    parser = argparse.ArgumentParser(description="Satellite File Ingester")
    parser.add_argument(
        "--source",
        default="unified",
        help="Data source: 'unified' (shared fleet), 'mock', or 'watch' for file monitoring"
    )
    parser.add_argument(
        "--watch-dir",
        default="./data/satellite",
        help="Directory to watch for new satellite files"
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Processing rate in Hz (cycle rate, not pass rate)"
    )
    parser.add_argument(
        "--cloud-cover",
        type=float,
        default=0.3,
        help="Cloud cover fraction (0.0=clear, 1.0=fully cloudy)"
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
            redis_client = redis.from_url(args.redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Connected to Redis at {args.redis_url}")
        except ImportError:
            logger.warning("redis package not installed, running in dry-run mode")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}, running in dry-run mode")

    # Create and run ingester
    ingester = SatelliteFileIngester(
        redis_client=redis_client,
        source=args.source,
        watch_dir=args.watch_dir,
        rate_hz=args.rate,
        cloud_cover=args.cloud_cover
    )

    try:
        await ingester.run()
    finally:
        if redis_client:
            await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
