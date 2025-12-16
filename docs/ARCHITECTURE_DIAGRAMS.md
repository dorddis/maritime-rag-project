# Maritime RAG - Architecture Diagrams

Simple diagrams for explaining the system architecture.

---

## 1. High-Level System Overview

```
                    ┌──────────────────┐
                    │   USER QUERY     │
                    │  "Dark ships     │
                    │   near Mumbai"   │
                    └────────┬─────────┘
                             │
                             ▼
╔════════════════════════════════════════════════════════════════════╗
║                        RAG LAYER                                    ║
║  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌────────────┐   ║
║  │  Router  │ -> │ SQL Agent │ -> │  Vector  │ -> │   Fusion   │   ║
║  │ (Gemini) │    │ (LangChain)│   │ (pgvector)│   │   (RRF)    │   ║
║  └──────────┘    └───────────┘    └──────────┘    └────────────┘   ║
╚════════════════════════════════════════════════════════════════════╝
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
          ▼                                     ▼
┌───────────────────┐                 ┌───────────────────┐
│    PostgreSQL     │                 │      Redis        │
│   (Historical)    │                 │   (Real-time)     │
│  - unified_tracks │                 │ - fusion:tracks   │
│  - dark_events    │                 │ - sensor streams  │
│  - embeddings     │                 └───────────────────┘
└───────────────────┘                           ▲
          ▲                                     │
          │            ┌────────────────────────┘
          │            │
╔═════════════════════════════════════════╗
║          FUSION LAYER                   ║
║  ┌───────────────────────────────────┐  ║
║  │  GNN Correlation + Dark Ship     │  ║
║  │  Detection Algorithm              │  ║
║  └───────────────────────────────────┘  ║
╚═════════════════════════════════════════╝
                    ▲
    ┌───────────────┼───────────────┬───────────────┐
    │               │               │               │
┌───────┐      ┌───────┐      ┌─────────┐      ┌───────┐
│  AIS  │      │ Radar │      │Satellite│      │ Drone │
│ Stream│      │ Stream│      │  Stream │      │ Stream│
└───────┘      └───────┘      └─────────┘      └───────┘
    ▲               ▲               ▲               ▲
    │               │               │               │
╔═════════════════════════════════════════════════════════╗
║                   SENSOR LAYER                          ║
║   NMEA Parser   Binary Parser  GeoJSON Parser  CV Parser║
╚═════════════════════════════════════════════════════════╝
                             ▲
                             │
╔═════════════════════════════════════════════════════════╗
║                GROUND TRUTH LAYER                       ║
║  ┌──────────────────┐    ┌───────────────────┐          ║
║  │  Fleet Manager   │    │  World Simulator  │          ║
║  │  (Ship Creation) │    │  (Physics Engine) │          ║
║  └──────────────────┘    └───────────────────┘          ║
╚═════════════════════════════════════════════════════════╝
```

---

## 2. Data Flow Diagram (Layer by Layer)

