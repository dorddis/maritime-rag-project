# Unified Maritime Simulation Plan

## Goal
Create a realistic multi-sensor maritime surveillance simulation where **all 4 sensors observe the same ground truth ships**.

## Architecture

```
                    GROUND TRUTH (Redis)
                    ==================
                    ships:{mmsi} -> Hash
                    - latitude, longitude
                    - speed, course
                    - vessel_type, name
                    - ais_enabled (can go dark)
                    - length_m, radar_cross_section
                           |
        +------------------+------------------+------------------+
        |                  |                  |                  |
        v                  v                  v                  v
   AIS SENSOR         RADAR SENSOR      SATELLITE SENSOR    DRONE SENSOR
   ==========         ============      ================    ============
   - Only sees        - Range limited   - Periodic passes   - Small patrol
     ships with         (50-80nm)       - Sees ALL ships      zones
     AIS ON           - No identity     - Lower accuracy    - High detail
   - High accuracy    - Position error  - Detects dark      - Visual ID
   - High frequency   - Weather factor    ships             - Continuous
        |                  |                  |                  |
        v                  v                  v                  v
   ais:positions      radar:contacts    satellite:detections  drone:detections
   (Redis Stream)     (Redis Stream)    (Redis Stream)        (Redis Stream)
```

## Components

### 1. Shared Fleet Manager (`ingestion/shared/fleet_manager.py`)

Manages ground truth ship state in Redis:

```python
class FleetManager:
    SHIPS_KEY = "maritime:ships"  # Hash of all ships
    SHIP_PREFIX = "ship:"         # Individual ship hashes

    def __init__(self, redis_client, num_ships=500):
        self.redis = redis_client
        self.num_ships = num_ships

    async def initialize_fleet(self):
        """Create initial ship positions"""
        # Vessel type distribution (realistic)
        # - 30% cargo, 25% tanker, 20% container
        # - 15% fishing, 5% passenger, 3% naval, 2% unknown (dark)

    async def get_all_ships(self) -> List[Ship]:
        """Get current state of all ships"""

    async def get_ship(self, mmsi: str) -> Ship:
        """Get single ship state"""

    async def update_ship(self, ship: Ship):
        """Update ship position in Redis"""
```

### 2. World Simulator (`ingestion/world_simulator.py`)

Moves ships continuously (runs as separate process):

```python
class WorldSimulator:
    def __init__(self, fleet_manager: FleetManager):
        self.fleet = fleet_manager
        self.update_rate_hz = 1.0  # Update positions every second

    async def run(self):
        """Main loop - moves all ships"""
        while True:
            ships = await self.fleet.get_all_ships()
            for ship in ships:
                ship.move(1.0 / self.update_rate_hz)

                # Random events
                if random.random() < 0.001:
                    ship.ais_enabled = not ship.ais_enabled  # Go dark

                await self.fleet.update_ship(ship)

            await asyncio.sleep(1.0 / self.update_rate_hz)
```

### 3. Sensor Ingesters (Updated)

Each ingester reads from shared fleet and applies its sensor model:

#### AIS Ingester
```python
async def run_once(self):
    ships = await self.fleet.get_all_ships()
    for ship in ships:
        if not ship.ais_enabled:
            continue  # Dark ship - invisible to AIS
        if random.random() > 0.9:
            continue  # 10% packet loss

        # Publish accurate position (AIS is precise)
        await self.publish_position(ship, error_m=10)
```

#### Radar Ingester
```python
RADAR_STATIONS = [
    {"id": "RAD-MUM", "lat": 18.94, "lon": 72.84, "range_nm": 50},
    {"id": "RAD-CHN", "lat": 13.08, "lon": 80.27, "range_nm": 50},
    # ... more stations
]

async def run_once(self):
    ships = await self.fleet.get_all_ships()
    for station in RADAR_STATIONS:
        for ship in ships:
            distance = haversine(station, ship)
            if distance > station["range_nm"]:
                continue  # Out of range

            # Detection probability based on distance and RCS
            detection_prob = (1 - distance/range) * ship.radar_cross_section
            if random.random() > detection_prob:
                continue

            # Publish with position error (radar less precise)
            # NO IDENTITY - just track number
            await self.publish_contact(
                track_id=f"{station['id']}-T{hash(ship.mmsi) % 10000}",
                position=add_error(ship.position, error_m=500),
                speed=ship.speed + random.uniform(-1, 1),
                rcs=ship.radar_cross_section
            )
```

#### Satellite Ingester
```python
SATELLITES = [
    {"id": "SAT-S2A", "type": "optical", "revisit_hours": 5},
    {"id": "SAT-S1A", "type": "SAR", "revisit_hours": 6},
]

async def run_once(self):
    # Only generate during satellite pass (every ~60 seconds in sim)
    if random.random() > 0.02:
        return

    sat = random.choice(SATELLITES)
    swath = generate_swath()  # Random area covered by pass

    ships = await self.fleet.get_all_ships()
    detections = []
    for ship in ships:
        if not in_swath(ship, swath):
            continue

        # SAR sees through clouds, optical affected by weather
        detection_prob = 0.95 if sat["type"] == "SAR" else 0.85 * weather
        if random.random() > detection_prob:
            continue

        # Satellite DOES see dark ships!
        detections.append({
            "position": add_error(ship.position, error_m=2000),
            "estimated_length": ship.length + random.uniform(-20, 20),
            "is_dark_ship": not ship.ais_enabled,  # Key insight!
        })

    await self.publish_pass(sat, detections)
```

