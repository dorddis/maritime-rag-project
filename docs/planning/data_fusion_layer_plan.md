# Maritime RAG - Data Fusion Layer Implementation Plan

## Overview
Build a data fusion layer that correlates detections from 4 sensor streams to create unified vessel tracks and detect dark ships.

## Input Streams (Already Implemented)
| Stream | Sensor | Accuracy | Identity | Sees Dark Ships |
|--------|--------|----------|----------|-----------------|
| `ais:positions` | AIS | ±10m | MMSI | NO |
| `radar:contacts` | Radar | ±500m | track_id | YES |
| `satellite:detections` | Satellite | ±2km | none | YES |
| `drone:detections` | Drone | ±50m | visual | YES |

## Output Streams (New)
- `fusion:tracks` - Real-time unified track updates
- `fusion:track:{id}` - Hash per track (current state)
- `fusion:active_tracks` - Set of active track IDs
- `fusion:dark_ships` - Dark ship alert stream
- `fusion:status` - Ingester status hash

---

## File Structure
```
ingestion/fusion/               # NEW DIRECTORY
├── __init__.py
├── schema.py                   # UnifiedTrack, SensorContribution models
├── config.py                   # Sensor configs, gating thresholds
├── correlation.py              # Gated GNN correlation algorithm
├── track_manager.py            # Track lifecycle, dark ship detection
└── fusion_ingester.py          # Main async ingester process
```

---

## Implementation Steps

### Step 1: Create schema.py
- `UnifiedTrack` model with position, velocity, identity, dark_ship_flag
- `SensorContribution` to track which sensors contributed
- `TrackStatus` enum: TENTATIVE → CONFIRMED → COASTING → DROPPED
- `to_redis_dict()` method for Redis serialization

### Step 2: Create config.py
- `SensorCharacteristics` dataclass (accuracy, update rate, capabilities)
- `SENSOR_CONFIG` dict for AIS, Radar, Satellite, Drone
- `CorrelationGates` (max_distance, time_window, chi2_threshold)
- `DarkShipDetectionConfig` (AIS gap threshold, confidence thresholds)

### Step 3: Create correlation.py
- `CorrelationEngine` class
- `correlate_detection()` - Single detection to tracks
- `batch_correlate()` - GNN assignment using Hungarian algorithm
- Position prediction using velocity extrapolation
- Adaptive gate sizing based on combined uncertainty
- Mahalanobis distance with kinematic consistency scoring

### Step 4: Create track_manager.py
- `TrackManager` class
- `create_track()` - Initialize from first detection
- `update_track()` - Weighted average position update
- `check_dark_ships()` - Flag vessels with AIS gaps or multi-sensor non-AIS correlation
- `age_tracks()` - Handle coasting and dropping stale tracks
- Track quality scoring based on sensors, updates, uncertainty

### Step 5: Create fusion_ingester.py
- Async Redis consumer (XREADGROUP from all 4 streams)
- Main loop: read → correlate → update tracks → publish
- Publish to `fusion:tracks` stream and `fusion:track:*` hashes
- Dark ship alerts to `fusion:dark_ships` stream
- Status updates to `fusion:status` hash

### Step 6: Register with Admin Server
- Add `"fusion"` to `INGESTERS` dict in `ingester_manager.py`
- Add `/api/fusion/tracks` and `/api/fusion/dark-ships` endpoints

### Step 7: Dashboard Integration (Optional)
- Add fused tracks layer to globe visualization
- Show dark ship markers with alert styling

---

## Key Algorithm: Dark Ship Detection

```
IF track.identity_source == AIS AND ais_last_seen > 15 min:
    IF still seen by radar/satellite/drone:
        → FLAG AS DARK SHIP (AIS went silent)

IF track.identity_source == UNKNOWN:
    IF seen by >= 2 non-AIS sensors OR confirmed by drone:
        → FLAG AS DARK SHIP (never had AIS)
```

---

## Critical Implementation Details

1. **Position Fusion**: Weighted average by inverse variance
   - `fused_pos = (track_pos/track_var + det_pos/det_var) / (1/track_var + 1/det_var)`

2. **Gate Sizing**: 3-sigma combined uncertainty
   - `gate = 3 * sqrt(track_uncertainty² + sensor_uncertainty²)`

3. **Track Confirmation**: Requires 3+ updates from any sensors

4. **Coasting Timeout**: 5 min without updates → increase uncertainty
   **Drop Timeout**: 10 min without updates → remove track

---

## Testing Approach
1. Start world simulator with 500 ships (5% dark)
2. Start all 4 sensor ingesters
3. Start fusion ingester
4. Verify: track count ≈ ship count, dark ships flagged correctly
5. Toggle AIS on ships → verify detection of new dark ships

---

## Files to Modify
- `admin/ingester_manager.py` - Add fusion ingester config
- `admin/server.py` - Add fusion API endpoints + WebSocket updates
- `dashboard/src/lib/types.ts` - Add fusion ingester + track types
- `dashboard/src/lib/api.ts` - Add fusion API calls
- `dashboard/src/components/globe/maritime-globe.tsx` - Add fused tracks layer
- `dashboard/src/components/dashboard/dark-ships-panel.tsx` - NEW: Dark ship alerts

## Dashboard Integration (Full Scope)

### Step 8: Add Fusion API Endpoints
```python
# admin/server.py
@app.get("/api/fusion/tracks")      # All active fused tracks
@app.get("/api/fusion/dark-ships")  # Flagged dark ships
@app.get("/api/fusion/track/{id}")  # Single track details
```

### Step 9: Add Fused Tracks to Globe
- New layer showing unified tracks (different color from raw sensor data)
- Dark ships highlighted in RED with pulsing effect
- Tooltip showing track details (sensors, confidence, dark ship status)

### Step 10: Add Dark Ships Alert Panel
- Real-time panel showing flagged dark ships
- Shows: track_id, position, confidence, alert_reason, detecting sensors
- Click to center globe on dark ship
- Auto-updates via WebSocket

## Estimated Effort
- Core fusion logic: ~5 files, ~800 lines
- Admin integration: ~100 lines
- Dashboard tracks layer: ~150 lines
- Dark ships panel: ~200 lines
