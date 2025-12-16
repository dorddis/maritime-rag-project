# Maritime RAG Project - Context File

**Last Updated:** 2024-12-16

## Project Overview

A **Maritime Domain Awareness (MDA)** demo project showcasing multi-sensor data fusion for ship tracking. Built as an interview demonstration piece showing realistic maritime surveillance simulation.

### Core Concept
- **Ground Truth**: World Simulator creates ships in Redis, moving along realistic Indian Ocean shipping lanes
- **Multi-Sensor Ingestion**: 4 sensor types generate synthetic data by reading ground truth
- **Data Fusion**: Correlates detections across all sensors to create unified tracks and detect "dark ships"

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 NEXT.JS DASHBOARD (:3000)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              3D GLOBE (react-globe.gl)                    │  │
│  │  - Ships as colored dots (cyan=AIS, red=dark)            │  │
│  │  - 7 Radar coverage rings (pulsing red)                  │  │
│  │  - 5 Drone patrol zones (green polygons)                 │  │
│  │  - 3 Satellite paths (yellow dashed arcs)                │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ WORLD   │ │  AIS    │ │ RADAR   │ │SATELLITE│ │ DRONE   │  │
│  │ Ground  │ │ NMEA    │ │ Binary  │ │ GeoJSON │ │ CV JSON │  │
│  │ Truth   │ │ 0183    │ │Protocol │ │         │ │         │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│                        ┌─────────┐                             │
│                        │ FUSION  │ Dark Ships Panel            │
│                        │ Unified │ Real-time alerts            │
│                        │ Tracks  │                             │
│                        └─────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                    REST API + WebSocket
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FASTAPI BACKEND (:8001)                        │
│  - Ingester process management                                  │
│  - Redis stream stats                                           │
│  - Fleet ship data API                                          │
│  - Fusion API (tracks, dark ships, status)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       REDIS                                      │
│  - maritime:fleet (Set of MMSIs)                                │
│  - maritime:ship:{mmsi} (Hash per ship)                         │
│  - ais:positions, radar:contacts, satellite/drone:detections   │
│  - fusion:tracks, fusion:dark_ships, fusion:active_tracks      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Files

### Dashboard (Next.js)
| File | Purpose |
|------|---------|
| `dashboard/src/components/globe/maritime-globe.tsx` | 3D globe with ships, radar rings, drone zones, satellite paths |
| `dashboard/src/components/ingester/ingester-card.tsx` | Sensor control cards with tech details, config, logs |
| `dashboard/src/components/ingester/config-panel.tsx` | Configuration sliders for each sensor |
| `dashboard/src/lib/types.ts` | TypeScript types, tech details metadata, config ranges |
| `dashboard/src/lib/api.ts` | REST API client for backend |
| `dashboard/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:8001` |

### Backend (Python)
| File | Purpose |
|------|---------|
| `ingestion/shared/fleet_manager.py` | Ground truth ship state, shipping lanes, ocean validation |
| `ingestion/shared/world_simulator.py` | Moves ships in real-time, AIS toggle events |
| `ingestion/generators/nmea_generator.py` | AIS NMEA 0183 message generation |
| `ingestion/generators/radar_generator.py` | Binary radar protocol generation |
| `ingestion/generators/satellite_generator.py` | GeoJSON satellite detection files |
| `ingestion/generators/drone_generator.py` | YOLO-style CV JSON output |

### Fusion Layer (Python)
| File | Purpose |
|------|---------|
| `ingestion/fusion/schema.py` | UnifiedTrack, SensorContribution Pydantic models |
| `ingestion/fusion/config.py` | Sensor characteristics, correlation gates, dark ship thresholds |
| `ingestion/fusion/correlation.py` | Gated GNN algorithm with Hungarian assignment |
| `ingestion/fusion/track_manager.py` | Track lifecycle, dark ship detection logic |
| `ingestion/fusion/fusion_ingester.py` | Main async process consuming all 4 streams |

---

## Sensor Technical Details

### World Simulator (Ground Truth)
- **Redis Hashes** with atomic updates
- **global-land-mask** (1km GLOBE dataset) for ocean validation
- **7 shipping lanes**: Malacca-Gulf, India West/East Coast, Bay of Bengal, Colombo Hub, Persian Gulf, SE Asia-India
- Ships follow waypoints with smooth course adjustment (max 5 deg/s)
- Random AIS on/off toggle (simulates dark ships)
- **Simulation bounds**: Lat -5 to 25, Lon 50 to 105 (Indian Ocean)
- **Sensor coverage**: Lat 5 to 25, Lon 65 to 100 (ships stay on lanes within this area)

### AIS (NMEA 0183)
- **6-bit ASCII armoring** (chars 0-63 mapped to printable)
- **Message Types**: 1/2/3 (position), 5 (static/voyage), 18 (Class B)
- XOR checksum between `!` and `*`
- **Limitation**: Only sees ships with AIS ON

### Radar (Binary Protocol)
- **struct.pack** big-endian: Header 8B + Body variable
- **7 coastal stations**: Mumbai, Chennai, Kochi, Vizag, Karwar, Kolkata, Tuticorin
- Range: 40-80nm per station
- **Advantage**: Detects ALL ships including dark vessels

### Satellite (GeoJSON)
- **GeoJSON FeatureCollection** with metadata
- **SAR** (Sentinel-1): 92% detection, ignores clouds
- **Optical** (Maxar/Planet): 88% * (1 - cloud%) detection
- Wide-area dark ship detection

