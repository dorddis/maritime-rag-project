# Maritime Hybrid RAG Implementation Plan

## Overview
Build a hybrid RAG system combining **Text-to-SQL** (structured queries) + **Vector Search** (semantic queries) with intelligent routing.

## Current State
- **Fusion layer**: Complete, outputs to Redis (`fusion:tracks`, `fusion:dark_ships`)
- **PostgreSQL schema**: Exists at `scripts/setup_db.sql` but NOT connected
- **ChromaDB**: Static documents only (maritime_documents.json)
- **Gap**: No data sync from Redis fusion → PostgreSQL

## Architecture

```
User Query: "Tankers near Mumbai with suspicious behavior"
                    │
                    ▼
        ┌───────────────────────┐
        │  Query Router (LLM)   │ ← Classifies: STRUCTURED | SEMANTIC | HYBRID
        └─────────┬─────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│SQL Agent│  │ Vector  │  │ Redis   │
│(LangChn)│  │Retriever│  │Real-time│
└────┬────┘  └────┬────┘  └────┬────┘
     │            │            │
     └────────────┴────────────┘
                  │
                  ▼
        PostgreSQL + pgvector
```

## File Structure

```
maritime-rag-project/
├── rag/
│   ├── __init__.py
│   ├── config.py                 # RAG settings, model config
│   ├── router/
│   │   ├── __init__.py
│   │   └── query_router.py       # LLM query classifier
│   ├── sql_agent/
│   │   ├── __init__.py
│   │   ├── agent.py              # LangChain SQL Agent
│   │   └── schema_context.py     # DB schema for LLM
│   ├── vector/
│   │   ├── __init__.py
│   │   ├── retriever.py          # pgvector semantic search
│   │   └── embeddings.py         # Gemini embedding generation
│   ├── hybrid/
│   │   ├── __init__.py
│   │   └── executor.py           # Combines SQL + Vector + Redis
│   └── sync/
│       ├── __init__.py
│       └── redis_to_postgres.py  # Sync fusion tracks to PostgreSQL
├── scripts/
│   └── setup_db_rag.sql          # Schema updates (pgvector, new tables)
└── api/
    └── rag_endpoints.py          # FastAPI endpoints
```

## Database Schema Updates

**New file**: `scripts/setup_db_rag.sql`

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Unified tracks (synced from Redis fusion)
CREATE TABLE unified_tracks (
    track_id VARCHAR(50) PRIMARY KEY,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    speed_knots DOUBLE PRECISION,
    mmsi VARCHAR(20),
    ship_name VARCHAR(100),
    vessel_type VARCHAR(50),
    is_dark_ship BOOLEAN DEFAULT FALSE,
    dark_ship_confidence DOUBLE PRECISION,
    contributing_sensors TEXT[],
    track_status VARCHAR(20),
    track_quality INTEGER,
    updated_at TIMESTAMPTZ
);

-- Document embeddings (Gemini 768-dim)
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    document_type VARCHAR(50),
    metadata JSONB,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Dark ship events
CREATE TABLE dark_ship_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    track_id VARCHAR(50),
    event_timestamp TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    alert_reason TEXT
);

