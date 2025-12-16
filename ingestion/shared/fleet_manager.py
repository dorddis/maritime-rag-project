"""
Fleet Manager - Ground Truth Ship State

Manages the single source of truth for all ships in the simulation.
All sensors read from this shared state.

Uses realistic Indian Ocean shipping lanes and ocean-only spawning.
"""

import json
import math
import random
import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# Try to import global-land-mask for ocean validation
try:
    from global_land_mask import globe
    HAS_LAND_MASK = True
except ImportError:
    HAS_LAND_MASK = False
    print("Warning: global-land-mask not installed. Using bounding box only.")

# Indian Ocean bounds (realistic for the simulation)
LAT_MIN, LAT_MAX = -5.0, 25.0  # Extended south for more ocean coverage
LON_MIN, LON_MAX = 50.0, 105.0  # Extended west to include Arabian Sea

# =============================================================================
# REALISTIC SHIPPING LANES - Indian Ocean Major Routes
# Based on: https://porteconomicsmanagement.org/pemp/contents/part1/interoceanic-passages/main-maritime-shipping-routes/
# =============================================================================

SHIPPING_LANES = {
    # Main East-West Route: Strait of Malacca to Middle East/Europe
    "malacca_to_gulf": [
        (1.3, 103.8),    # Singapore
        (4.0, 100.0),    # Strait of Malacca exit
        (6.0, 95.0),     # Andaman Sea
        (8.0, 80.0),     # South of Sri Lanka
        (10.0, 72.0),    # Arabian Sea
        (12.5, 65.0),    # Approaching Gulf of Aden
        (12.0, 55.0),    # Gulf of Aden
    ],

    # India West Coast Route
    "india_west_coast": [
        (8.5, 76.9),     # Cochin
        (12.9, 74.8),    # Mangalore
        (15.4, 73.8),    # Goa
        (18.9, 72.8),    # Mumbai
        (22.5, 70.0),    # Kandla/Gulf of Kutch
    ],

    # India East Coast Route
    "india_east_coast": [
        (8.0, 77.5),     # Tuticorin
        (13.1, 80.3),    # Chennai
        (17.7, 83.3),    # Visakhapatnam
        (20.0, 87.0),    # Approaching Kolkata
    ],

    # Bay of Bengal Crossing
    "bay_of_bengal": [
        (1.3, 103.8),    # Singapore
        (6.0, 95.0),     # Andaman Sea
        (10.0, 88.0),    # Central Bay of Bengal
        (13.1, 80.3),    # Chennai
    ],

    # Sri Lanka Hub Routes
    "colombo_hub": [
        (6.9, 79.8),     # Colombo
        (8.0, 77.0),     # South tip of India
        (5.5, 73.0),     # Maldives area
        (10.0, 72.0),    # Arabian Sea
    ],

    # Persian Gulf Route
    "persian_gulf": [
        (12.5, 65.0),    # Gulf of Aden approach
        (15.0, 60.0),    # Arabian Sea
        (22.0, 60.0),    # Approaching Hormuz
        (26.0, 56.5),    # Strait of Hormuz
    ],

    # Southeast Asia to India
    "se_asia_india": [
        (1.3, 103.8),    # Singapore
        (7.0, 98.0),     # Phuket area
        (10.0, 92.0),    # Andaman Islands
        (13.1, 80.3),    # Chennai
        (18.9, 72.8),    # Mumbai
    ],
}

# Flatten all waypoints for spawning ships on lanes
ALL_LANE_WAYPOINTS: List[Tuple[float, float]] = []
for lane in SHIPPING_LANES.values():
    ALL_LANE_WAYPOINTS.extend(lane)

# Major ports for destinations (with coordinates)
MAJOR_PORTS = {
    "SINGAPORE": (1.3, 103.8),
    "MUMBAI": (18.9, 72.8),
    "CHENNAI": (13.1, 80.3),
    "COLOMBO": (6.9, 79.8),
    "DUBAI": (25.2, 55.3),
    "COCHIN": (9.9, 76.3),
    "VISAKHAPATNAM": (17.7, 83.3),
    "KANDLA": (23.0, 70.2),
    "JEDDAH": (21.5, 39.2),
    "KARACHI": (24.8, 67.0),
    "PORT_KLANG": (3.0, 101.4),
    "MUNDRA": (22.8, 69.7),
}


