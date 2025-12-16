"""
AIS NMEA Ingester

Standalone process that:
- Reads from shared fleet (unified simulation) OR mock generator
- Simulates AIS transponder behavior (only ships with AIS ON)
- Converts to MaritimePosition schema
- Publishes to Redis stream 'ais:positions'

In unified mode, this ingester reads from the shared fleet and only
reports ships that have their AIS transponder enabled.

Usage:
    python -m ingestion.ingesters.ais_nmea_ingester --source unified
    python -m ingestion.ingesters.ais_nmea_ingester --source mock --ships 100
"""

import argparse
import asyncio
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingestion.parsers.nmea_parser import NMEAParser
from ingestion.generators.nmea_generator import NMEAGenerator
from ingestion.schema import MaritimePosition, DataSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - AIS_INGESTER - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AISNMEAIngester:
    """
    Ingests AIS data simulating real AIS receivers.

    Sensor Characteristics:
    - Only sees ships with AIS transponder ON (ais_enabled=True)
    - High accuracy (±10m position error)
    - High frequency (every 2-10 seconds per ship)
    - ~5% packet loss due to transmission issues
    - Global coverage (via satellite AIS + coastal receivers)
    """

    STREAM_NAME = "ais:positions"
    STATUS_KEY = "ingester:ais:status"

    # AIS sensor characteristics
    PACKET_LOSS_RATE = 0.05  # 5% packet loss
    POSITION_ERROR_M = 10  # ±10 meters accuracy
    TRANSMISSION_RATE = 0.8  # 80% of ships transmit per cycle

    def __init__(
        self,
        redis_client=None,
        source: str = "unified",
        num_ships: int = 100,
        rate_hz: float = 1.0
    ):
        self.redis = redis_client
        self.source = source
        self.num_ships = num_ships
        self.rate_hz = rate_hz
        self.parser = NMEAParser()
        self.generator: Optional[NMEAGenerator] = None
        self.fleet_manager = None
        self.running = False

        # Stats
        self.messages_processed = 0
        self.positions_published = 0
        self.dark_ships_skipped = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None

    async def _init_fleet_manager(self):
        """Initialize fleet manager for unified source"""
        if self.source == "unified" and self.redis is not None:
            from ingestion.shared.fleet_manager import FleetManager
            self.fleet_manager = FleetManager(self.redis)
            logger.info("Initialized fleet manager for unified simulation")

    def _init_generator(self):
        """Initialize mock generator if using mock source"""
        if self.source == "mock":
            self.generator = NMEAGenerator(num_ships=self.num_ships)
            logger.info(f"Initialized mock generator with {self.num_ships} ships")

    def _add_position_error(self, lat: float, lon: float) -> tuple:
        """Add realistic AIS position error (±10m)"""
        # Convert meters to degrees (approximate)
        error_deg = self.POSITION_ERROR_M / 111000  # ~111km per degree
        return (
            lat + random.uniform(-error_deg, error_deg),
            lon + random.uniform(-error_deg, error_deg)
        )

    async def _process_unified(self):
        """Process ships from shared fleet (unified simulation)"""
        if self.fleet_manager is None:
            return

        ships = await self.fleet_manager.get_all_ships()

        for ship in ships:
            self.messages_processed += 1

            # AIS CANNOT see dark ships - this is the key behavior
            if not ship.ais_enabled:
                self.dark_ships_skipped += 1
                continue

            # Transmission probability (not all ships transmit every cycle)
            if random.random() > self.TRANSMISSION_RATE:
                continue

            # Packet loss simulation
            if random.random() < self.PACKET_LOSS_RATE:
                continue

            # Add small position error (AIS is very accurate)
            lat, lon = self._add_position_error(ship.latitude, ship.longitude)

            # Create position report
            position = MaritimePosition(
                source=DataSource.AIS,
                timestamp=datetime.now(timezone.utc),
                latitude=lat,
                longitude=lon,
                mmsi=ship.mmsi,
                ship_name=ship.name,
                ship_type=ship.vessel_type,
                speed_knots=ship.speed,
                heading=ship.heading,
                course=ship.course,
                nav_status=str(ship.nav_status),
                vessel_length_m=ship.length_m,
                raw_payload={
                    "source": "unified_fleet",
                    "ais_class": "A" if ship.length_m > 50 else "B",
                }
            )

            await self._publish_position(position)

    def _process_sentence(self, sentence: str) -> Optional[MaritimePosition]:
        """Parse NMEA sentence and convert to MaritimePosition (for mock/file)"""
        try:
            result = self.parser.parse_sentence(sentence)

            if result is None:
                return None

            if 'latitude' not in result or 'longitude' not in result:
                return None

            position = MaritimePosition(
                source=DataSource.AIS,
                timestamp=datetime.now(timezone.utc),
                latitude=result['latitude'],
                longitude=result['longitude'],
                mmsi=result.get('mmsi'),
                ship_name=result.get('ship_name'),
                ship_type=result.get('ship_type'),
                imo=result.get('imo'),
                speed_knots=result.get('speed'),
                heading=result.get('heading'),
                course=result.get('course'),
                nav_status=result.get('nav_status'),
                vessel_length_m=result.get('length'),
                raw_payload={"nmea": sentence, "parsed": result}
            )

            return position

        except Exception as e:
            logger.error(f"Error processing sentence: {e}")
            self.errors += 1
            return None

    async def _publish_position(self, position: MaritimePosition):
        """Publish position to Redis stream"""
        if self.redis is None:
            logger.debug(f"Would publish: MMSI={position.mmsi}, "
                        f"Pos=({position.latitude:.4f}, {position.longitude:.4f})")
            return

        try:
            await self.redis.xadd(
                self.STREAM_NAME,
                position.to_redis_dict(),
                maxlen=10000
            )
            self.positions_published += 1
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
            "positions_published": self.positions_published,
            "dark_ships_skipped": self.dark_ships_skipped,
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
        """Process one batch"""
        if self.source == "unified":
            await self._process_unified()
        elif self.source == "mock":
            if self.generator is None:
                self._init_generator()

            for sentence in self.generator.generate_batch(include_static=True):
                self.messages_processed += 1
                position = self._process_sentence(sentence)
                if position:
                    await self._publish_position(position)
        else:
            # File source
            for sentence in self._read_file_sentences(self.source):
                self.messages_processed += 1
                position = self._process_sentence(sentence)
                if position:
                    await self._publish_position(position)

    def _read_file_sentences(self, filepath: str):
        """Read NMEA sentences from file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and (line.startswith('!') or line.startswith('$')):
                    yield line

    async def run(self):
        """Main run loop"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        # Initialize fleet manager for unified mode
        await self._init_fleet_manager()

        mode = "UNIFIED (shared fleet)" if self.source == "unified" else f"source={self.source}"
        logger.info(f"Starting AIS NMEA Ingester ({mode}, rate={self.rate_hz}Hz)")

        try:
            while self.running:
                batch_start = time.time()

                await self.run_once()
                await self._update_status()

                elapsed = time.time() - batch_start
                sleep_time = max(0, (1.0 / self.rate_hz) - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Log stats periodically
                if self.messages_processed % 500 == 0 and self.messages_processed > 0:
                    logger.info(
                        f"Stats: processed={self.messages_processed}, "
                        f"published={self.positions_published}, "
                        f"dark_skipped={self.dark_ships_skipped}, errors={self.errors}"
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
    parser = argparse.ArgumentParser(description="AIS NMEA Ingester")
    parser.add_argument(
        "--source",
        default="unified",
        help="Data source: 'unified' (shared fleet), 'mock', or path to NMEA file"
    )
    parser.add_argument(
        "--ships",
        type=int,
        default=100,
        help="Number of mock ships (only for mock source)"
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
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

    ingester = AISNMEAIngester(
        redis_client=redis_client,
        source=args.source,
        num_ships=args.ships,
        rate_hz=args.rate
    )

    try:
        await ingester.run()
    finally:
        if redis_client:
            await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