### Drone (CV JSON)
- **YOLOv8** maritime model (50-200ms inference)
- Bounding boxes + geo-projection (pixel to lat/lon)
- Persistent tracking IDs across frames (T001-T050)
- **3 drones** (300-800m altitude) patrolling **5 zones** across Indian Ocean

### Data Fusion
- **Gated Global Nearest Neighbor (GNN)** - Hungarian algorithm for optimal detection-to-track assignment
- **Inverse variance weighting** - Combines positions weighted by sensor accuracy
- **3-sigma adaptive gates** - Gate size = 3 * sqrt(track_uncertainty^2 + sensor_uncertainty^2)
- **Track lifecycle**: TENTATIVE (3 updates) -> CONFIRMED -> COASTING (5 min) -> DROPPED (10 min)
- **Dark ship detection**:
  - AIS gap: Ship had AIS, now missing for 15+ min but still seen by radar/satellite/drone
  - Multi-sensor correlation: 2+ non-AIS sensors agree, or drone visual confirmation

| Input Stream | Output |
|--------------|--------|
| ais:positions | fusion:tracks |
| radar:contacts | fusion:track:{id} hashes |
| satellite:detections | fusion:active_tracks set |
| drone:detections | fusion:dark_ships alerts |

---

## Configuration Options (UI Sliders)

| Sensor | Config | Range | Default |
|--------|--------|-------|---------|
| **World** | Fleet Size | 100-1000 | 500 |
| | Dark Ships % | 0-30% | 5% |
| | Speed Multiplier | 1-120x | 60x |
| **AIS** | Ships to Track | 1-500 | 100 |
| | Update Rate | 0.1-10 Hz | 1.0 Hz |
| **Radar** | Active Tracks | 1-200 | 50 |
| | Update Rate | 0.1-10 Hz | 1.0 Hz |
| | Detection Range | 50-150% | 100% |
| **Satellite** | Pass Rate | 0.01-1 Hz | 0.1 Hz |
| | Cloud Cover | 0-80% | 20% |
| | Vessels/Pass | 20-100 | 50 |
| **Drone** | Frame Rate | 0.1-5 Hz | 0.5 Hz |
| | Detections/Frame | 1-10 | 5 |
| **Fusion** | Processing Rate | 0.5-10 Hz | 2.0 Hz |

---

## Globe Visualization Layers

### Ships (Points)
- Cyan dots: AIS-enabled ships
- Red dots: Dark ships (AIS off)
- Size varies by ship type (container > cargo > fishing)

### Radar Coverage (Rings)
7 stations with pulsing red rings:
- Mumbai (50nm), Chennai (50nm), Kochi (40nm)
- Vizag (80nm), Karwar (60nm), Kolkata (45nm), Tuticorin (40nm)

### Drone Patrol Zones (Polygons)
5 green semi-transparent zones:
- Mumbai-Goa Corridor
- Kerala Coast
- Sri Lanka - Malacca Route
- Chennai-Vizag Coast
- Andaman Strait

### Satellite Paths (Arcs)
3 animated yellow dashed arcs:
- Sentinel-1A, Sentinel-2A, Planet-Dove

---

## Running the Project

```bash
# Terminal 1: Redis
docker run -p 6379:6379 redis

# Terminal 2: FastAPI Backend
cd maritime-rag-project
python -m uvicorn admin.server:app --port 8001

# Terminal 3: Next.js Dashboard
cd maritime-rag-project/dashboard
npm run dev
```

Dashboard: http://localhost:3000
API: http://localhost:8001

---

## Demo Flow

1. **Start World Simulator** - Creates 500 ships on realistic shipping lanes
2. **Start all sensors** - AIS, Radar, Satellite, Drone begin generating detections
3. **Watch globe** - Ships move along trade routes, some go dark
4. **Start Fusion** - Correlates all sensor data, unified tracks appear
5. **Show Dark Ships Panel** - Watch alerts as dark ships are detected
6. **Show Tech Details** - Expand each card to show realistic implementation
7. **Explain fusion value** - AIS misses dark ships, radar/satellite/drone + fusion fills gaps

---

## Recent Changes (This Session)

1. Added **technical bullet points** to each ingester card (4 points each, bold key terms)
2. Added **sensor coverage visualizations** on globe (radar rings, drone zones, satellite paths)
3. Fixed **drone zone positions** to align with shipping lanes
4. Updated to **7 radar stations** (added Kolkata, Tuticorin)
5. Added **comprehensive config sliders** for all sensors
6. Created reusable **ConfigSlider** component
7. Added **markdown bold rendering** for tech details (`**text**` -> bold white)
8. **Implemented Data Fusion Layer**:
   - Gated GNN correlation algorithm with Hungarian assignment
   - Inverse variance position fusion
   - Track lifecycle management (tentative -> confirmed -> coasting -> dropped)
   - Dark ship detection (AIS gaps + multi-sensor correlation)
   - API endpoints: /api/fusion/tracks, /api/fusion/dark-ships, /api/fusion/status
9. Added **Dark Ships Alert Panel** to dashboard

---

## Pending / Future Work

- [ ] Connect config sliders to actually change backend behavior on start
- [ ] Add ship trail visualization (movement history)
- [ ] Add click-to-zoom on radar stations
- [ ] Add fused tracks layer to globe (different color from raw sensor data)
- [ ] Click dark ship alert to pan globe to that location
