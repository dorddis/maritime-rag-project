# Maritime Domain Awareness System - Full Specification

**Purpose:** Blurgs.ai Interview Prep - Build a production-like system
**Target:** Real-time AIS processing + Multi-source ingestion + RAG chatbot

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES (3 Formats)                             │
├─────────────────────┬─────────────────────┬─────────────────────────────────┤
│   AIS Stream        │   Weather API       │   Satellite/Radar Sim           │
│   (WebSocket JSON)  │   (REST JSON)       │   (CSV/GeoJSON)                 │
│   aisstream.io      │   OpenWeatherMap    │   Generated/NOAA               │
└─────────────────────┴─────────────────────┴─────────────────────────────────┘
          │                     │                         │
          ▼                     ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INGESTION LAYER (Python)                                │
│                                                                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│   │ AIS Ingester│    │Weather Ingest│    │Satellite Ing│                     │
│   │ (WebSocket) │    │ (Polling)   │    │ (File Watch)│                     │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                     │
│          │                  │                  │                             │
│          └──────────────────┼──────────────────┘                             │
│                             ▼                                                │
│              ┌─────────────────────────────┐                                 │
│              │   UNIFIED SCHEMA NORMALIZER │                                 │
│              │   (Pydantic Models)         │                                 │
│              └─────────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MESSAGE QUEUE                                        │
│                      Redis Streams / Kafka                                   │
│                                                                              │
│   Streams:                                                                   │
│   • maritime:ais-positions     (normalized AIS data)                        │
│   • maritime:weather           (weather conditions)                         │
│   • maritime:satellite         (satellite detections)                       │
│   • maritime:alerts            (anomaly alerts)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                                    │
        ┌───────────┘                                    └───────────┐
        ▼                                                            ▼
┌──────────────────────────────┐                ┌──────────────────────────────┐
│     STREAM PROCESSOR         │                │      BATCH PROCESSOR         │
│                              │                │                              │
│  Real-time anomaly detection │                │  • Hourly aggregations       │
│  • Speed anomalies           │                │  • Daily model retraining    │
│  • AIS gaps (dark ships)     │                │  • Historical analytics      │
│  • Zone violations           │                │  • Checkpoint: every 1000 msg│
│  • Weather correlation       │                │                              │
│                              │                │  Cron: */5 * * * *           │
│  Publishes to: alerts stream │                │                              │
└──────────────────────────────┘                └──────────────────────────────┘
                    │                                    │
                    └──────────────────┬─────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            STORAGE LAYER                                     │
│                                                                              │
│   ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│   │   TimescaleDB       │  │   PostgreSQL        │  │   ChromaDB          │ │
│   │   (Time-series)     │  │   + PostGIS         │  │   (Vectors/RAG)     │ │
│   │                     │  │                     │  │                     │ │
│   │   • ais_positions   │  │   • ships           │  │   • ship_reports    │ │
│   │   • weather_obs     │  │   • ports           │  │   • anomaly_docs    │ │
│   │   • aggregations    │  │   • zones           │  │   • zone_docs       │ │
│   └─────────────────────┘  └─────────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
┌──────────────────────────────┐        ┌──────────────────────────────────────┐
│     NEXTJS DASHBOARD         │        │         RAG CHATBOT API              │
│                              │        │                                      │
│  • Leaflet live map          │        │  • FastAPI backend                   │
│  • Ship markers (WebSocket)  │        │  • Gemini 2.5 Flash                  │
│  • Alert notifications       │        │  • ChromaDB retrieval                │
│  • Analytics charts          │        │  • WebSocket for live context        │
│                              │        │                                      │
│  Tech: NextJS 14 + shadcn    │        │  Queries:                            │
│        Socket.io             │        │  • "Ships near Mumbai?"              │
│        Recharts              │        │  • "Any anomalies in last hour?"     │
│        Leaflet               │        │  • "Dark ships detected today?"      │
└──────────────────────────────┘        └──────────────────────────────────────┘
```

---

## Data Source Details

### 1. AIS Stream (WebSocket JSON) - PRIMARY
**Source:** [aisstream.io](https://aisstream.io/)
**Format:** WebSocket → JSON
**Rate:** ~1000s of messages/minute globally

```python
# Connection
wss://stream.aisstream.io/v0/stream

# Subscription message
{
    "APIKey": "<YOUR_API_KEY>",
    "BoundingBoxes": [[[5, 65], [25, 100]]],  # Indian Ocean region
    "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
}

