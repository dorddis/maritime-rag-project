# Legacy Scripts (Archived)

These scripts were the original demo implementations, now superseded by the modular architecture.

| Script | Original Purpose | Superseded By |
|--------|------------------|---------------|
| `sample_ais_data.py` | Generate synthetic AIS data | `ingestion/shared/fleet_manager.py` + `world_simulator.py` |
| `mock_ship_generator.py` | Mock ship simulator | `ingestion/shared/world_simulator.py` |
| `multi_source_generator.py` | Multi-sensor data generation | Individual sensor ingesters in `ingestion/` |
| `maritime_rag.py` | Simple RAG demo | `rag/` module with hybrid search |
| `maritime_analytics.py` | Basic analytics | Fusion layer in `ingestion/fusion/` |
| `run_system.py` | Old entry point | `admin/server.py` + `run_demo.py` |

These files are kept for historical reference only.
