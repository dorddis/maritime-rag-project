"""
Mock Ship Data Generator
Simulates realistic ship movements at high volume for testing

Features:
- Configurable fleet size (100-10000 ships)
- Realistic movement patterns (not random teleportation)
- Different vessel types with appropriate speeds
- Generates anomalies (speed spikes, dark ships, zone violations)
"""

import asyncio
import random
import math
import os
from datetime import datetime, timezone
from typing import List, Dict
from dataclasses import dataclass, field
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

# Indian Ocean bounds
LAT_MIN, LAT_MAX = 5, 25
LON_MIN, LON_MAX = 65, 100

# Vessel types with realistic speeds (knots)
VESSEL_TYPES = {
    "cargo": {"speed_min": 10, "speed_max": 16, "prefix": "CARGO"},
    "tanker": {"speed_min": 8, "speed_max": 14, "prefix": "TANKER"},
    "container": {"speed_min": 14, "speed_max": 24, "prefix": "CONTAINER"},
    "fishing": {"speed_min": 2, "speed_max": 8, "prefix": "FISHING"},
    "passenger": {"speed_min": 15, "speed_max": 22, "prefix": "CRUISE"},
    "tug": {"speed_min": 4, "speed_max": 12, "prefix": "TUG"},
}

# Major ports for realistic destinations
PORTS = [
    {"name": "Mumbai", "lat": 18.94, "lon": 72.84},
    {"name": "Chennai", "lat": 13.08, "lon": 80.27},
    {"name": "Kochi", "lat": 9.93, "lon": 76.27},
    {"name": "Colombo", "lat": 6.93, "lon": 79.85},
    {"name": "Singapore", "lat": 1.29, "lon": 103.85},
    {"name": "Dubai", "lat": 25.20, "lon": 55.27},
    {"name": "Karachi", "lat": 24.86, "lon": 67.01},
]


