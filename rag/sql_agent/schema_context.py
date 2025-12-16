"""
Database Schema Context for SQL Agent

Provides detailed schema descriptions to help the LLM generate accurate SQL.
"""

SCHEMA_CONTEXT = """
# Maritime Ship Tracking Database Schema

## Main Tables

### unified_tracks
Fused vessel tracks from multiple sensors (AIS, Radar, Satellite, Drone).
Updated every 0.5 seconds from the fusion layer.

| Column | Type | Description |
|--------|------|-------------|
| track_id | VARCHAR(50) | Primary key, format: TRK-XXXXXXXX |
| latitude | DOUBLE | Current latitude (-90 to 90) |
| longitude | DOUBLE | Current longitude (-180 to 180) |
| speed_knots | DOUBLE | Speed in knots (1 knot = 1.852 km/h) |
| course | DOUBLE | Course over ground in degrees (0-360, 0=North) |
| heading | DOUBLE | Ship heading in degrees |
| mmsi | VARCHAR(20) | Maritime Mobile Service Identity (9 digits) |
| ship_name | VARCHAR(100) | Vessel name |
| vessel_type | VARCHAR(50) | Ship type: TANKER, CARGO, CONTAINER, PASSENGER, FISHING, etc. |
| vessel_length_m | DOUBLE | Length in meters |
| is_dark_ship | BOOLEAN | TRUE if AIS is disabled but ship detected by other sensors |
| dark_ship_confidence | DOUBLE | Confidence score 0-1 (higher = more suspicious) |
| ais_gap_seconds | DOUBLE | Seconds since last AIS signal (NULL if AIS active) |
| contributing_sensors | TEXT[] | Array of sensors: 'ais', 'radar', 'satellite', 'drone' |
| track_status | VARCHAR(20) | Status: 'tentative', 'confirmed', 'coasting', 'dropped' |
| track_quality | INTEGER | Quality score 0-100 (higher = better track) |
| updated_at | TIMESTAMPTZ | Last update timestamp |

### dark_ship_events
Point-in-time alerts when vessels disable AIS.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| track_id | VARCHAR(50) | Reference to unified_tracks |
| event_timestamp | TIMESTAMPTZ | When the dark ship was detected |
| latitude | DOUBLE | Position at detection |
| longitude | DOUBLE | Position at detection |
| confidence | DOUBLE | Detection confidence 0-1 |
| alert_reason | TEXT | Why flagged (e.g., "AIS gap: 45 minutes") |
| detected_by | TEXT[] | Sensors that detected it |
| ais_gap_seconds | DOUBLE | How long AIS was off |
| resolved | BOOLEAN | Whether the alert was resolved |

### ports
Known port locations for proximity queries.

| Column | Type | Description |
|--------|------|-------------|
| name | VARCHAR(100) | Port name (Mumbai, Chennai, Singapore, etc.) |
| country | VARCHAR(50) | Country |
| latitude | DOUBLE | Port latitude |
| longitude | DOUBLE | Port longitude |

Available ports: Mumbai, Chennai, Kochi, Visakhapatnam, Kandla, Colombo, Singapore, Dubai, Karachi, Chittagong

## Useful Views

### latest_unified_tracks
Most recent position for each vessel (by MMSI). Use for "current" queries.

### active_dark_ships
Currently flagged dark ships (is_dark_ship = TRUE and not dropped).

### recent_dark_events
Dark ship events from the last 24 hours.

## Helper Functions

### haversine_distance(lat1, lon1, lat2, lon2)
Returns distance in KILOMETERS between two lat/lon points.
Example: `haversine_distance(18.9388, 72.8354, 13.0827, 80.2707)` returns ~1033 km

### find_ships_near_point(center_lat, center_lon, radius_km, max_results)
Returns ships within radius of a point.
Example: `SELECT * FROM find_ships_near_point(18.9388, 72.8354, 50, 100)` - ships within 50km of Mumbai

### find_ships_near_port(port_name, radius_km, max_results)
Returns ships near a named port.
Example: `SELECT * FROM find_ships_near_port('Mumbai', 50, 100)`

## Common Query Patterns

### Filter by vessel type:
```sql
SELECT * FROM unified_tracks WHERE vessel_type = 'TANKER'
```

### Filter by speed:
```sql
SELECT * FROM unified_tracks WHERE speed_knots > 15
```

### Ships near Mumbai (within 50km):
```sql
SELECT * FROM find_ships_near_port('Mumbai', 50, 100)
```
OR using haversine:
```sql
SELECT *, haversine_distance(latitude, longitude, 18.9388, 72.8354) as dist_km
FROM unified_tracks
WHERE haversine_distance(latitude, longitude, 18.9388, 72.8354) < 50
ORDER BY dist_km
```

### Dark ships only:
```sql
SELECT * FROM unified_tracks WHERE is_dark_ship = TRUE
```
OR use the view:
```sql
SELECT * FROM active_dark_ships
```

### Ships in the last hour:
```sql
SELECT * FROM unified_tracks
WHERE updated_at >= NOW() - INTERVAL '1 hour'
```

### Ships heading north (course 315-45 degrees):
```sql
SELECT * FROM unified_tracks
WHERE course >= 315 OR course <= 45
```

### Count ships by type:
```sql
SELECT vessel_type, COUNT(*) as count
FROM unified_tracks
WHERE track_status = 'confirmed'
GROUP BY vessel_type
ORDER BY count DESC
```

### Dark ship events today:
```sql
SELECT * FROM dark_ship_events
WHERE event_timestamp >= CURRENT_DATE
ORDER BY event_timestamp DESC
```

## Important Notes

1. Always use `track_status != 'dropped'` or `track_status = 'confirmed'` for active tracks
2. Coordinates: latitude is -90 to 90, longitude is -180 to 180
3. Speed is in KNOTS (not km/h or mph)
4. Course/heading: 0=North, 90=East, 180=South, 270=West
5. Use haversine_distance() for accurate distance calculations
6. Use find_ships_near_port() for common port proximity queries
7. For "current" or "latest" queries, use the latest_unified_tracks view
"""

EXAMPLE_QUERIES = [
    {
        "question": "Show me all tankers",
        "sql": "SELECT * FROM unified_tracks WHERE vessel_type = 'TANKER' AND track_status = 'confirmed'"
    },
    {
        "question": "Ships near Mumbai faster than 15 knots",
        "sql": """SELECT * FROM find_ships_near_port('Mumbai', 50, 100)
WHERE speed_knots > 15"""
    },
    {
        "question": "Dark ships detected today",
        "sql": """SELECT * FROM dark_ship_events
WHERE event_timestamp >= CURRENT_DATE
ORDER BY event_timestamp DESC"""
    },
    {
        "question": "How many ships by type?",
        "sql": """SELECT vessel_type, COUNT(*) as count
FROM unified_tracks
WHERE track_status = 'confirmed'
GROUP BY vessel_type
ORDER BY count DESC"""
    },
    {
        "question": "Ships in the last hour",
        "sql": """SELECT * FROM unified_tracks
WHERE updated_at >= NOW() - INTERVAL '1 hour'
AND track_status = 'confirmed'"""
    },
    {
        "question": "Cargo ships heading east",
        "sql": """SELECT * FROM unified_tracks
WHERE vessel_type = 'CARGO'
AND course BETWEEN 45 AND 135
AND track_status = 'confirmed'"""
    },
]


def get_schema_context() -> str:
    """Get the full schema context for SQL generation."""
    return SCHEMA_CONTEXT


def get_example_queries() -> list:
    """Get example question-SQL pairs for few-shot prompting."""
    return EXAMPLE_QUERIES
