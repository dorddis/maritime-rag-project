"""
Radar Binary Ingester

Standalone process that:
- Reads from shared fleet (unified simulation) OR mock generator
- Simulates coastal radar station behavior
- NO IDENTITY info - only track numbers
- Range-limited detection (50-80nm per station)
- Publishes to Redis stream 'radar:contacts'

In unified mode, this ingester simulates multiple coastal radar stations
that detect ships within their range. Radar does NOT provide identity info,
only track numbers based on position hashing.

Usage:
    python -m ingestion.ingesters.radar_binary_ingester --source unified
    python -m ingestion.ingesters.radar_binary_ingester --source mock --tracks 50
"""

import argparse
import asyncio
import logging
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingestion.parsers.binary_radar_parser import BinaryRadarParser
from ingestion.generators.radar_generator import BinaryRadarGenerator
from ingestion.schema import RadarContact

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - RADAR_INGESTER - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Coastal Radar Stations in Indian Ocean region
RADAR_STATIONS = [
    {"id": "RAD-MUM", "name": "Mumbai", "lat": 18.94, "lon": 72.84, "range_nm": 60},
    {"id": "RAD-CHN", "name": "Chennai", "lat": 13.08, "lon": 80.27, "range_nm": 55},
    {"id": "RAD-COL", "name": "Colombo", "lat": 6.93, "lon": 79.85, "range_nm": 50},
    {"id": "RAD-GOA", "name": "Goa", "lat": 15.50, "lon": 73.83, "range_nm": 45},
    {"id": "RAD-KOC", "name": "Kochi", "lat": 9.97, "lon": 76.27, "range_nm": 50},
    {"id": "RAD-VIS", "name": "Visakhapatnam", "lat": 17.69, "lon": 83.22, "range_nm": 55},
    {"id": "RAD-KAR", "name": "Karachi", "lat": 24.86, "lon": 67.01, "range_nm": 60},
]


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in nautical miles between two points"""
    R = 3440.065  # Earth radius in nautical miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class RadarBinaryIngester:
    """
    Ingests radar data simulating coastal radar stations.

    Sensor Characteristics:
    - Range limited: Each station has 45-60nm range
    - NO IDENTITY: Cannot read AIS/MMSI - only assigns track numbers
    - Position error: ~500m accuracy (worse than AIS)
    - Detection probability: Based on distance and radar cross-section
    - Weather affected: Sea state reduces detection probability
    - CAN SEE DARK SHIPS: Radar doesn't rely on transponders

    In unified mode, reads from shared fleet and applies realistic
    radar detection model per station.
    """

    STREAM_NAME = "radar:contacts"
    STATUS_KEY = "ingester:radar:status"

    # Radar sensor characteristics
    POSITION_ERROR_M = 500  # ±500 meters accuracy
    BASE_DETECTION_PROB = 0.85  # Base probability at optimal range
    WEATHER_FACTOR = 0.95  # Sea state effect (1.0 = calm, 0.5 = rough)
    TRACK_UPDATE_RATE = 0.7  # 70% of tracks update per cycle

    def __init__(
        self,
        redis_client=None,
        source: str = "unified",
        num_tracks: int = 50,
        rate_hz: float = 1.0,
        weather_factor: float = 0.95
    ):
        self.redis = redis_client
        self.source = source
        self.num_tracks = num_tracks
        self.rate_hz = rate_hz
        self.weather_factor = weather_factor
        self.parser = BinaryRadarParser()
        self.generator: Optional[BinaryRadarGenerator] = None
        self.fleet_manager = None
        self.running = False

        # Track ID mapping (MMSI -> track number per station)
        # Radar doesn't know identity, just assigns track numbers
        self.track_mapping: dict = {}

        # Stats
        self.messages_processed = 0
        self.contacts_published = 0
        self.ships_in_range = 0
        self.system_status_count = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None

    async def _init_fleet_manager(self):
        """Initialize fleet manager for unified source"""
        if self.source == "unified" and self.redis is not None:
            from ingestion.shared.fleet_manager import FleetManager
            self.fleet_manager = FleetManager(self.redis)
            logger.info(f"Initialized fleet manager for unified simulation")
            logger.info(f"Active radar stations: {len(RADAR_STATIONS)}")
            for station in RADAR_STATIONS:
                logger.info(f"  {station['id']} ({station['name']}): {station['range_nm']}nm range")

    def _init_generator(self):
        """Initialize mock generator"""
        if self.source == "mock":
            self.generator = BinaryRadarGenerator(num_tracks=self.num_tracks)
            logger.info(f"Initialized mock generator with {self.num_tracks} tracks "
                       f"across {len(self.generator.stations)} stations")

    def _get_track_id(self, station_id: str, mmsi: str) -> str:
        """
        Generate a track ID for a ship at a station.
        Radar doesn't know MMSI - uses consistent track numbering.
        """
        key = f"{station_id}:{mmsi}"
        if key not in self.track_mapping:
            # Assign new track number (T-0001 to T-9999)
            track_num = (hash(key) % 9999) + 1
            self.track_mapping[key] = f"T-{track_num:04d}"
        return self.track_mapping[key]

    def _add_position_error(self, lat: float, lon: float) -> Tuple[float, float]:
        """Add realistic radar position error (~500m)"""
        error_deg = self.POSITION_ERROR_M / 111000  # ~111km per degree
        return (
            lat + random.uniform(-error_deg, error_deg),
            lon + random.uniform(-error_deg, error_deg)
        )

    def _calculate_detection_prob(self, distance_nm: float, range_nm: float, rcs: float) -> float:
        """
        Calculate detection probability based on distance, range and RCS.
        Probability decreases with distance and increases with larger RCS.
        """
        # Normalized distance (0 = at station, 1 = at max range)
        norm_distance = distance_nm / range_nm

        # Base probability decreases with square of distance
        distance_factor = max(0, 1 - norm_distance ** 2)

        # RCS factor (larger ships are easier to detect)
        rcs_factor = min(1.5, 0.5 + rcs * 0.5)

        return self.BASE_DETECTION_PROB * distance_factor * rcs_factor * self.weather_factor

    async def _process_unified(self):
        """Process ships from shared fleet (unified simulation)"""
        if self.fleet_manager is None:
            return

        ships = await self.fleet_manager.get_all_ships()
        self.ships_in_range = 0

        for station in RADAR_STATIONS:
            station_contacts = 0

            for ship in ships:
                self.messages_processed += 1

                # Calculate distance from station
                distance = haversine_distance(
                    station["lat"], station["lon"],
                    ship.latitude, ship.longitude
                )

                # Out of range - radar cannot see this ship
                if distance > station["range_nm"]:
                    continue

                self.ships_in_range += 1

                # Track update probability (not all tracks update every cycle)
                if random.random() > self.TRACK_UPDATE_RATE:
                    continue

                # Detection probability based on distance and RCS
                detection_prob = self._calculate_detection_prob(
                    distance, station["range_nm"], ship.radar_cross_section
                )

                if random.random() > detection_prob:
                    continue

                # Add position error (radar is less accurate than AIS)
                lat, lon = self._add_position_error(ship.latitude, ship.longitude)

                # Create radar contact - NO IDENTITY INFO
                contact = RadarContact(
                    track_id=self._get_track_id(station["id"], ship.mmsi),
                    station_id=station["id"],
                    timestamp=datetime.now(timezone.utc),
                    latitude=lat,
                    longitude=lon,
                    speed_knots=ship.speed + random.uniform(-1, 1),  # Speed error
                    course=ship.course + random.uniform(-5, 5),  # Course error
                    rcs_dbsm=10 * math.log10(ship.radar_cross_section + 0.1),  # Convert to dBsm
                    range_nm=distance,
                    bearing=self._calculate_bearing(
                        station["lat"], station["lon"],
                        ship.latitude, ship.longitude
                    ),
                    quality=int(detection_prob * 100)
                )

                await self._publish_contact(contact)
                station_contacts += 1

            if station_contacts > 0:
                logger.debug(f"Station {station['id']}: {station_contacts} contacts")

    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing from point 1 to point 2"""
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.atan2(x, y)
        return (math.degrees(bearing) + 360) % 360

    def _read_binary_file(self, filepath: str) -> List[bytes]:
        """Read binary messages from file"""
        messages = []
        with open(filepath, 'rb') as f:
            data = f.read()

        # Parse messages based on length field
        offset = 0
        while offset < len(data) - 8:  # At least header size
            msg_length = int.from_bytes(data[offset+2:offset+4], 'big')
            if offset + msg_length > len(data):
                break
            messages.append(data[offset:offset + msg_length])
            offset += msg_length

        return messages

    def _process_message(self, message: bytes) -> Optional[RadarContact]:
        """Parse binary message and convert to RadarContact"""
        try:
            result = self.parser.parse_message(message)

            if result is None:
                return None

            msg_type = result.get('message_type')

            # Track updates become RadarContact
            if msg_type == 'TRACK_UPDATE':
                # Parse timestamp (could be ISO string or epoch)
                ts = result['timestamp']
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                elif isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts, tz=timezone.utc)

                contact = RadarContact(
                    track_id=result['track_id'],
                    station_id=result.get('station_id', "RAD-UNK"),
                    timestamp=ts,
                    latitude=result['latitude'],
                    longitude=result['longitude'],
                    speed_knots=result.get('speed_knots'),
                    course=result.get('course'),
                    rcs_dbsm=result.get('rcs_dbsm'),
                    range_nm=result.get('range_nm'),
                    bearing=result.get('bearing'),
                    quality=result.get('quality', 0)
                )
                return contact

            elif msg_type == 'SYSTEM_STATUS':
                self.system_status_count += 1
                logger.debug(f"System status: station={result.get('station_id')}, "
                           f"tracks={result.get('tracks_active')}")

            return None

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.errors += 1
            return None

    async def _publish_contact(self, contact: RadarContact):
        """Publish contact to Redis stream"""
        if self.redis is None:
            logger.debug(f"Would publish: Track={contact.track_id}, "
                        f"Pos=({contact.latitude:.4f}, {contact.longitude:.4f}), "
                        f"Q={contact.quality}")
            return

        try:
            await self.redis.xadd(
                self.STREAM_NAME,
                contact.to_redis_dict(),
                maxlen=10000
            )
            self.contacts_published += 1
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
            "messages_processed": self.messages_processed,
            "contacts_published": self.contacts_published,
            "ships_in_range": self.ships_in_range,
            "active_stations": len(RADAR_STATIONS),
            "weather_factor": self.weather_factor,
            "system_status_count": self.system_status_count,
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
        """Process one batch of messages"""
        if self.source == "unified":
            await self._process_unified()
        elif self.source == "mock":
            if self.generator is None:
                self._init_generator()

            # Generate batch
            for message in self.generator.generate_batch():
                self.messages_processed += 1

                contact = self._process_message(message)
                if contact:
                    await self._publish_contact(contact)
        else:
            # Read from file
            messages = self._read_binary_file(self.source)
            for message in messages:
                self.messages_processed += 1

                contact = self._process_message(message)
                if contact:
                    await self._publish_contact(contact)

    async def run(self):
        """Main run loop"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        # Initialize fleet manager for unified mode
        await self._init_fleet_manager()

        if self.source == "unified":
            mode = f"UNIFIED ({len(RADAR_STATIONS)} stations, weather={self.weather_factor})"
        else:
            mode = f"source={self.source}"
        logger.info(f"Starting Radar Binary Ingester ({mode}, rate={self.rate_hz}Hz)")

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
                if self.contacts_published % 50 == 0 and self.contacts_published > 0:
                    logger.info(
                        f"Stats: in_range={self.ships_in_range}, "
                        f"contacts={self.contacts_published}, errors={self.errors}"
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
    parser = argparse.ArgumentParser(description="Radar Binary Ingester")
    parser.add_argument(
        "--source",
        default="unified",
        help="Data source: 'unified' (shared fleet), 'mock', or path to binary file"
    )
    parser.add_argument(
        "--tracks",
        type=int,
        default=50,
        help="Number of mock tracks (only for mock source)"
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Processing rate in Hz"
    )
    parser.add_argument(
        "--weather",
        type=float,
        default=0.95,
        help="Weather factor (0.5=rough seas, 1.0=calm)"
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
    ingester = RadarBinaryIngester(
        redis_client=redis_client,
        source=args.source,
        num_tracks=args.tracks,
        rate_hz=args.rate,
        weather_factor=args.weather
    )

    try:
        await ingester.run()
    finally:
        if redis_client:
            await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
