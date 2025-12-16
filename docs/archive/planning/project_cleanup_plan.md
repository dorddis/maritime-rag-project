# Maritime RAG Project - Cleanup Plan

## Goal
Make the project interview-ready by cleaning up messy areas and rewriting the README to properly showcase the architecture.

---

## Current State Summary

**The Good:**
- Excellent architecture (6-layer system: Ground Truth -> Sensors -> Redis -> Fusion -> PostgreSQL -> RAG)
- Working dashboard with real-time globe visualization
- Comprehensive ARCHITECTURE_DIAGRAMS.md (425 lines of clean diagrams)
- Modular codebase with clear separation of concerns

**The Bad:**
- README.md is **severely outdated** - references old demo scripts, not the real system
- Multiple orphaned entry point scripts in root
- Empty directories that serve no purpose
- Duplicate chat implementations in dashboard
- Stray files (nul, untracked files)
- Ingesters scattered between two locations

---

## Cleanup Tasks

### Phase 1: Delete Stray/Unnecessary Files

| File/Dir | Action | Reason |
|----------|--------|--------|
| `nul` | DELETE | Windows error artifact |
| `processing/` | DELETE | Empty directory, never used |
| `data/drone/` | DELETE | Empty, data goes to Redis |
| `data/nmea/` | DELETE | Empty, data goes to Redis |
| `data/radar/` | DELETE | Empty, data goes to Redis |
| `data/satellite/` | DELETE | Empty, data goes to Redis |

Keep `data/` as placeholder with `.gitkeep` if needed.

### Phase 2: Archive Legacy Scripts

Move to `archive/legacy/` (not delete - preserve history):

| File | Reason |
|------|--------|
| `sample_ais_data.py` | Superseded by FleetManager + WorldSimulator |
| `mock_ship_generator.py` | Superseded by multi-sensor system |
| `multi_source_generator.py` | Superseded by individual ingesters |
| `maritime_rag.py` | Superseded by `rag/` module |
| `maritime_analytics.py` | Superseded by fusion layer |
| `run_system.py` | Old entry point, superseded by admin/server.py |

Keep `run_demo.py` as the canonical entry point (or rename to `main.py`).

### Phase 3: Consolidate Ingesters

Move root-level ingesters to proper location:

```
BEFORE:
ingestion/ais_ingester.py          <- Old location
ingestion/satellite_ingester.py    <- Old location
ingestion/weather_ingester.py      <- Old location (unused?)
ingestion/ingesters/*.py           <- New location

AFTER:
ingestion/ingesters/*.py           <- All ingesters here
```

Or archive the old ones if they're truly superseded.

### Phase 4: Consolidate Dashboard Chat

Decide on ONE chat implementation:

| Route | Component | Purpose |
|-------|-----------|---------|
| `/chat` | `chat/` | Full RAG with pipeline visualization |
| `/chat-simple` | `chat-simple/` | Lightweight Q&A |

**Recommendation:** Keep both but document clearly. Or merge into one with a "simple mode" toggle.

### Phase 5: Clean Up Docs

**Archive outdated planning docs:**
```
docs/planning/ -> docs/archive/planning/
```

Keep only actively relevant docs in `docs/`:
- `ARCHITECTURE_DIAGRAMS.md` (reference from README)
- `API.md` (if exists, or create)

**Large docs to review:**
- `RAG_ARCHITECTURE_RESEARCH.md` (1,349 lines) -> Move to `docs/research/`
- `FULL_SYSTEM_SPEC.md` (480 lines) -> Keep or archive
- `UNIFIED_SIMULATION_PLAN.md` (321 lines) -> Archive (implementation done)
- `CONTEXT.md` (253 lines) -> Keep (active reference)

### Phase 6: Consolidate Config/Setup Scripts

```
scripts/
  setup_db.sql        <- Merge into one
  setup_db_rag.sql    <- Merge into one
  setup_postgres.py   <- Keep
  clear_databases.py  <- Keep
```

Create single `scripts/setup_all.sql` or document the order.

---

## Phase 7: Rewrite README.md

