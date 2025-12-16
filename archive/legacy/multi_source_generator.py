"""
Multi-Source Maritime Data Generator
Simulates ALL data sources for Blurgs-style system:
1. AIS - Ship transponder data (streaming, high volume)
2. Radar - Coastal/ship radar contacts (streaming, medium volume)
3. Satellite - Optical/SAR imagery detections (batch, periodic)
4. Drone - UAV surveillance feeds (streaming, low volume but high fidelity)

This demonstrates multi-format ingestion for interview discussion.
"""

import asyncio
import random
import math
import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

# Indian Ocean bounds
LAT_MIN, LAT_MAX = 5, 25
LON_MIN, LON_MAX = 65, 100

# Radar station locations (coastal)
RADAR_STATIONS = [
    {"id": "RAD-MUM", "name": "Mumbai Coastal", "lat": 18.94, "lon": 72.84, "range_nm": 50},
    {"id": "RAD-CHN", "name": "Chennai Coastal", "lat": 13.08, "lon": 80.27, "range_nm": 50},
    {"id": "RAD-KOC", "name": "Kochi Coastal", "lat": 9.93, "lon": 76.27, "range_nm": 40},
    {"id": "RAD-VIZ", "name": "Vizag Naval", "lat": 17.69, "lon": 83.22, "range_nm": 80},
    {"id": "RAD-KAR", "name": "Karwar Naval", "lat": 14.81, "lon": 74.13, "range_nm": 60},
]

# Satellite passes
SATELLITES = [
    {"id": "SAT-S2A", "name": "Sentinel-2A", "type": "optical", "revisit_hours": 5},
    {"id": "SAT-S1A", "name": "Sentinel-1A", "type": "SAR", "revisit_hours": 6},
    {"id": "SAT-PLN", "name": "Planet-Dove", "type": "optical", "revisit_hours": 1},
    {"id": "SAT-MAX", "name": "Maxar-WV3", "type": "optical", "revisit_hours": 12},
]

# Drone patrol zones
DRONE_ZONES = [
    {"id": "DRN-001", "name": "Mumbai Approach", "lat": 18.8, "lon": 72.5, "radius_nm": 20},
    {"id": "DRN-002", "name": "Lakshadweep Patrol", "lat": 10.5, "lon": 72.6, "radius_nm": 30},
    {"id": "DRN-003", "name": "Andaman Watch", "lat": 11.5, "lon": 92.5, "radius_nm": 25},
]


class DataSource(Enum):
    AIS = "ais"
    RADAR = "radar"
    SATELLITE = "satellite"
    DRONE = "drone"