def is_in_ocean(lat: float, lon: float) -> bool:
    """Check if a point is in the ocean (not on land)."""
    if HAS_LAND_MASK:
        return globe.is_ocean(lat, lon)
    # Fallback: simple bounding box check (less accurate)
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def spawn_point_on_lane() -> Tuple[float, float, float, str]:
    """
    Generate a spawn point along a shipping lane.
    Returns (lat, lon, course, lane_name)
    """
    lane_name = random.choice(list(SHIPPING_LANES.keys()))
    lane = SHIPPING_LANES[lane_name]

    # Pick a random segment of the lane
    idx = random.randint(0, len(lane) - 2)
    start = lane[idx]
    end = lane[idx + 1]

    # Random position along the segment
    t = random.random()
    lat = start[0] + t * (end[0] - start[0])
    lon = start[1] + t * (end[1] - start[1])

    # Add small random offset (ships don't travel exactly on the line)
    lat += random.uniform(-0.3, 0.3)
    lon += random.uniform(-0.3, 0.3)

    # Calculate course toward next waypoint
    course = calculate_bearing(lat, lon, end[0], end[1])

    return lat, lon, course, lane_name


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2 in degrees."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360) % 360


def get_next_waypoint(lat: float, lon: float, current_lane: str, current_wp_idx: int) -> Tuple[Tuple[float, float], int]:
    """Get the next waypoint for a ship on a lane."""
    lane = SHIPPING_LANES.get(current_lane, [])
    if not lane:
        # No lane assigned, pick a random port as destination
        port = random.choice(list(MAJOR_PORTS.values()))
        return port, 0

    # Check if we're close to current waypoint
    if current_wp_idx < len(lane):
        wp = lane[current_wp_idx]
        dist = haversine_distance(lat, lon, wp[0], wp[1])
        if dist < 5:  # Within 5 nm, move to next waypoint
            current_wp_idx += 1

    # If we've reached end of lane, reverse or pick new lane
    if current_wp_idx >= len(lane):
        # 50% chance to reverse, 50% to pick new lane
        if random.random() < 0.5:
            lane = list(reversed(lane))
            SHIPPING_LANES[current_lane] = lane  # Update in place
            current_wp_idx = 0
        else:
            new_lane = random.choice(list(SHIPPING_LANES.keys()))
            lane = SHIPPING_LANES[new_lane]
            current_wp_idx = 0

    return lane[min(current_wp_idx, len(lane) - 1)], current_wp_idx