### New README Structure

```markdown
# Maritime Dark Ship Detection System

> Real-time maritime surveillance with multi-sensor fusion and RAG-powered natural language queries.

## What This Project Demonstrates

1. **Multi-Sensor Data Fusion** - Correlate AIS, radar, satellite, drone data
2. **Dark Ship Detection** - Identify vessels evading AIS tracking
3. **Hybrid RAG Pipeline** - SQL + Vector + Real-time search with Gemini
4. **Real-Time Dashboard** - 3D globe visualization with WebSocket updates

## Architecture

See [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) for detailed diagrams.

[Insert simplified high-level diagram from ARCHITECTURE_DIAGRAMS.md]

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React, Three.js Globe |
| API | FastAPI (Python) |
| RAG | Gemini 2.5, LangChain, pgvector |
| Databases | PostgreSQL + Redis |
| Fusion | Custom GNN correlation algorithm |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (with pgvector)
- Redis 7+

### 1. Backend Setup
[Actual working instructions]

### 2. Dashboard Setup
[Actual working instructions]

### 3. Run the System
[Actual working instructions]

## Key Features

### Dark Ship Detection
[Brief explanation with diagram reference]

### RAG Query Types
[Table of query types: STRUCTURED, SEMANTIC, HYBRID, GENERAL]

### Real-Time Fusion
[Brief explanation]

## Project Structure

[Clean tree showing main directories]

## API Endpoints

[Table of key endpoints]

## Interview Talking Points

[Keep this section - it's valuable]

## Author

Built by [Your Name] - December 2024
```

---

## Implementation Order

### Step 1: File Cleanup (5 min)
- Delete `nul`
- Delete empty `processing/` and `data/*` subdirs
- Create `archive/legacy/` directory

### Step 2: Archive Legacy Scripts (5 min)
- Move 6 legacy scripts to `archive/legacy/`
- Keep `run_demo.py` or rename to `main.py`

### Step 3: Verify System Still Works (5 min)
- Run admin/server.py
- Run dashboard
- Confirm nothing broke

### Step 4: Consolidate Ingesters (10 min)
- Review which are active vs deprecated
- Move or archive appropriately

### Step 5: Clean Docs (10 min)
- Create `docs/archive/`
- Move planning docs there
- Move research docs there

### Step 6: Rewrite README (30 min)
- Follow new structure above
- Reference ARCHITECTURE_DIAGRAMS.md properly
- Add actual working setup instructions
- Test the instructions work

### Step 7: Final Commit (5 min)
- Single commit: "refactor: clean up project structure and rewrite README"
- Push to main

---

## Files to Create

| File | Purpose |
|------|---------|
| `archive/legacy/README.md` | Explain what these old files are |
| `docs/archive/README.md` | Explain archived planning docs |

## Files to Delete

| File | Reason |
|------|--------|
| `nul` | Stray Windows artifact |
| `processing/` | Empty, unused |
| `data/drone/` | Empty |
| `data/nmea/` | Empty |
| `data/radar/` | Empty |
| `data/satellite/` | Empty |

## Files to Move

| From | To |
|------|-----|
| `sample_ais_data.py` | `archive/legacy/` |
| `mock_ship_generator.py` | `archive/legacy/` |
| `multi_source_generator.py` | `archive/legacy/` |
| `maritime_rag.py` | `archive/legacy/` |
| `maritime_analytics.py` | `archive/legacy/` |
| `run_system.py` | `archive/legacy/` |
| `docs/planning/*.md` | `docs/archive/planning/` |
| `RAG_ARCHITECTURE_RESEARCH.md` | `docs/research/` |
| `UNIFIED_SIMULATION_PLAN.md` | `docs/archive/` |

---

## Success Criteria

- [ ] No stray files in root
- [ ] Clear single entry point (`run_demo.py` or `main.py`)
- [ ] README accurately describes the system
- [ ] README references ARCHITECTURE_DIAGRAMS.md
- [ ] Setup instructions actually work
- [ ] Project structure is clean and intuitive
- [ ] Interviewer can understand the system in 5 minutes