```
LAYER 1: GROUND TRUTH (Generation)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   FleetManager                    WorldSimulator                  │
│   ┌───────────┐                   ┌─────────────┐                 │
│   │ Creates   │                   │ Moves ships │                 │
│   │ 50 ships  │ ────────────────> │ along lanes │                 │
│   │ in Redis  │                   │ at 60x time │                 │
│   └───────────┘                   └─────────────┘                 │
│        │                                │                         │
│        ▼                                ▼                         │
│   [maritime:ship:{mmsi}]    [Updates lat/lon/speed/ais_enabled]  │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
LAYER 2: SENSORS (Ingestion)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ┌───────┐   ┌───────┐   ┌───────────┐   ┌───────┐               │
│  │  AIS  │   │ Radar │   │ Satellite │   │ Drone │               │
│  └───────┘   └───────┘   └───────────┘   └───────┘               │
│      │           │            │              │                    │
│  [NMEA 0183] [Binary]    [GeoJSON]     [YOLO JSON]               │
│      │           │            │              │                    │
│      ▼           ▼            ▼              ▼                    │
│  Only ships   All ships   Wide area     High detail              │
│  with AIS ON  in range    periodic      small area               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
LAYER 3: FAST STORAGE (Redis Streams)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   ais:positions    radar:contacts    satellite:detections        │
│        │                │                   │                     │
│        └────────────────┼───────────────────┘                     │
│                         │                                         │
│                    drone:detections                               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
LAYER 4: FUSION (Processing)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   1. Read all 4 streams                                          │
│   2. Correlate detections -> tracks (GNN algorithm)              │
│   3. Detect dark ships (AIS gaps + multi-sensor)                 │
│   4. Publish unified tracks                                       │
│                                                                   │
│   Output: fusion:tracks, fusion:dark_ships                       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
LAYER 5: PERSISTENT STORAGE (PostgreSQL)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   unified_tracks          dark_ship_events        embeddings     │
│   ┌────────────┐          ┌───────────────┐       ┌─────────┐    │
│   │ track_id   │          │ track_id      │       │ doc_id  │    │
│   │ mmsi       │          │ timestamp     │       │ vector  │    │
│   │ position   │   <--->  │ confidence    │       │ meta    │    │
│   │ is_dark    │          │ alert_reason  │       └─────────┘    │
│   │ sensors    │          └───────────────┘                      │
│   └────────────┘                                                  │
│                                                                   │
│   Synced from Redis at 2 Hz                                      │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
LAYER 6: RAG INFERENCE
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   Query Router (Gemini 2.5 Pro)                                  │
│        │                                                          │
│        ├──> STRUCTURED ──> SQL Agent ──> PostgreSQL              │
│        │                                                          │
│        ├──> SEMANTIC ────> Vector Search ──> pgvector            │
│        │                                                          │
│        ├──> HYBRID ──────> Both + Redis Real-time                │
│        │                                                          │
│        └──> GENERAL ─────> Direct LLM Response                   │
│                                                                   │
│   Result Fusion: Reciprocal Rank Fusion (RRF)                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Sensor Comparison Matrix

```
┌─────────────┬──────────┬──────────┬────────────┬───────────┐
│   Sensor    │ Coverage │ Identity │  Accuracy  │ Dark Ship │
├─────────────┼──────────┼──────────┼────────────┼───────────┤
│    AIS      │  Global  │   Yes    │   +/- 10m  │    No     │
├─────────────┼──────────┼──────────┼────────────┼───────────┤
│   Radar     │  40-80nm │    No    │  +/- 100m  │    Yes    │
├─────────────┼──────────┼──────────┼────────────┼───────────┤
│ Satellite   │   Wide   │    No    │  +/- 200m  │    Yes    │
├─────────────┼──────────┼──────────┼────────────┼───────────┤
│   Drone     │  Small   │   Yes    │   +/- 50m  │    Yes    │
└─────────────┴──────────┴──────────┴────────────┴───────────┘

Key Insight: AIS is most accurate but ONLY sees cooperative vessels.
             Fusion combines all sensors to detect dark ships.
```

---

## 4. Dark Ship Detection Logic

```
                   ┌───────────────────┐
                   │   Incoming Track  │
                   └────────┬──────────┘
                            │
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
   ┌────────────────┐             ┌────────────────┐
   │ Has AIS History│             │   No AIS Ever  │
   └────────┬───────┘             └────────┬───────┘
            │                               │
            ▼                               ▼
   ┌────────────────┐             ┌────────────────┐
   │ AIS Gap > 15min│             │ 2+ Non-AIS     │
   └────────┬───────┘             │ sensors agree? │
            │                     └────────┬───────┘
    ┌───────┴───────┐                      │
    │               │               ┌──────┴───────┐
    ▼               ▼               │              │
  [No]            [Yes]           [No]           [Yes]
    │               │               │              │
    ▼               ▼               ▼              ▼
 Normal          Check if        Normal       DARK SHIP
 Track           still seen      Track        (confidence
                 by other                     0.5-1.0)
                 sensors
                    │
            ┌───────┴───────┐
            │               │
            ▼               ▼
       [Not seen]      [Seen by
            │          radar/sat/
            ▼          drone]
         Track              │
         Lost               ▼
                       DARK SHIP
                       (AIS gap)
```

---

## 5. RAG Query Routing

```
User Query: "Show me tankers with suspicious behavior near Mumbai"
                            │
                            ▼
              ┌─────────────────────────┐
              │       QUERY ROUTER      │
              │      (Gemini 2.5 Pro)   │
              └─────────────┬───────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
        ┌───────────┐              ┌───────────┐
        │ Extracted │              │ Semantic  │
        │ Filters   │              │ Query     │
        └───────────┘              └───────────┘
              │                           │
    ┌─────────┴─────────┐                 │
    │                   │                 │
    ▼                   ▼                 ▼
┌────────┐        ┌────────┐        ┌───────────┐
│ vessel │        │  port  │        │"suspicious│
│ =TANKER│        │=Mumbai │        │ behavior" │
└────────┘        └────────┘        └───────────┘
    │                   │                 │
    └───────────────────┘                 │
              │                           │
              ▼                           ▼
        ┌───────────┐              ┌───────────┐
        │ SQL Agent │              │  Vector   │
        │ (filters) │              │  Search   │
        └───────────┘              └───────────┘
              │                           │
              ▼                           ▼
        ┌───────────┐              ┌───────────┐
        │ 12 tankers│              │ anomaly   │
        │ near port │              │ patterns  │
        └───────────┘              └───────────┘
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │    RESULT FUSION (RRF)  │
              └─────────────┬───────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │   "3 tankers showing      │
              │   suspicious patterns:    │
              │   - AEGEAN STAR (dark 2h) │
              │   - PACIFIC VOYAGER ...   │
              └───────────────────────────┘
