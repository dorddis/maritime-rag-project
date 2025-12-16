# Maritime Dark Ship Detection System

> Real-time maritime surveillance that fuses AIS, radar, satellite, and drone data to detect dark ships, with a hybrid RAG pipeline for natural language queries.

## Key Features

- **Multi-Sensor Fusion** - Correlate 4 sensor types using GNN algorithm with Hungarian assignment
- **Dark Ship Detection** - Identify vessels evading AIS tracking (transmitter off or spoofing)
- **Hybrid RAG** - SQL + Vector + Real-time search with intelligent query routing
- **3D Globe Dashboard** - Real-time visualization with WebSocket updates

## Architecture

```
User Query: "Dark ships near Mumbai"
                    |
                    v
        +-------------------+
        |   QUERY ROUTER    |  <- Gemini 2.5 classifies query type
        +-------------------+
                    |
    +---------------+---------------+
    |               |               |
    v               v               v
+--------+    +----------+    +---------+
|  SQL   |    |  Vector  |    | Redis   |
| Agent  |    |  Search  |    |Real-time|
+--------+    +----------+    +---------+
    |               |               |
    +-------+-------+-------+-------+
            |               |
            v               v
      PostgreSQL         Redis
      (Historical)     (Live Tracks)
            ^               ^
            |               |
    +-------+---------------+-------+
    |         FUSION LAYER          |
    |  GNN Correlation + Dark Ship  |
    +-------------------------------+
                    ^
    +-------+-------+-------+-------+
    |       |       |       |       |
  [AIS]  [Radar] [Sat]  [Drone]
  NMEA   Binary  GeoJSON  YOLO
```

See **[docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md)** for detailed diagrams.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React, Three.js Globe, shadcn/ui |
| API | FastAPI, WebSocket |
| RAG | Gemini 2.5, LangChain, pgvector |
| Storage | PostgreSQL (historical) + Redis (real-time) |
| Fusion | Custom GNN correlation with Hungarian algorithm |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ with pgvector extension
- Redis 7+

### 1. Clone and Install

```bash
git clone https://github.com/dorddis/maritime-rag-project.git
cd maritime-rag-project

# Python dependencies
pip install -r requirements.txt

# Dashboard dependencies
cd dashboard && npm install && cd ..
```

### 2. Environment Setup

```bash
# Create .env file
GOOGLE_API_KEY=your_gemini_api_key
POSTGRES_URL=postgresql://user:pass@localhost:5432/maritime
REDIS_URL=redis://localhost:6379
```

### 3. Database Setup

```bash
# Run PostgreSQL setup
python -X utf8 scripts/setup_postgres.py
```

### 4. Run the System

```bash
# Start everything (backend + dashboard)
python -X utf8 run_demo.py

# Or backend only
python -X utf8 run_demo.py --backend-only
```

- **Dashboard**: http://localhost:3000
- **API**: http://localhost:8001
- **API Docs**: http://localhost:8001/docs

## Project Structure

```
maritime-rag-project/
|
+-- admin/                 # FastAPI server + ingester management
|   +-- server.py          # Main API server
|   +-- ingester_manager.py
|
+-- api/                   # API endpoints
|   +-- rag_endpoints.py   # RAG query endpoints
|   +-- chat_endpoints.py  # Chat interface
|
+-- dashboard/             # Next.js frontend
|   +-- src/
|       +-- app/           # Pages (/, /chat)
|       +-- components/    # React components
|           +-- globe/     # 3D globe visualization
|           +-- chat/      # RAG chat interface
|
+-- ingestion/             # Data ingestion pipeline
|   +-- fusion/            # Multi-sensor correlation
|   +-- generators/        # Synthetic data generators
|   +-- ingesters/         # Sensor-specific ingesters
|   +-- parsers/           # Format parsers (NMEA, binary, GeoJSON)
|   +-- shared/            # Fleet manager, world simulator
|
+-- rag/                   # RAG pipeline
|   +-- router/            # Query classification
|   +-- sql_agent/         # Text-to-SQL with LangChain
|   +-- vector/            # pgvector semantic search
|   +-- hybrid/            # Result fusion (RRF)
|   +-- sync/              # Redis -> PostgreSQL sync
|
+-- scripts/               # Setup and utility scripts
+-- docs/                  # Documentation
    +-- ARCHITECTURE_DIAGRAMS.md  # System diagrams
```

## How It Works

### Dark Ship Detection

Ships are flagged as "dark" when:
1. **AIS Gap**: Previously broadcasting AIS, then silent for 15+ minutes while still visible on radar/satellite
2. **Never Had AIS**: Detected by 2+ non-AIS sensors with consistent correlation

```
Track with AIS history --> AIS gap > 15 min --> Still seen by radar/sat? --> DARK SHIP
Track without AIS ------> 2+ sensors agree? -----------------------> DARK SHIP
```

### RAG Query Types

| Query Type | Example | Execution |
|------------|---------|-----------|
| STRUCTURED | "Tankers faster than 15 knots" | SQL Agent |
| SEMANTIC | "Ships with suspicious behavior" | Vector Search |
| HYBRID | "Dark ships near Mumbai with unusual patterns" | SQL + Vector + Real-time |
| GENERAL | "What is AIS?" | Direct LLM |

### Sensor Fusion

| Sensor | Coverage | Identity | Accuracy | Sees Dark Ships |
|--------|----------|----------|----------|-----------------|
| AIS | Global | Yes (MMSI) | +/- 10m | No |
| Radar | 40-80nm | No | +/- 100m | Yes |
| Satellite | Wide area | No | +/- 200m | Yes |
| Drone | Small area | Visual | +/- 50m | Yes |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/rag/query` | POST | Hybrid RAG query |
| `/api/rag/chat/stream` | POST | SSE streaming chat |
| `/api/fusion/tracks` | GET | Active fused tracks |
| `/api/fusion/dark-ships` | GET | Flagged dark ships |
| `/api/ingesters` | GET | Ingester status |
| `/api/ingesters/{name}/start` | POST | Start ingester |
| `/ws/dashboard` | WS | Real-time updates |

## Key Numbers

| Metric | Value |
|--------|-------|
| Ships in simulation | 50 (configurable) |
| Dark ship detection threshold | 15 min AIS gap |
| Fusion processing rate | 2 Hz |
| Vector dimensions | 768 (Gemini embedding) |
| Sensor update rates | AIS: 0.8Hz, Radar: 1Hz |

## Interview Talking Points

### System Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | PostgreSQL + Redis | Historical queries vs real-time streaming |
| Fusion algorithm | GNN + Hungarian | Optimal multi-sensor assignment |
| RAG approach | Hybrid | Structured data + semantic understanding |
| Query routing | LLM-based | Handles ambiguous natural language |

### Trade-offs Considered

| Aspect | Option A | Option B | Chosen |
|--------|----------|----------|--------|
| Anomaly detection | Rule-based | ML-based | Rule-based (explainable) |
| Real-time updates | Polling | WebSocket | WebSocket (lower latency) |
| Vector DB | ChromaDB | pgvector | pgvector (single DB) |

### Scalability Path

1. **Current**: Single-node, 50 ships, 2 Hz processing
2. **Scale**: Kafka for ingestion, Flink for processing, TimescaleDB for time-series
3. **Production**: Kubernetes, horizontal scaling, CDC for sync

---

## Documentation

- [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) - Visual system design
- [Research Notes](docs/research/) - RAG architecture research
- [Archive](docs/archive/) - Historical planning documents

---

Built by **Siddharth Rodrigues** - 2025