@dataclass
class Ship:
    """Simulated ship that can be detected by multiple sources"""
    mmsi: str
    name: str
    vessel_type: str
    latitude: float
    longitude: float
    speed: float
    course: float
    ais_enabled: bool = True  # Can be turned off (dark ship)
    radar_cross_section: float = 1.0  # Affects radar detection probability
    length_m: float = 100

    def move(self, seconds: float = 1.0):
        """Update position based on speed and course"""
        distance_nm = (self.speed * seconds) / 3600
        distance_deg = distance_nm / 60

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
        self.course = self.course % 360

        # Random adjustments
        if random.random() < 0.02:
            self.course += random.uniform(-10, 10)
        if random.random() < 0.01:
            self.speed = max(2, self.speed + random.uniform(-2, 2))


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in nautical miles"""
    R = 3440.065  # Earth radius in nm
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class MultiSourceSimulator:
    """
    Simulates realistic multi-source maritime surveillance data.

    Key characteristics per source:
    - AIS: High frequency (every 2-10 sec), all ships with AIS on
    - Radar: Medium frequency (every 10-30 sec), range-limited, weather-affected
    - Satellite: Low frequency (passes every few hours), wide coverage, detects dark ships
    - Drone: Medium frequency, small coverage area, highest detail
    """

    def __init__(self, num_ships: int = 500):
        self.ships: List[Ship] = []
        self.redis_client = None
        self.num_ships = num_ships
        self.stats = {source.value: 0 for source in DataSource}
        self.start_time = None

    def generate_fleet(self):
        """Generate realistic fleet of ships"""
        vessel_types = [
            ("cargo", 0.3, 100, 200, 10, 16),      # type, fraction, min_len, max_len, min_spd, max_spd
            ("tanker", 0.25, 150, 350, 8, 14),
            ("container", 0.2, 200, 400, 14, 24),
            ("fishing", 0.15, 20, 50, 2, 8),
            ("passenger", 0.05, 150, 300, 15, 22),
            ("naval", 0.03, 50, 200, 15, 35),
            ("unknown", 0.02, 30, 100, 5, 15),     # Dark ships, suspicious
        ]

        ship_id = 0
        for vtype, fraction, min_len, max_len, min_spd, max_spd in vessel_types:
            count = int(self.num_ships * fraction)
            for i in range(count):
                ship = Ship(
                    mmsi=f"{vtype.upper()[:3]}{ship_id:06d}",
                    name=f"{vtype.upper()}_{ship_id:04d}",
                    vessel_type=vtype,
                    latitude=random.uniform(LAT_MIN, LAT_MAX),
                    longitude=random.uniform(LON_MIN, LON_MAX),
                    speed=random.uniform(min_spd, max_spd),
                    course=random.uniform(0, 360),
                    ais_enabled=(vtype != "unknown"),  # Unknown ships are dark
                    radar_cross_section=random.uniform(0.5, 2.0) * (max_len / 100),
                    length_m=random.uniform(min_len, max_len)
                )
                self.ships.append(ship)
                ship_id += 1

        print(f"Fleet generated: {len(self.ships)} ships")

    async def connect(self):
        self.redis_client = redis.from_url(REDIS_URL)
        await self.redis_client.ping()
        print("Connected to Redis")

    # ==================== AIS INGESTION ====================
    async def generate_ais(self):
        """
        AIS Data - High frequency streaming
        Format: JSON from AIS receivers
        Rate: ~1000-5000 msg/sec for busy shipping lanes
        """
        pipeline = self.redis_client.pipeline()

        for ship in self.ships:
            if not ship.ais_enabled:
                continue  # Dark ship - no AIS transmission

            # AIS transmission probability varies by ship type
            if random.random() > 0.8:  # 80% of ships transmit per cycle
                continue

            msg = {
                "source": "AIS",
                "mmsi": ship.mmsi,
                "ship_name": ship.name,
                "vessel_type": ship.vessel_type,
                "latitude": str(round(ship.latitude, 6)),
                "longitude": str(round(ship.longitude, 6)),
                "speed_knots": str(round(ship.speed, 1)),
                "course": str(round(ship.course, 1)),
                "heading": str(round(ship.course, 1)),
                "nav_status": "underway",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "receiver": random.choice(["AIS-MUM", "AIS-CHN", "AIS-SAT"])
            }
            pipeline.xadd("maritime:ais-positions", msg, maxlen=500000)
            self.stats["ais"] += 1

        await pipeline.execute()

    # ==================== RADAR INGESTION ====================
    async def generate_radar(self):
        """
        Radar Data - Medium frequency streaming
        Format: Binary/Protocol Buffer (simulated as JSON)
        Rate: ~100-500 contacts/sec across all stations
        Characteristics:
        - Range limited (50-80nm from station)
        - Weather affects detection (rain/sea clutter)
        - No identity info - just position and RCS
        """
        pipeline = self.redis_client.pipeline()
        weather_factor = random.uniform(0.7, 1.0)  # Simulates sea state

        for station in RADAR_STATIONS:
            for ship in self.ships:
                distance = haversine_distance(
                    station["lat"], station["lon"],
                    ship.latitude, ship.longitude
                )

                # Detection probability based on distance and RCS
                if distance > station["range_nm"]:
                    continue

                detection_prob = (1 - distance/station["range_nm"]) * ship.radar_cross_section * weather_factor
                if random.random() > detection_prob:
                    continue

                # Radar doesn't know ship identity - assigns track number
                track_id = f"{station['id']}-T{hash(ship.mmsi) % 10000:04d}"

                msg = {
                    "source": "RADAR",
                    "station_id": station["id"],
                    "station_name": station["name"],
                    "track_id": track_id,
                    "latitude": str(round(ship.latitude + random.uniform(-0.01, 0.01), 6)),  # Radar has position error
                    "longitude": str(round(ship.longitude + random.uniform(-0.01, 0.01), 6)),
                    "speed_knots": str(round(ship.speed + random.uniform(-1, 1), 1)),
                    "course": str(round(ship.course + random.uniform(-5, 5), 1)),
                    "rcs_dbsm": str(round(10 * math.log10(ship.radar_cross_section * 100), 1)),
                    "range_nm": str(round(distance, 1)),
                    "bearing_deg": str(round(random.uniform(0, 360), 1)),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "confidence": str(round(detection_prob, 2))
                }
                pipeline.xadd("maritime:radar", msg, maxlen=200000)
                self.stats["radar"] += 1

        await pipeline.execute()

    # ==================== SATELLITE INGESTION ====================
    async def generate_satellite(self):
        """
        Satellite Data - Batch/periodic
        Format: GeoJSON or CSV from imagery processing
        Rate: Batch every few hours, 100-1000 detections per pass
        Characteristics:
        - Detects ALL ships including dark ships
        - Lower position accuracy than AIS
        - Includes ship length estimate from imagery
        """
        # Simulate a satellite pass every ~60 simulation cycles
        if random.random() > 0.02:  # 2% chance per cycle
            return

        sat = random.choice(SATELLITES)
        pipeline = self.redis_client.pipeline()

        # Satellite sees a swath of the ocean
        swath_center_lat = random.uniform(LAT_MIN + 5, LAT_MAX - 5)
        swath_center_lon = random.uniform(LON_MIN + 10, LON_MAX - 10)
        swath_width = 5  # degrees

        detections = 0
        for ship in self.ships:
            # Check if ship is in swath
            if abs(ship.latitude - swath_center_lat) > swath_width:
                continue
            if abs(ship.longitude - swath_center_lon) > swath_width:
                continue

            # Detection probability based on ship size and satellite type
            if sat["type"] == "SAR":
                detection_prob = 0.95  # SAR sees through clouds
            else:
                detection_prob = 0.85 * random.uniform(0.7, 1.0)  # Cloud cover affects optical

            if random.random() > detection_prob:
                continue

            msg = {
                "source": "SATELLITE",
                "satellite_id": sat["id"],
                "satellite_name": sat["name"],
                "sensor_type": sat["type"],
                "detection_id": f"{sat['id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{detections:03d}",
                "latitude": str(round(ship.latitude + random.uniform(-0.02, 0.02), 6)),
                "longitude": str(round(ship.longitude + random.uniform(-0.02, 0.02), 6)),
                "estimated_length_m": str(round(ship.length_m + random.uniform(-20, 20), 0)),
                "confidence": str(round(random.uniform(0.7, 0.98), 2)),
                "is_dark_ship": str(not ship.ais_enabled),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pass_id": f"PASS-{datetime.now().strftime('%Y%m%d%H%M')}"
            }
            pipeline.xadd("maritime:satellite", msg, maxlen=100000)
            self.stats["satellite"] += 1
            detections += 1

        if detections > 0:
            print(f"  [SATELLITE] {sat['name']} pass: {detections} detections")

        await pipeline.execute()

    # ==================== DRONE INGESTION ====================
    async def generate_drone(self):
        """
        Drone/UAV Data - Real-time streaming
        Format: JSON + image metadata
        Rate: Continuous in patrol zone, ~10-50 contacts/min
        Characteristics:
        - Small coverage area but highest detail
        - Can identify vessel visually
        - Includes image snapshots (simulated as metadata)
        """
        pipeline = self.redis_client.pipeline()

        for zone in DRONE_ZONES:
            # Drone randomly patrols within zone
            if random.random() > 0.3:  # 30% chance drone is active per cycle
                continue

            for ship in self.ships:
                distance = haversine_distance(
                    zone["lat"], zone["lon"],
                    ship.latitude, ship.longitude
                )

                if distance > zone["radius_nm"]:
                    continue

                # Drone gets detailed visual identification
                msg = {
                    "source": "DRONE",
                    "drone_id": zone["id"],
                    "zone_name": zone["name"],
                    "target_mmsi": ship.mmsi if ship.ais_enabled else "UNKNOWN",
                    "target_name": ship.name if ship.ais_enabled else "VISUAL_CONTACT",
                    "vessel_type": ship.vessel_type,
                    "latitude": str(round(ship.latitude, 6)),
                    "longitude": str(round(ship.longitude, 6)),
                    "speed_knots": str(round(ship.speed, 1)),
                    "course": str(round(ship.course, 1)),
                    "estimated_length_m": str(round(ship.length_m, 0)),
                    "visual_confidence": str(round(random.uniform(0.85, 0.99), 2)),
                    "image_id": f"IMG-{zone['id']}-{datetime.now().strftime('%H%M%S%f')[:10]}",
                    "is_dark_ship": str(not ship.ais_enabled),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                pipeline.xadd("maritime:drone", msg, maxlen=50000)
                self.stats["drone"] += 1

        await pipeline.execute()

    async def run(self, duration_seconds: int = 60, updates_per_second: int = 5):
        """Run the multi-source simulation"""
        await self.connect()
        self.generate_fleet()
        self.start_time = datetime.now(timezone.utc)

        print(f"\n{'='*70}")
        print("MULTI-SOURCE MARITIME SIMULATION")
        print(f"{'='*70}")
        print(f"Ships: {len(self.ships)}")
        print(f"Update rate: {updates_per_second}/sec")
        print(f"Duration: {duration_seconds}s")
        print(f"\nData sources:")
        print(f"  - AIS: ~{int(len(self.ships)*0.8)} ships/update (transponder)")
        print(f"  - RADAR: {len(RADAR_STATIONS)} coastal stations")
        print(f"  - SATELLITE: {len(SATELLITES)} satellites (periodic passes)")
        print(f"  - DRONE: {len(DRONE_ZONES)} patrol zones")
        print(f"{'='*70}\n")

        interval = 1.0 / updates_per_second
        iteration = 0

        try:
            while True:
                iteration += 1

                # Move all ships
                for ship in self.ships:
                    ship.move(interval)

                # Randomly toggle AIS (dark ships)
                if random.random() < 0.001:
                    ship = random.choice(self.ships)
                    ship.ais_enabled = not ship.ais_enabled

                # Generate data from all sources
                await asyncio.gather(
                    self.generate_ais(),
                    self.generate_radar(),
                    self.generate_satellite(),
                    self.generate_drone()
                )

                # Stats every second
                if iteration % updates_per_second == 0:
                    elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                    total = sum(self.stats.values())
                    rate = total / elapsed if elapsed > 0 else 0

                    dark_ships = len([s for s in self.ships if not s.ais_enabled])

                    print(f"[{elapsed:3.0f}s] Total: {total:,} | Rate: {rate:,.0f}/sec | "
                          f"AIS: {self.stats['ais']:,} | RADAR: {self.stats['radar']:,} | "
                          f"SAT: {self.stats['satellite']:,} | DRONE: {self.stats['drone']:,} | "
                          f"Dark: {dark_ships}")

                # Check duration
                if duration_seconds > 0:
                    elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                    if elapsed >= duration_seconds:
                        break

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping...")

        finally:
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            total = sum(self.stats.values())

            print(f"\n{'='*70}")
            print("SIMULATION COMPLETE")
            print(f"{'='*70}")
            print(f"Duration: {elapsed:.1f}s")
            print(f"Total messages: {total:,}")
            print(f"Average rate: {total/elapsed:,.0f} msg/sec")
            print(f"\nBreakdown:")
            for source, count in self.stats.items():
                print(f"  {source.upper()}: {count:,} ({count/total*100:.1f}%)")
            print(f"{'='*70}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Source Maritime Data Generator")
    parser.add_argument("--ships", type=int, default=500, help="Number of ships (default: 500)")
    parser.add_argument("--rate", type=int, default=5, help="Updates per second (default: 5)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (default: 60)")
    args = parser.parse_args()

    simulator = MultiSourceSimulator(num_ships=args.ships)
    await simulator.run(updates_per_second=args.rate, duration_seconds=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