@dataclass
class MockShip:
    mmsi: str
    name: str
    vessel_type: str
    latitude: float
    longitude: float
    speed: float
    course: float  # degrees, 0=North, 90=East
    destination: Dict = field(default_factory=dict)
    is_dark: bool = False  # AIS turned off
    dark_until: datetime = None

    def move(self, seconds: float = 1.0):
        """Move ship based on speed and course"""
        if self.is_dark:
            if datetime.now(timezone.utc) > self.dark_until:
                self.is_dark = False
            return

        # Convert speed (knots) to degrees per second
        # 1 knot = 1 nautical mile/hour = 1/60 degree latitude per hour
        distance_nm = (self.speed * seconds) / 3600
        distance_deg = distance_nm / 60

        # Calculate new position
        rad_course = math.radians(self.course)
        self.latitude += distance_deg * math.cos(rad_course)
        self.longitude += distance_deg * math.sin(rad_course) / math.cos(math.radians(self.latitude))

        # Bounce off boundaries
        if self.latitude < LAT_MIN or self.latitude > LAT_MAX:
            self.course = 180 - self.course
            self.latitude = max(LAT_MIN, min(LAT_MAX, self.latitude))
        if self.longitude < LON_MIN or self.longitude > LON_MAX:
            self.course = -self.course
            self.longitude = max(LON_MIN, min(LON_MAX, self.longitude))

        # Normalize course to 0-360
        self.course = self.course % 360

        # Random course adjustments (realistic navigation)
        if random.random() < 0.05:  # 5% chance per update
            self.course += random.uniform(-15, 15)

        # Random speed adjustments
        if random.random() < 0.02:
            type_info = VESSEL_TYPES[self.vessel_type]
            self.speed = random.uniform(type_info["speed_min"], type_info["speed_max"])

    def to_dict(self) -> Dict:
        return {
            "mmsi": self.mmsi,
            "ship_name": self.name,
            "vessel_type": self.vessel_type,
            "latitude": str(round(self.latitude, 6)),
            "longitude": str(round(self.longitude, 6)),
            "speed_knots": str(round(self.speed, 1)),
            "course": str(round(self.course, 1)),
            "heading": str(round(self.course, 1)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "MOCK",
            "is_mock": "true"
        }


class FleetSimulator:
    def __init__(self, num_ships: int = 500):
        self.ships: List[MockShip] = []
        self.redis_client = None
        self.num_ships = num_ships
        self.message_count = 0
        self.start_time = None

    def generate_fleet(self):
        """Generate a fleet of ships"""
        print(f"Generating {self.num_ships} mock ships...")

        for i in range(self.num_ships):
            vessel_type = random.choice(list(VESSEL_TYPES.keys()))
            type_info = VESSEL_TYPES[vessel_type]

            ship = MockShip(
                mmsi=f"MOCK{i:06d}",
                name=f"{type_info['prefix']}_{i:04d}",
                vessel_type=vessel_type,
                latitude=random.uniform(LAT_MIN, LAT_MAX),
                longitude=random.uniform(LON_MIN, LON_MAX),
                speed=random.uniform(type_info["speed_min"], type_info["speed_max"]),
                course=random.uniform(0, 360),
                destination=random.choice(PORTS)
            )
            self.ships.append(ship)

        print(f"Fleet generated: {len(self.ships)} ships")
        for vtype in VESSEL_TYPES:
            count = len([s for s in self.ships if s.vessel_type == vtype])
            print(f"  - {vtype}: {count}")

    async def connect(self):
        self.redis_client = redis.from_url(REDIS_URL)
        await self.redis_client.ping()
        print(f"Connected to Redis")

    def inject_anomalies(self):
        """Randomly inject anomalies for detection testing"""
        for ship in self.ships:
            # Speed spike (1% chance)
            if random.random() < 0.01:
                ship.speed = random.uniform(30, 50)  # Unrealistic speed

            # Dark ship - turn off AIS (0.5% chance)
            if random.random() < 0.005 and not ship.is_dark:
                ship.is_dark = True
                ship.dark_until = datetime.now(timezone.utc)
                # Will be dark for 5-30 seconds
                from datetime import timedelta
                ship.dark_until += timedelta(seconds=random.randint(5, 30))

    async def publish_positions(self):
        """Publish all ship positions to Redis"""
        pipeline = self.redis_client.pipeline()

        for ship in self.ships:
            if not ship.is_dark:
                pipeline.xadd(
                    "maritime:ais-positions",
                    ship.to_dict(),
                    maxlen=100000
                )
                self.message_count += 1

        await pipeline.execute()

    async def run(self, updates_per_second: int = 10, duration_seconds: int = 60):
        """
        Run the simulation

        Args:
            updates_per_second: How many position updates per second (affects Redis commands)
            duration_seconds: How long to run (0 = forever)
        """
        await self.connect()
        self.generate_fleet()
        self.start_time = datetime.now(timezone.utc)

        print(f"\n{'='*60}")
        print(f"SIMULATION STARTED")
        print(f"Ships: {self.num_ships}")
        print(f"Update rate: {updates_per_second}/sec")
        print(f"Expected throughput: ~{self.num_ships * updates_per_second} positions/sec")
        print(f"Duration: {'infinite' if duration_seconds == 0 else f'{duration_seconds}s'}")
        print(f"{'='*60}\n")

        interval = 1.0 / updates_per_second
        iteration = 0

        try:
            while True:
                iteration += 1

                # Move all ships
                for ship in self.ships:
                    ship.move(interval)

                # Inject anomalies occasionally
                if iteration % 10 == 0:
                    self.inject_anomalies()

                # Publish to Redis
                await self.publish_positions()

                # Stats every second
                if iteration % updates_per_second == 0:
                    elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                    rate = self.message_count / elapsed if elapsed > 0 else 0
                    dark_count = len([s for s in self.ships if s.is_dark])
                    stream_len = await self.redis_client.xlen("maritime:ais-positions")

                    print(f"[{elapsed:.0f}s] Published: {self.message_count:,} | Rate: {rate:,.0f}/sec | Stream: {stream_len:,} | Dark ships: {dark_count}")

                # Check duration
                if duration_seconds > 0:
                    elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                    if elapsed >= duration_seconds:
                        break

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping simulation...")

        finally:
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            print(f"\n{'='*60}")
            print(f"SIMULATION COMPLETE")
            print(f"Total messages: {self.message_count:,}")
            print(f"Duration: {elapsed:.1f}s")
            print(f"Average rate: {self.message_count/elapsed:,.0f} positions/sec")
            print(f"{'='*60}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mock Ship Data Generator")
    parser.add_argument("--ships", type=int, default=500, help="Number of ships (default: 500)")
    parser.add_argument("--rate", type=int, default=5, help="Updates per second (default: 5)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (0=forever, default: 60)")
    args = parser.parse_args()

    simulator = FleetSimulator(num_ships=args.ships)
    await simulator.run(updates_per_second=args.rate, duration_seconds=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