```

---

## 6. Fusion Algorithm (Simplified)

```
                    SENSOR DETECTIONS
                           │
       ┌───────────────────┼───────────────────┐
       │         │         │         │         │
       ▼         ▼         ▼         ▼         ▼
    [AIS 1]  [Radar 1] [Radar 2] [Sat 1]  [Drone 1]
       │         │         │         │         │
       └───────────────────┼───────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │     CORRELATION        │
              │   (Which detections    │
              │    are same ship?)     │
              └────────────┬───────────┘
                           │
     Distance + Uncertainty Gating:
     Gate = 3 * sqrt(track_err^2 + sensor_err^2)
                           │
                           ▼
              ┌────────────────────────┐
              │  HUNGARIAN ALGORITHM   │
              │  (Optimal assignment)  │
              └────────────┬───────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌───────────┐             ┌───────────┐
       │  Matched  │             │ Unmatched │
       │ Detections│             │ Detections│
       └───────────┘             └───────────┘
              │                         │
              ▼                         ▼
       ┌───────────┐             ┌───────────┐
       │  Update   │             │   Create  │
       │  Existing │             │    New    │
       │   Track   │             │   Track   │
       └───────────┘             └───────────┘
              │
              ▼
       ┌───────────┐
       │  Fused    │
       │ Position  │
       └───────────┘
              │
   Inverse Variance Weighting:
   pos = sum(pos_i / err_i^2) / sum(1/err_i^2)
              │
              ▼
       ┌───────────┐
       │ Unified   │
       │   Track   │
       └───────────┘
```

---

## 7. Tech Stack Summary

```
┌──────────────────────────────────────────────────────────────────┐
│                         PRESENTATION                              │
│  ┌────────────────────┐    ┌──────────────────┐                   │
│  │ Next.js Dashboard  │    │   REST API       │                   │
│  │ (React + Globe)    │    │   (FastAPI)      │                   │
│  └────────────────────┘    └──────────────────┘                   │
├──────────────────────────────────────────────────────────────────┤
│                         INFERENCE                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │   Router   │  │ SQL Agent  │  │   Vector   │  │   Hybrid   │   │
│  │  (Gemini)  │  │ (LangChain)│  │ (pgvector) │  │   (RRF)    │   │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                         STORAGE                                   │
│  ┌────────────────────────┐    ┌────────────────────────┐         │
│  │      PostgreSQL        │    │        Redis           │         │
│  │ - Unified Tracks       │    │ - Streams (4 sensors)  │         │
│  │ - Dark Ship Events     │    │ - Track Hashes         │         │
│  │ - Vector Embeddings    │    │ - Fleet State          │         │
│  └────────────────────────┘    └────────────────────────┘         │
├──────────────────────────────────────────────────────────────────┤
│                         PROCESSING                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    FUSION ENGINE                            │  │
│  │  - GNN Correlation    - Dark Ship Detection    - Track Mgmt │  │
│  └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                         INGESTION                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │   AIS    │  │  Radar   │  │Satellite │  │  Drone   │          │
│  │  (NMEA)  │  │ (Binary) │  │ (GeoJSON)│  │(CV JSON) │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
├──────────────────────────────────────────────────────────────────┤
│                         SIMULATION                                │
│  ┌────────────────────────┐    ┌────────────────────────┐         │
│  │    Fleet Manager       │    │   World Simulator      │         │
│  │  (Ship Generation)     │    │   (Physics Engine)     │         │
│  └────────────────────────┘    └────────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Key Numbers to Remember

```
┌───────────────────────────┬──────────────────────────────────┐
│        Component          │             Value                │
├───────────────────────────┼──────────────────────────────────┤
│ Ships in simulation       │ 50 (configurable)                │
│ Shipping lanes            │ 7 (Indian Ocean region)          │
│ Dark ship percentage      │ ~2% (unknown type)               │
│ Sensor update rates       │ AIS: 0.8Hz, Radar: 1Hz           │
│ Fusion processing rate    │ 2 Hz                             │
│ Redis -> PostgreSQL sync  │ 2 Hz                             │
│ AIS accuracy              │ +/- 10m                          │
│ Radar accuracy            │ +/- 100m                         │
│ Dark ship threshold       │ 15 min AIS gap                   │
│ Track quality max         │ 100 points                       │
│ Vector dimensions         │ 768 (Gemini embedding)           │
│ LLM model                 │ Gemini 2.5 Pro/Flash             │
└───────────────────────────┴──────────────────────────────────┘
```

---

## 9. One-Liner System Description

> **A real-time maritime surveillance system that fuses AIS, radar, satellite, and drone data to detect dark ships, with a RAG pipeline for natural language queries over vessel tracks.**
