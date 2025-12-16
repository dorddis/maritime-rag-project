# Maritime RAG + Analytics Project

**Built for: Blurgs.ai System Design Interview Prep**

This project demonstrates:
1. **RAG (Retrieval Augmented Generation)** on domain-specific data
2. **Geospatial queries** on ship tracking (AIS) data
3. **Time-series anomaly detection** for maritime security
4. **Multi-source data handling** patterns

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key
set GOOGLE_API_KEY=your_gemini_api_key

# 3. Generate sample AIS data
python sample_ais_data.py

# 4. Run analytics demo
python maritime_analytics.py

# 5. Run RAG demo
python maritime_rag.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AIS DATA SOURCES                          │
│            (Ships broadcasting positions)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 DATA GENERATION LAYER                        │
│                  sample_ais_data.py                          │
│                                                              │
│  • Simulates realistic ship trajectories                     │
│  • Generates anomalous behavior (dark ships, speed spikes)   │
│  • Creates documents for RAG ingestion                       │
└─────────────────────────────────────────────────────────────┘
                    │                        │
                    ▼                        ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   RAG SYSTEM             │    │   ANALYTICS ENGINE       │
│   maritime_rag.py        │    │   maritime_analytics.py  │
│                          │    │                          │
│ • ChromaDB vectors       │    │ • Speed anomalies        │
│ • Gemini 2.5 Flash LLM   │    │ • AIS gap detection      │
│ • Natural language Q&A   │    │ • Zone violations        │
│                          │    │ • Geospatial queries     │
└──────────────────────────┘    └──────────────────────────┘
```

## Key Concepts Demonstrated

### 1. RAG Pipeline
```
User Query → Embedding → Vector Search → Context Retrieval → LLM → Answer
```

### 2. Anomaly Detection
- **Speed anomalies**: Ships exceeding realistic speeds
- **AIS gaps**: Transmission blackouts (dark ships)
- **Zone violations**: Unauthorized area entry

### 3. Geospatial Queries
- Ships within radius of port
- Ships in bounding box
- Distance calculations (Haversine formula)

### 4. Time-Series Patterns
- Traffic aggregation over time
- Historical trajectory analysis
- Statistical profiling by ship type

## Interview Talking Points

### "How would you design this for Blurgs?"

1. **Ingestion**: Kafka topics per data source (AIS, radar, satellite)
2. **Processing**: Flink for real-time correlation and anomaly detection
3. **Storage**: TimescaleDB for time-series, PostGIS for geospatial
4. **RAG**: Vector DB for natural language queries on reports
5. **Alerting**: Rules engine + notification service

### Trade-offs

| Decision | Option A | Option B |
|----------|----------|----------|
| Anomaly detection | Rule-based (explainable) | ML-based (complex patterns) |
| Storage | Single DB (simple) | Polyglot (optimized per query type) |
| Processing | Batch (cheaper) | Stream (real-time alerts) |

## Files

- `sample_ais_data.py` - Generate synthetic AIS data
- `maritime_rag.py` - RAG system with Gemini
- `maritime_analytics.py` - Anomaly detection and analytics
- `requirements.txt` - Python dependencies