-- Vector index
CREATE INDEX ON document_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Haversine distance function
CREATE FUNCTION haversine_distance(lat1 FLOAT, lon1 FLOAT, lat2 FLOAT, lon2 FLOAT)
RETURNS FLOAT AS $$ ... $$ LANGUAGE plpgsql;
```

## Implementation Phases

### Phase 1: Data Sync (Day 1-2)
**Goal**: Get fusion data into PostgreSQL

1. Create `scripts/setup_db_rag.sql` and run migrations
2. Implement `rag/sync/redis_to_postgres.py`:
   - Read from `fusion:active_tracks` set
   - Fetch each `fusion:track:{id}` hash
   - Upsert to `unified_tracks` table
   - Sync `fusion:dark_ships` stream to `dark_ship_events`
3. Run sync service at 2 Hz

**Test**: Verify tracks appear in PostgreSQL

### Phase 2: Vector Embeddings (Day 2-3)
**Goal**: Semantic search capability

1. Implement `rag/vector/embeddings.py`:
   - Use Gemini `models/embedding-001` (768 dims)
   - Batch embed documents
2. Create `scripts/seed_embeddings.py`:
   - Load `maritime_documents.json`
   - Generate embeddings
   - Insert to `document_embeddings`
3. Implement `rag/vector/retriever.py`:
   - `search_documents(query, limit)` → pgvector similarity

**Test**: "ships with suspicious behavior" returns relevant docs

### Phase 3: SQL Agent (Day 3-4)
**Goal**: Natural language → SQL

1. Implement `rag/sql_agent/schema_context.py`:
   - Document all tables, columns, relationships
   - Include example queries
2. Implement `rag/sql_agent/agent.py`:
   - LangChain `create_sql_agent` with Gemini 2.5 Flash
   - Add safety checks (no DROP, DELETE without WHERE)

**Test**: "Tankers faster than 15 knots" generates correct SQL

### Phase 4: Query Router (Day 4-5)
**Goal**: Intelligent query classification

1. Implement `rag/router/query_router.py`:
   - Prompt LLM to classify: STRUCTURED | SEMANTIC | HYBRID
   - Extract filters (vessel_type, speed, location, time)
2. Classification rules:
   - Exact filters (speed > 15, type = TANKER) → STRUCTURED
   - Fuzzy patterns (suspicious, unusual) → SEMANTIC
   - Mixed → HYBRID

**Test**: Various queries route correctly

### Phase 5: Hybrid Executor (Day 5-6)
**Goal**: Combine all sources

1. Implement `rag/hybrid/executor.py`:
   - Run SQL agent for structured component
   - Run vector retriever for semantic component
   - Fetch real-time from Redis
   - Fuse with Reciprocal Rank Fusion (RRF)

**Test**: "Tankers with unusual behavior near Mumbai"

### Phase 6: API Integration (Day 6-7)
**Goal**: Expose via REST

1. Add endpoints to `api/rag_endpoints.py`:
   - `POST /api/rag/query` - Main hybrid endpoint
   - `GET /api/rag/documents/search` - Direct vector search
2. Integrate with existing FastAPI in `admin/server.py`

## Key Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `scripts/setup_db_rag.sql` | CREATE | pgvector schema |
| `rag/config.py` | CREATE | Configuration |
| `rag/sync/redis_to_postgres.py` | CREATE | Data sync service |
| `rag/vector/embeddings.py` | CREATE | Gemini embeddings |
| `rag/vector/retriever.py` | CREATE | pgvector search |
| `rag/sql_agent/agent.py` | CREATE | LangChain SQL agent |
| `rag/router/query_router.py` | CREATE | Query classifier |
| `rag/hybrid/executor.py` | CREATE | Result fusion |
| `api/rag_endpoints.py` | CREATE | REST API |
| `admin/server.py` | MODIFY | Mount RAG router |
| `requirements.txt` | MODIFY | Add langchain, pgvector |

## PostgreSQL Setup (Local - No Docker)

**User has**: PostgreSQL 17.7 installed locally

**Setup Steps**:
1. Create database:
   ```sql
   CREATE DATABASE maritime;
   ```
2. Install pgvector extension (Windows):
   - Download from: https://github.com/pgvector/pgvector/releases
   - Or use `vcpkg install pgvector`
   - Then in psql: `CREATE EXTENSION vector;`
3. Connection string: `postgresql://postgres:password@localhost:5432/maritime`

**Alternative if pgvector install is complex on Windows**:
- Use Supabase free tier (has pgvector built-in)
- Or skip vector search initially, use ChromaDB for embeddings

## Dependencies to Add

```
langchain>=0.3.0
langchain-google-genai>=2.0.0
langchain-community>=0.3.0
pgvector>=0.3.0
asyncpg>=0.29.0
psycopg2-binary>=2.9.0
```

## Example Queries After Implementation

| Query | Route | Execution |
|-------|-------|-----------|
| "Tankers near Mumbai faster than 15 knots" | STRUCTURED | SQL: `WHERE vessel_type='TANKER' AND speed>15 AND haversine(...)<50` |
| "Ships in the last hour" | STRUCTURED | SQL: `WHERE updated_at >= NOW() - INTERVAL '1 hour'` |
| "Ships with suspicious behavior" | SEMANTIC | Vector: search document_embeddings |
| "Dark ships near Chennai with unusual patterns" | HYBRID | SQL (dark ships + geo) + Vector (unusual patterns) |

## Success Criteria
1. Sync service runs continuously, tracks in PostgreSQL
2. "Tankers faster than 15 knots" returns correct SQL results
3. "Suspicious behavior" returns semantically relevant documents
4. Hybrid queries combine both effectively
5. API response time < 2 seconds