#### Drone Ingester
```python
PATROL_ZONES = [
    {"id": "DRN-001", "name": "Mumbai Approach", "lat": 18.8, "lon": 72.5, "radius_nm": 20},
    {"id": "DRN-002", "name": "Lakshadweep", "lat": 10.5, "lon": 72.6, "radius_nm": 30},
]

async def run_once(self):
    ships = await self.fleet.get_all_ships()
    for zone in PATROL_ZONES:
        if random.random() > 0.3:
            continue  # Drone not active in this zone

        for ship in ships:
            if distance(zone, ship) > zone["radius_nm"]:
                continue

            # Drone gets detailed visual - can ID even dark ships
            await self.publish_detection(
                drone_id=zone["id"],
                mmsi=ship.mmsi if ship.ais_enabled else "UNKNOWN",
                visual_id=ship.name,  # Can read hull markings
                position=ship.position,  # Very accurate
                is_dark_ship=not ship.ais_enabled,
                image_id=generate_image_id()
            )
```

## Data Flow for a Dark Ship

Example: Fishing vessel "UNKNOWN_0042" turns off AIS to fish illegally

```
Time    AIS           Radar              Satellite         Drone
----    ---           -----              ---------         -----
T+0     Position      Contact T-0042     -                 -
T+1     Position      Contact T-0042     -                 -
T+2     [GOES DARK]   Contact T-0042     -                 -
T+3     -             Contact T-0042     -                 -
T+4     -             Contact T-0042     -                 -
T+5     -             [Out of range]     -                 -
T+6     -             -                  Pass: 1 dark ship -
T+7     -             -                  -                 Visual contact!
```

This is exactly how real maritime surveillance works!

## Config Variables to Expose

| Ingester | Config | Range | Description |
|----------|--------|-------|-------------|
| World | num_ships | 100-2000 | Total ships in simulation |
| World | dark_ship_pct | 0-20% | Percentage that start with AIS off |
| World | update_rate | 0.1-10 Hz | Ship movement update rate |
| AIS | packet_loss | 0-50% | Transmission loss rate |
| Radar | stations | list | Coastal radar station configs |
| Radar | weather_factor | 0.5-1.0 | Sea state affecting detection |
| Satellite | pass_interval | 30-300 sec | Time between passes |
| Satellite | cloud_cover | 0-100% | Affects optical detection |
| Drone | zones | list | Patrol zone configs |
| Drone | active_probability | 0-100% | Chance drone is patrolling |

## Implementation Order

1. **Fleet Manager** - Shared ship state in Redis
2. **World Simulator** - Moves ships (separate process)
3. **Update Ingesters** - Read from shared fleet
4. **Dashboard Integration** - Controls for World Simulator
5. **Testing** - Verify cross-sensor correlation

## Success Criteria

- [x] Same ship visible in multiple sensor streams
- [x] Dark ships: Missing from AIS, visible in Radar/Satellite/Drone
- [x] Position correlation: Same ship detected within error bounds across sensors
- [x] Realistic data rates: AIS high, Radar medium, Satellite batch, Drone low
- [ ] Dashboard shows unified ship count and dark ship count

## Implementation Status (COMPLETED)

All components have been implemented:

1. **FleetManager** (`ingestion/shared/fleet_manager.py`) - Ship dataclass and Redis management
2. **WorldSimulator** (`ingestion/shared/world_simulator.py`) - Physics engine moving ships
3. **AIS Ingester** - Updated with `--source unified` option, skips dark ships
4. **Radar Ingester** - 7 coastal stations, range-limited, no identity, CAN see dark ships
5. **Satellite Ingester** - 4 satellites, periodic passes, CAN see dark ships
6. **Drone Ingester** - 5 patrol zones, highest accuracy, CAN identify dark ships

## Testing Instructions

### Step 1: Start Redis
```bash
redis-server
```

### Step 2: Initialize Fleet and Start World Simulator
```bash
cd interview-prep/maritime-rag-project
python -m ingestion.shared.world_simulator --ships 500 --dark-pct 5 --rate 1.0
```

This creates 500 ships with ~5% dark and continuously moves them.

### Step 3: Start Ingesters (in separate terminals)
```bash
# Terminal 2: AIS Ingester
python -m ingestion.ingesters.ais_nmea_ingester --source unified --rate 1.0

# Terminal 3: Radar Ingester
python -m ingestion.ingesters.radar_binary_ingester --source unified --rate 1.0

# Terminal 4: Satellite Ingester
python -m ingestion.ingesters.satellite_file_ingester --source unified --rate 1.0

# Terminal 5: Drone Ingester
python -m ingestion.ingesters.drone_cv_ingester --source unified --rate 0.5
```

### Step 4: Verify in Redis
```bash
redis-cli

# Check fleet
SMEMBERS maritime:fleet
HGETALL maritime:ship:000000000

# Check streams
XLEN ais:positions
XLEN radar:contacts
XLEN satellite:detections
XLEN drone:detections

# Check ingester status
HGETALL ingester:ais:status
HGETALL ingester:radar:status
```

### Expected Behavior

| Sensor | What it sees | Dark ships |
|--------|-------------|------------|
| AIS | Only ships with `ais_enabled=True` | INVISIBLE |
| Radar | Ships within range of 7 coastal stations | VISIBLE (no identity) |
| Satellite | Ships in swath during periodic passes | VISIBLE (flagged) |
| Drone | Ships in 5 patrol zones | VISIBLE (can identify) |