# Sample position message
{
    "MessageType": "PositionReport",
    "Message": {
        "PositionReport": {
            "UserID": 123456789,  # MMSI
            "Latitude": 18.9388,
            "Longitude": 72.8354,
            "Sog": 12.5,  # Speed over ground (knots)
            "Cog": 245.0,  # Course over ground (degrees)
            "TrueHeading": 243,
            "Timestamp": "2025-12-15T14:30:00Z",
            "NavigationalStatus": 0  # 0=underway
        }
    },
    "MetaData": {
        "MMSI": 123456789,
        "ShipName": "MV OCEAN STAR",
        "time_utc": "2025-12-15T14:30:00Z"
    }
}
```

**Get API Key:** https://aisstream.io/ (FREE signup)

---

### 2. Weather API (REST JSON) - SECONDARY
**Source:** [OpenWeatherMap](https://openweathermap.org/api) or [Open-Meteo](https://open-meteo.com/)
**Format:** REST API → JSON
**Rate:** Poll every 15 minutes per region

```python
# Open-Meteo (FREE, no API key needed)
GET https://api.open-meteo.com/v1/forecast?latitude=18.94&longitude=72.84&current_weather=true

# Response
{
    "latitude": 18.94,
    "longitude": 72.84,
    "current_weather": {
        "temperature": 28.5,
        "windspeed": 15.2,
        "winddirection": 225,
        "weathercode": 1,
        "time": "2025-12-15T14:00"
    }
}
```

**Use case:** Correlate weather with ship behavior (ships slow down in storms)

---

### 3. Satellite/Radar Simulation (CSV/GeoJSON) - TERTIARY
**Source:** Generated data simulating satellite detections
**Format:** CSV files dropped into watched directory, or GeoJSON
**Rate:** Batch files every 30 minutes

```csv
# satellite_detections_20251215_1430.csv
detection_id,timestamp,latitude,longitude,confidence,vessel_length_m,source
SAT-001,2025-12-15T14:30:00Z,18.95,72.80,0.85,180,Sentinel-2
SAT-002,2025-12-15T14:30:00Z,19.10,72.95,0.72,95,Sentinel-2
```

```json
// satellite_detections.geojson
{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [72.80, 18.95]
            },
            "properties": {
                "detection_id": "SAT-001",
                "timestamp": "2025-12-15T14:30:00Z",
                "confidence": 0.85,
                "vessel_length_m": 180,
                "source": "Sentinel-2"
            }
        }
    ]
}
```

**Use case:** Cross-reference AIS positions with satellite detections (find dark ships)

---

## Unified Schema (Pydantic)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal
from enum import Enum

class DataSource(str, Enum):
    AIS = "ais"
    WEATHER = "weather"
    SATELLITE = "satellite"
    RADAR = "radar"

class MaritimePosition(BaseModel):
    """Unified position record from any source"""

    # Core fields
    id: str  # Unique record ID
    source: DataSource
    timestamp: datetime
    latitude: float
    longitude: float

    # Vessel identification (nullable for non-AIS sources)
    mmsi: Optional[int] = None
    ship_name: Optional[str] = None
    ship_type: Optional[str] = None

    # Movement data
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    course: Optional[float] = None

    # Source-specific metadata
    confidence: Optional[float] = None  # For satellite detections
    raw_payload: Optional[dict] = None  # Original message

    # Processing metadata
    ingested_at: datetime
    processed: bool = False

class WeatherObservation(BaseModel):
    """Weather data for a location"""

    id: str
    timestamp: datetime
    latitude: float
    longitude: float

    temperature_c: Optional[float] = None
    wind_speed_knots: Optional[float] = None
    wind_direction: Optional[float] = None
    wave_height_m: Optional[float] = None
    visibility_nm: Optional[float] = None
    weather_code: Optional[int] = None

    source: str = "open-meteo"

class AnomalyAlert(BaseModel):
    """Detected anomaly"""

    id: str
    timestamp: datetime
    anomaly_type: Literal["speed_spike", "ais_gap", "zone_violation", "dark_ship", "spoofing"]
    severity: Literal["low", "medium", "high", "critical"]

    # Location
    latitude: float
    longitude: float

    # Vessel (if known)
    mmsi: Optional[int] = None
    ship_name: Optional[str] = None

    # Details
    description: str
    evidence: dict  # Supporting data

    # Status
    acknowledged: bool = False
    resolved: bool = False
```

---

## Project Structure

