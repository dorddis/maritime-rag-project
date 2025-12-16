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
        (1.2, 103.6),    # Singapore approach (offshore)
        (4.0, 100.0),    # Strait of Malacca exit
        (6.0, 95.0),     # Andaman Sea
        (6.5, 79.0),     # South of Sri Lanka (offshore)
        (10.0, 72.0),    # Arabian Sea
        (12.5, 65.0),    # Approaching Gulf of Aden
        (12.0, 55.0),    # Gulf of Aden
    ],

    # India West Coast Route (moved offshore by ~0.5 degrees)
    "india_west_coast": [
        (8.5, 75.5),     # Cochin approach (offshore)
        (12.9, 73.5),    # Mangalore approach (offshore)
        (15.4, 72.5),    # Goa approach (offshore)
        (18.9, 71.5),    # Mumbai approach (offshore)
        (22.0, 68.5),    # Kandla approach (offshore)
    ],

    # India East Coast Route (moved offshore)
    "india_east_coast": [
        (8.0, 78.5),     # Tuticorin approach (offshore)
        (13.1, 81.5),    # Chennai approach (offshore)
        (17.7, 85.0),    # Visakhapatnam approach (offshore)
        (20.0, 88.0),    # Bay of Bengal
    ],

    # Bay of Bengal Crossing
    "bay_of_bengal": [
        (1.2, 103.6),    # Singapore approach
        (6.0, 95.0),     # Andaman Sea
        (10.0, 88.0),    # Central Bay of Bengal
        (13.1, 81.5),    # Chennai approach (offshore)
    ],

    # Sri Lanka Hub Routes
    "colombo_hub": [
        (6.5, 79.0),     # Colombo approach (offshore)
        (7.5, 77.5),     # South of India
        (5.5, 73.0),     # Maldives area
        (10.0, 72.0),    # Arabian Sea
    ],

    # Persian Gulf Route
    "persian_gulf": [
        (12.5, 65.0),    # Gulf of Aden approach
        (15.0, 60.0),    # Arabian Sea
        (22.0, 60.0),    # Approaching Hormuz
        (25.5, 57.0),    # Strait of Hormuz approach
    ],

    # Southeast Asia to India
    "se_asia_india": [
        (1.2, 103.6),    # Singapore approach
        (7.0, 97.0),     # Phuket area (offshore)
        (10.0, 92.0),    # Andaman Islands
        (13.1, 81.5),    # Chennai approach (offshore)
        (18.9, 71.5),    # Mumbai approach (offshore)
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

    Validates that the point is in ocean before returning.
    """
    lane_name = random.choice(list(SHIPPING_LANES.keys()))
    lane = SHIPPING_LANES[lane_name]

    # Pick a random segment of the lane
    idx = random.randint(0, len(lane) - 2)
    start = lane[idx]
    end = lane[idx + 1]

    # Random position along the segment
    t = random.random()
    base_lat = start[0] + t * (end[0] - start[0])
    base_lon = start[1] + t * (end[1] - start[1])

    # Try adding offset, but validate it stays in ocean
    # Start with small offset and increase if needed for variety
    for offset_scale in [0.1, 0.15, 0.2]:
        lat = base_lat + random.uniform(-offset_scale, offset_scale)
        lon = base_lon + random.uniform(-offset_scale, offset_scale)

        if HAS_LAND_MASK and is_in_ocean(lat, lon):
            break
    else:
        # If offset keeps hitting land, use the base lane point
        lat, lon = base_lat, base_lon

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

# =============================================================================
# REALISTIC SHIP NAMES
# =============================================================================

# Prefixes by vessel type (shipping companies, common naming patterns)
SHIP_NAME_PREFIXES = {
    "cargo": ["ATLANTIC", "PACIFIC", "OCEAN", "GLOBAL", "STAR", "ORIENT", "NORDIC", "BALTIC", "FORTUNE", "UNITY"],
    "tanker": ["EAGLE", "BRITISH", "NORDIC", "CROWN", "ENERGY", "CRUDE", "PETRO", "OCEAN", "GULF", "ROYAL"],
    "container": ["MSC", "MAERSK", "COSCO", "EVER", "CMA CGM", "ONE", "HAPAG", "YANG MING", "MOL", "NYK"],
    "fishing": ["SEA", "OCEAN", "DEEP", "BLUE", "STAR", "LUCKY", "GOLDEN", "SILVER", "PEARL", "CORAL"],
    "passenger": ["ROYAL", "CARNIVAL", "PRINCESS", "CELEBRITY", "COSTA", "QUEEN", "DIAMOND", "CRYSTAL", "GRAND", "STAR"],
    "naval": ["INS", "VIKRANT", "SHIVALIK", "TALWAR", "KOLKATA", "DELHI", "MYSORE", "CHENNAI", "KOCHI", "VIZAG"],
    "tug": ["OCEAN", "PORT", "HARBOUR", "MIGHTY", "STRONG", "POWER", "FORCE", "TITAN", "ATLAS", "NEPTUNE"],
    "unknown": ["SHADOW", "PHANTOM", "GHOST", "DARK", "NIGHT", "SILENT", "VOID", "UNKNOWN", "MYSTERY", "STEALTH"],
}

# Suffixes (geographic, descriptive)
SHIP_NAME_SUFFIXES = {
    "cargo": ["VOYAGER", "CARRIER", "EXPRESS", "TRADER", "PIONEER", "VENTURE", "FORTUNE", "SPIRIT", "PRIDE", "GLORY",
              "MUMBAI", "SINGAPORE", "DUBAI", "CHENNAI", "COLOMBO", "MALDIVES", "ARABIAN", "INDIAN", "BENGAL", "ANDAMAN"],
    "tanker": ["SPIRIT", "FORTUNE", "STAR", "GLORY", "PRIDE", "TEXAS", "ALASKA", "LIBERTY", "GRACE", "CROWN",
               "GULF", "ARABIAN", "PERSIAN", "INDIAN", "PACIFIC", "ATLANTIC", "HORIZON", "ENDEAVOUR", "RESOLVE", "VALIANT"],
    "container": ["GLORY", "FORTUNE", "STAR", "HARMONY", "TRIUMPH", "UNITY", "WISDOM", "TRUST", "FAITH", "HOPE",
                  "GULSUN", "ELBA", "EMMA", "OSCAR", "MADISON", "JAKARTA", "BANGKOK", "TOKYO", "SEOUL", "SHANGHAI"],
    "fishing": ["HUNTER", "SPIRIT", "DREAM", "QUEST", "VENTURE", "DAWN", "HORIZON", "WAVE", "TIDE", "BREEZE",
                "DRAGON", "PHOENIX", "TIGER", "FALCON", "EAGLE", "MARLIN", "TUNA", "PEARL", "CORAL", "REEF"],
    "passenger": ["PRINCESS", "QUEEN", "EMPRESS", "MONARCH", "SOVEREIGN", "MAJESTY", "SPLENDOUR", "SERENITY", "DREAM", "FANTASY",
                  "CARIBBEAN", "MEDITERRANEAN", "PACIFIC", "ATLANTIC", "INDIAN", "ARABIAN", "CORAL", "AZURE", "JADE", "RUBY"],
    "naval": ["BRAHMAPUTRA", "GODAVARI", "GANGA", "KAVERI", "NARMADA", "SAHYADRI", "VINDHYAGIRI", "NILGIRI", "HIMGIRI", "UDAYGIRI",
              "CHAKRA", "ARIHANT", "SINDHUGHOSH", "SHISHUMAR", "KALVARI", "KHANDERI", "KARANJ", "VELA", "VAGIR", "VAGSHEER"],
    "tug": ["FORCE", "POWER", "STRENGTH", "MIGHT", "GRIP", "PULL", "WORKER", "HELPER", "ASSIST", "GUARDIAN",
            "LION", "TIGER", "BEAR", "BULL", "BUFFALO", "ELEPHANT", "MAMMOTH", "GIANT", "COLOSSUS", "HERCULES"],
    "unknown": ["RUNNER", "DRIFTER", "WANDERER", "NOMAD", "ROGUE", "SPECTRE", "WRAITH", "SHADE", "MIST", "FOG",
                "ZERO", "NULL", "VOID", "BLANK", "CIPHER", "ENIGMA", "RIDDLE", "PUZZLE", "MAZE", "LABYRINTH"],
}

# Track used names to avoid duplicates
_used_ship_names: set = set()


def generate_ship_name(vessel_type: str, ship_id: int) -> str:
    """
    Generate a realistic ship name based on vessel type.

    Examples:
        - cargo: "ATLANTIC VOYAGER", "PACIFIC MUMBAI"
        - tanker: "EAGLE SPIRIT", "NORDIC GULF"
        - container: "MSC GULSUN", "MAERSK ELBA"
        - fishing: "SEA HUNTER", "LUCKY DRAGON"
    """
    global _used_ship_names

    prefixes = SHIP_NAME_PREFIXES.get(vessel_type, SHIP_NAME_PREFIXES["cargo"])
    suffixes = SHIP_NAME_SUFFIXES.get(vessel_type, SHIP_NAME_SUFFIXES["cargo"])

    # Try to generate unique name
    for _ in range(50):  # Max attempts
        prefix = random.choice(prefixes)
        suffix = random.choice(suffixes)
        name = f"{prefix} {suffix}"

        if name not in _used_ship_names:
            _used_ship_names.add(name)
            return name

    # Fallback: add number suffix for uniqueness
    name = f"{random.choice(prefixes)} {random.choice(suffixes)} {ship_id}"
    _used_ship_names.add(name)
    return name


def reset_ship_names():
    """Reset the used names tracker (call when reinitializing fleet)."""
    global _used_ship_names
    _used_ship_names = set()


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

        # Reset ship name tracker for fresh names
        reset_ship_names()

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
                max_retries = 20
                found_ocean = False
                for _ in range(max_retries):
                    if is_in_ocean(lat, lon):
                        found_ocean = True
                        break
                    lat, lon, course, lane_name = spawn_point_on_lane()

                # If still on land after retries, use a safe deep ocean fallback
                if not found_ocean:
                    # Deep ocean point in Bay of Bengal (guaranteed water)
                    lat = random.uniform(8.0, 12.0)
                    lon = random.uniform(85.0, 92.0)
                    course = random.uniform(0, 360)
                    lane_name = "bay_of_bengal"

                # Pick destination based on lane
                destination = random.choice(DESTINATIONS)

                ship = Ship(
                    mmsi=f"{ship_id:09d}",
                    name=generate_ship_name(vtype, ship_id),
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