@dataclass
class Ship:
    """Ground truth ship state - the actual ship in the ocean"""
    mmsi: str
    name: str
    vessel_type: str
    latitude: float
    longitude: float
    speed: float  # knots
    course: float  # degrees
    heading: float  # degrees
    ais_enabled: bool = True  # Can be turned off (dark ship)
    radar_cross_section: float = 1.0  # Affects radar detection
    length_m: float = 100.0
    width_m: float = 20.0
    draught_m: float = 8.0
    destination: str = ""
    nav_status: int = 0  # 0 = underway using engine
    # Route tracking
    current_lane: str = ""
    waypoint_idx: int = 0
    target_lat: float = 0.0
    target_lon: float = 0.0

    def move(self, seconds: float = 1.0):
        """Update position based on speed and course, following shipping lanes."""
        # Update target waypoint if needed
        if self.current_lane:
            wp, new_idx = get_next_waypoint(
                self.latitude, self.longitude,
                self.current_lane, self.waypoint_idx
            )
            self.target_lat, self.target_lon = wp
            self.waypoint_idx = new_idx

            # Gradually adjust course toward waypoint
            target_course = calculate_bearing(
                self.latitude, self.longitude,
                self.target_lat, self.target_lon
            )
            # Smooth course adjustment (ships don't turn instantly)
            course_diff = (target_course - self.course + 180) % 360 - 180
            max_turn = 5.0  # Max 5 degrees per second
            self.course = (self.course + max(min(course_diff, max_turn), -max_turn)) % 360

        # Convert speed (knots) to distance traveled
        distance_nm = (self.speed * seconds) / 3600
        distance_deg = distance_nm / 60  # Approximate degrees

        rad_course = math.radians(self.course)
        new_lat = self.latitude + distance_deg * math.cos(rad_course)
        new_lon = self.longitude + distance_deg * math.sin(rad_course) / max(0.1, math.cos(math.radians(self.latitude)))

        # Check if new position is in ocean (land avoidance)
        if is_in_ocean(new_lat, new_lon):
            self.latitude = new_lat
            self.longitude = new_lon
        else:
            # Hit land - turn around
            self.course = (self.course + 180) % 360

        # Keep within simulation bounds
        self.latitude = max(LAT_MIN + 0.5, min(LAT_MAX - 0.5, self.latitude))
        self.longitude = max(LON_MIN + 0.5, min(LON_MAX - 0.5, self.longitude))

        # Update heading (slight drift from course)
        self.heading = (self.course + random.uniform(-3, 3)) % 360

        # Random small speed adjustments (realistic navigation)
        if random.random() < 0.01:
            self.speed = max(1, min(30, self.speed + random.uniform(-0.5, 0.5)))

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage"""
        return {
            "mmsi": self.mmsi,
            "name": self.name,
            "vessel_type": self.vessel_type,
            "latitude": str(self.latitude),
            "longitude": str(self.longitude),
            "speed": str(self.speed),
            "course": str(self.course),
            "heading": str(self.heading),
            "ais_enabled": str(self.ais_enabled),
            "radar_cross_section": str(self.radar_cross_section),
            "length_m": str(self.length_m),
            "width_m": str(self.width_m),
            "draught_m": str(self.draught_m),
            "destination": self.destination,
            "nav_status": str(self.nav_status),
            # Route tracking
            "current_lane": self.current_lane,
            "waypoint_idx": str(self.waypoint_idx),
            "target_lat": str(self.target_lat),
            "target_lon": str(self.target_lon),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ship":
        """Create Ship from Redis hash data"""
        return cls(
            mmsi=data.get("mmsi", ""),
            name=data.get("name", ""),
            vessel_type=data.get("vessel_type", "cargo"),
            latitude=float(data.get("latitude", 15.0)),
            longitude=float(data.get("longitude", 80.0)),
            speed=float(data.get("speed", 10.0)),
            course=float(data.get("course", 0.0)),
            heading=float(data.get("heading", 0.0)),
            ais_enabled=data.get("ais_enabled", "True") == "True",
            radar_cross_section=float(data.get("radar_cross_section", 1.0)),
            length_m=float(data.get("length_m", 100.0)),
            width_m=float(data.get("width_m", 20.0)),
            draught_m=float(data.get("draught_m", 8.0)),
            destination=data.get("destination", ""),
            nav_status=int(data.get("nav_status", 0)),
            # Route tracking
            current_lane=data.get("current_lane", ""),
            waypoint_idx=int(data.get("waypoint_idx", 0)),
            target_lat=float(data.get("target_lat", 0.0)),
            target_lon=float(data.get("target_lon", 0.0)),
        )


# Realistic vessel type distribution
VESSEL_TYPES = [
    # (type, fraction, min_len, max_len, min_spd, max_spd, dark_prob)
    ("cargo", 0.30, 100, 200, 10, 16, 0.02),
    ("tanker", 0.25, 150, 350, 8, 14, 0.03),
    ("container", 0.20, 200, 400, 14, 24, 0.01),
    ("fishing", 0.12, 20, 50, 2, 8, 0.15),  # Fishing boats often go dark
    ("passenger", 0.05, 150, 300, 15, 22, 0.0),
    ("naval", 0.03, 50, 200, 15, 35, 0.05),  # Naval sometimes goes dark
    ("tug", 0.03, 20, 40, 5, 12, 0.01),
    ("unknown", 0.02, 30, 100, 5, 15, 1.0),  # Always dark - suspicious
]

# Common destinations (use MAJOR_PORTS keys)
DESTINATIONS = list(MAJOR_PORTS.keys())


class FleetManager:
    """
    Manages the ground truth ship fleet in Redis.

    All sensors read from this shared state to simulate
    real-world multi-sensor maritime surveillance.
    """

    FLEET_KEY = "maritime:fleet"  # Set of all MMSIs
    SHIP_PREFIX = "maritime:ship:"  # Hash per ship
    METADATA_KEY = "maritime:fleet:metadata"

    def __init__(self, redis_client):
        self.redis = redis_client

    async def initialize_fleet(self, num_ships: int = 500, dark_ship_pct: float = 5.0):
        """
        Create initial fleet of ships.

        Args:
            num_ships: Total ships in simulation
            dark_ship_pct: Percentage that start with AIS disabled
        """
        # Clear existing fleet
        existing = await self.redis.smembers(self.FLEET_KEY)
        if existing:
            pipeline = self.redis.pipeline()
            for mmsi in existing:
                pipeline.delete(f"{self.SHIP_PREFIX}{mmsi}")
            pipeline.delete(self.FLEET_KEY)
            await pipeline.execute()

        ships = []
        ship_id = 0

        for vtype, fraction, min_len, max_len, min_spd, max_spd, base_dark_prob in VESSEL_TYPES:
            count = int(num_ships * fraction)
            for i in range(count):
                # Generate realistic ship properties
                length = random.uniform(min_len, max_len)
                width = length * random.uniform(0.12, 0.18)  # Realistic L/W ratio

                # Dark probability combines base rate + user-specified percentage
                is_dark = random.random() < (base_dark_prob + dark_ship_pct / 100)

                # Spawn on a shipping lane (ocean-only, realistic routes)
                lat, lon, course, lane_name = spawn_point_on_lane()

                # Validate it's in ocean, retry if needed
                max_retries = 10
                for _ in range(max_retries):
                    if is_in_ocean(lat, lon):
                        break
                    lat, lon, course, lane_name = spawn_point_on_lane()

                # Pick destination based on lane
                destination = random.choice(DESTINATIONS)

                ship = Ship(
                    mmsi=f"{ship_id:09d}",
                    name=f"{vtype.upper()}_{ship_id:04d}",
                    vessel_type=vtype,
                    latitude=lat,
                    longitude=lon,
                    speed=random.uniform(min_spd, max_spd),
                    course=course,
                    heading=(course + random.uniform(-5, 5)) % 360,
                    ais_enabled=not is_dark,
                    radar_cross_section=random.uniform(0.5, 2.0) * (length / 100),
                    length_m=length,
                    width_m=width,
                    draught_m=random.uniform(4, min(15, length * 0.05)),
                    destination=destination,
                    nav_status=0,
                    # Route tracking
                    current_lane=lane_name,
                    waypoint_idx=0,
                    target_lat=0.0,
                    target_lon=0.0,
                )
                ships.append(ship)
                ship_id += 1

        # Store in Redis
        pipeline = self.redis.pipeline()
        for ship in ships:
            pipeline.sadd(self.FLEET_KEY, ship.mmsi)
            pipeline.hset(f"{self.SHIP_PREFIX}{ship.mmsi}", mapping=ship.to_dict())

        # Store metadata
        dark_count = len([s for s in ships if not s.ais_enabled])
        metadata = {
            "total_ships": str(len(ships)),
            "dark_ships": str(dark_count),
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "lat_min": str(LAT_MIN),
            "lat_max": str(LAT_MAX),
            "lon_min": str(LON_MIN),
            "lon_max": str(LON_MAX),
        }
        pipeline.hset(self.METADATA_KEY, mapping=metadata)

        await pipeline.execute()
        return ships

    async def get_all_ships(self) -> List[Ship]:
        """Get current state of all ships"""
        mmsis = await self.redis.smembers(self.FLEET_KEY)
        if not mmsis:
            return []

        pipeline = self.redis.pipeline()
        for mmsi in mmsis:
            pipeline.hgetall(f"{self.SHIP_PREFIX}{mmsi}")

        results = await pipeline.execute()
        return [Ship.from_dict(data) for data in results if data]

    async def get_ship(self, mmsi: str) -> Optional[Ship]:
        """Get single ship by MMSI"""
        data = await self.redis.hgetall(f"{self.SHIP_PREFIX}{mmsi}")
        return Ship.from_dict(data) if data else None

    async def update_ship(self, ship: Ship):
        """Update ship state in Redis"""
        await self.redis.hset(f"{self.SHIP_PREFIX}{ship.mmsi}", mapping=ship.to_dict())

    async def update_ships_batch(self, ships: List[Ship]):
        """Update multiple ships efficiently"""
        pipeline = self.redis.pipeline()
        for ship in ships:
            pipeline.hset(f"{self.SHIP_PREFIX}{ship.mmsi}", mapping=ship.to_dict())
        await pipeline.execute()

    async def get_metadata(self) -> dict:
        """Get fleet metadata"""
        return await self.redis.hgetall(self.METADATA_KEY)

    async def update_metadata(self):
        """Update fleet statistics"""
        ships = await self.get_all_ships()
        dark_count = len([s for s in ships if not s.ais_enabled])
        await self.redis.hset(self.METADATA_KEY, mapping={
            "total_ships": str(len(ships)),
            "dark_ships": str(dark_count),
            "last_update": datetime.now(timezone.utc).isoformat(),
        })

    async def get_ships_in_area(self, lat_min: float, lat_max: float,
                                 lon_min: float, lon_max: float) -> List[Ship]:
        """Get ships within a geographic area"""
        ships = await self.get_all_ships()
        return [
            s for s in ships
            if lat_min <= s.latitude <= lat_max
            and lon_min <= s.longitude <= lon_max
        ]

    async def get_ships_in_range(self, center_lat: float, center_lon: float,
                                  range_nm: float) -> List[Ship]:
        """Get ships within range of a point (for radar stations)"""
        ships = await self.get_all_ships()
        result = []
        for ship in ships:
            distance = haversine_distance(center_lat, center_lon,
                                          ship.latitude, ship.longitude)
            if distance <= range_nm:
                result.append((ship, distance))
        return result


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in nautical miles between two points"""
    R = 3440.065  # Earth radius in nautical miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))