```
maritime-system/
├── docker-compose.yml          # Redis, TimescaleDB, services
├── .env.example                 # Environment variables template
│
├── ingestion/                   # Data ingestion layer
│   ├── __init__.py
│   ├── ais_ingester.py         # WebSocket client for aisstream.io
│   ├── weather_ingester.py     # REST poller for weather API
│   ├── satellite_ingester.py   # File watcher for CSV/GeoJSON
│   ├── schema.py               # Pydantic models (unified schema)
│   └── normalizer.py           # Convert raw → unified schema
│
├── processing/                  # Stream & batch processing
│   ├── __init__.py
│   ├── stream_processor.py     # Real-time anomaly detection
│   ├── batch_processor.py      # Scheduled aggregations
│   ├── anomaly_rules.py        # Detection rules
│   └── checkpointer.py         # State management
│
├── storage/                     # Database interactions
│   ├── __init__.py
│   ├── timescale.py            # TimescaleDB client
│   ├── postgres.py             # PostgreSQL + PostGIS
│   └── vector_store.py         # ChromaDB for RAG
│
├── api/                         # FastAPI backend
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── routes/
│   │   ├── positions.py        # Ship position endpoints
│   │   ├── alerts.py           # Anomaly alerts endpoints
│   │   └── chat.py             # RAG chatbot endpoint
│   └── websocket.py            # Real-time updates
│
├── dashboard/                   # NextJS frontend
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx            # Main dashboard
│   │   ├── map/                # Leaflet map component
│   │   ├── alerts/             # Alert panel
│   │   └── chat/               # RAG chatbot UI
│   └── components/
│
├── rag/                         # RAG system
│   ├── __init__.py
│   ├── embeddings.py           # Document embedding
│   ├── retriever.py            # ChromaDB retrieval
│   └── chatbot.py              # Gemini integration
│
├── scripts/
│   ├── setup_db.sql            # Database schema
│   ├── generate_test_data.py   # Generate satellite CSV files
│   └── run_all.py              # Start all services
│
└── tests/
    ├── test_ingestion.py
    ├── test_anomaly_detection.py
    └── test_rag.py
```

---

## Implementation Order

### Phase 1: Core Ingestion (1 hour)
1. [ ] Set up Redis (docker)
2. [ ] Implement AIS WebSocket ingester
3. [ ] Implement unified schema normalizer
4. [ ] Test: See messages flowing to Redis

### Phase 2: Stream Processing (1 hour)
1. [ ] Implement speed anomaly detection
2. [ ] Implement AIS gap detection
3. [ ] Implement zone violation detection
4. [ ] Publish alerts to Redis stream

### Phase 3: Storage + Batch (30 min)
1. [ ] Set up TimescaleDB (docker)
2. [ ] Implement position storage
3. [ ] Implement hourly aggregation
4. [ ] Add checkpointing

### Phase 4: Dashboard (1 hour)
1. [ ] NextJS setup with Leaflet
2. [ ] WebSocket connection to backend
3. [ ] Live ship markers on map
4. [ ] Alert notification panel

### Phase 5: RAG Chatbot (30 min)
1. [ ] ChromaDB setup
2. [ ] Document ingestion from alerts/reports
3. [ ] Gemini integration
4. [ ] Chat API endpoint

---

## Key Talking Points for Interview

### Multi-Source Data Fusion
> "I built a system that ingests 3 different data formats:
> - **AIS via WebSocket** (JSON, streaming, ~1000 msg/min)
> - **Weather via REST API** (JSON, polling every 15 min)
> - **Satellite detections via file watch** (CSV/GeoJSON, batch)
>
> All sources are normalized to a unified Pydantic schema before being published to Redis streams. This allows the downstream processors to handle data uniformly regardless of source."

### Stream vs Batch Trade-off
> "We use dual processing:
> - **Stream** for real-time anomaly detection (latency < 1 sec)
> - **Batch** for model training and historical aggregations
>
> Checkpointing every 1000 messages ensures we can recover from failures without data loss."

### Anomaly Detection
> "The system detects:
> - **Speed anomalies**: Ships exceeding realistic speeds (threshold-based)
> - **AIS gaps**: Transmission blackouts > 4 hours (dark ship indicator)
> - **Zone violations**: Ships entering restricted areas (geofencing)
> - **Dark ships**: Satellite detections without AIS correlation"

### RAG for Maritime Domain
> "We added a RAG chatbot so operators can query in natural language:
> 'Show me suspicious activity near Mumbai in the last 6 hours'
>
> It retrieves relevant alerts and ship reports from ChromaDB, then uses Gemini to generate contextual answers."

---

## Environment Variables

```bash
# .env
AISSTREAM_API_KEY=your_key_here
GOOGLE_API_KEY=your_gemini_key

REDIS_URL=redis://localhost:6379
TIMESCALE_URL=postgresql://postgres:password@localhost:5432/maritime

# Bounding box for Indian Ocean (lat_min, lon_min, lat_max, lon_max)
AIS_BOUNDING_BOX=5,65,25,100
```

---

## Docker Compose (Quick Start)

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  timescaledb:
    image: timescale/timescaledb:latest-pg15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_DB: maritime
    volumes:
      - timescale_data:/var/lib/postgresql/data

volumes:
  redis_data:
  timescale_data:
```

---

## Next Steps

1. **Get API key**: Sign up at https://aisstream.io/
2. **Start Docker**: `docker-compose up -d`
3. **Run ingestion**: `python ingestion/ais_ingester.py`
4. **Watch the data flow!**

---

*Created: Dec 15, 2025*
*For: Blurgs.ai System Design Interview (Dec 16, 9 AM)*
