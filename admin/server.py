"""
Admin Dashboard Server

FastAPI server for controlling ingesters and monitoring data flow.

Endpoints:
- GET  /api/ingesters           - List all ingesters with status
- POST /api/ingesters/{name}/start - Start an ingester
- POST /api/ingesters/{name}/stop  - Stop an ingester
- GET  /api/streams/stats       - Get Redis stream statistics
- GET  /                        - Simple HTML dashboard
"""

import asyncio
import logging
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

from admin.ingester_manager import get_manager, INGESTERS

# Import RAG router
try:
    from api.rag_endpoints import router as rag_router, cleanup_rag
    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    rag_router = None
    cleanup_rag = None
    print(f"RAG module not available: {e}")

# Import Chat router
try:
    from api.chat_endpoints import router as chat_router
    CHAT_AVAILABLE = True
except ImportError as e:
    CHAT_AVAILABLE = False
    chat_router = None
    print(f"Chat module not available: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - ADMIN - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis client (optional)
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global redis_client

    # Try to connect to Redis (decode_responses=True for string handling)
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}")
        redis_client = None

    yield

    # Cleanup
    manager = get_manager()
    manager.stop_all()

    if redis_client:
        await redis_client.close()

    # Cleanup RAG resources
    if RAG_AVAILABLE and cleanup_rag:
        await cleanup_rag()


app = FastAPI(
    title="Maritime Ship Tracking API",
    description="Control panel for maritime data ingesters and hybrid RAG queries",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include RAG router
if RAG_AVAILABLE and rag_router:
    app.include_router(rag_router)
    logger.info("RAG endpoints mounted at /api/rag")

# Include Chat router
if CHAT_AVAILABLE and chat_router:
    app.include_router(chat_router)
    logger.info("Chat endpoints mounted at /api/rag/chat")


class StartRequest(BaseModel):
    """Request body for starting an ingester"""
    args: Optional[Dict[str, str]] = None


# ============ API Endpoints ============

@app.get("/api/ingesters")
async def list_ingesters():
    """List all available ingesters with their current status"""
    manager = get_manager()
    return manager.get_all_status()


@app.get("/api/ingesters/{name}")
async def get_ingester(name: str):
    """Get status of a specific ingester"""
    if name not in INGESTERS:
        raise HTTPException(status_code=404, detail=f"Unknown ingester: {name}")

    manager = get_manager()
    return manager.get_status(name)


@app.post("/api/ingesters/{name}/start")
async def start_ingester(name: str, request: StartRequest = None):
    """Start an ingester"""
    if name not in INGESTERS:
        raise HTTPException(status_code=404, detail=f"Unknown ingester: {name}")

    manager = get_manager()
    args = request.args if request else None
    result = manager.start(name, args)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.post("/api/ingesters/{name}/stop")
async def stop_ingester(name: str):
    """Stop an ingester"""
    if name not in INGESTERS:
        raise HTTPException(status_code=404, detail=f"Unknown ingester: {name}")

    manager = get_manager()
    result = manager.stop(name)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.post("/api/ingesters/stop-all")
async def stop_all_ingesters():
    """Stop all running ingesters"""
    manager = get_manager()
    return manager.stop_all()


@app.get("/api/streams/stats")
async def get_stream_stats():
    """Get Redis stream statistics"""
    if redis_client is None:
        return {"error": "Redis not connected", "streams": {}}

    streams = {
        "ais:positions": 0,
        "radar:contacts": 0,
        "satellite:detections": 0,
        "drone:detections": 0,
        "fusion:tracks": 0,
        "fusion:dark_ships": 0,
    }

    for stream in streams:
        try:
            info = await redis_client.xinfo_stream(stream)
            streams[stream] = info.get("length", 0)
        except Exception:
            streams[stream] = 0

    return {"streams": streams, "redis_connected": True}


@app.get("/api/fleet/metadata")
async def get_fleet_metadata():
    """Get fleet metadata (total ships, dark ships count, etc.)"""
    if redis_client is None:
        return {"error": "Redis not connected"}

    try:
        metadata = await redis_client.hgetall("maritime:fleet:metadata")
        return {
            "total_ships": int(metadata.get("total_ships", 0)),
            "dark_ships": int(metadata.get("dark_ships", 0)),
            "initialized_at": metadata.get("initialized_at", ""),
            "last_update": metadata.get("last_update", ""),
            "bounds": {
                "lat_min": float(metadata.get("lat_min", 0)),
                "lat_max": float(metadata.get("lat_max", 0)),
                "lon_min": float(metadata.get("lon_min", 0)),
                "lon_max": float(metadata.get("lon_max", 0)),
            }
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/fleet/ships")
async def get_fleet_ships():
    """
    Get all ships for globe visualization.
    Returns lightweight ship data optimized for rendering.
    """
    if redis_client is None:
        logger.error("Redis client is None!")
        return {"error": "Redis not connected", "ships": []}

    try:
        # Get all ship MMSIs
        mmsis = await redis_client.smembers("maritime:fleet")
        logger.info(f"Found {len(mmsis) if mmsis else 0} ships in Redis fleet set")
        if not mmsis:
            return {"ships": [], "count": 0, "debug": "No MMSIs in maritime:fleet"}

        # Fetch all ships in parallel
        pipeline = redis_client.pipeline()
        for mmsi in mmsis:
            pipeline.hgetall(f"maritime:ship:{mmsi}")

        results = await pipeline.execute()

        ships = []
        for data in results:
            if data:
                ships.append({
                    "mmsi": data.get("mmsi", ""),
                    "name": data.get("name", ""),
                    "type": data.get("vessel_type", "cargo"),
                    "lat": float(data.get("latitude", 0)),
                    "lng": float(data.get("longitude", 0)),
                    "speed": float(data.get("speed", 0)),
                    "course": float(data.get("course", 0)),
                    "ais": data.get("ais_enabled", "True") == "True",
                })

        return {
            "ships": ships,
            "count": len(ships),
            "dark_count": len([s for s in ships if not s["ais"]]),
        }
    except Exception as e:
        return {"error": str(e), "ships": []}


@app.get("/api/streams/{stream}/recent")
async def get_recent_messages(stream: str, count: int = 10):
    """Get recent messages from a stream"""
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")

    try:
        messages = await redis_client.xrevrange(stream, count=count)
        return {
            "stream": stream,
            "count": len(messages),
            "messages": [
                {"id": msg[0], "data": msg[1]}
                for msg in messages
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ingesters/{name}/logs")
async def get_ingester_logs(name: str, lines: int = 50):
    """Get recent logs from an ingester"""
    if name not in INGESTERS:
        raise HTTPException(status_code=404, detail=f"Unknown ingester: {name}")

    manager = get_manager()
    return {"name": name, "logs": manager.get_logs(name, lines)}


@app.get("/api/logs")
async def get_all_logs():
    """Get logs from all ingesters"""
    manager = get_manager()
    return manager.get_all_logs()


# ============ Fusion API Endpoints ============

@app.get("/api/fusion/status")
async def get_fusion_status():
    """Get fusion ingester status from Redis"""
    if redis_client is None:
        return {"error": "Redis not connected"}

    try:
        status = await redis_client.hgetall("fusion:status")
        if not status:
            return {
                "running": False,
                "active_tracks": 0,
                "dark_ships": 0,
                "message": "Fusion ingester not running"
            }
        return status
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/fusion/tracks")
async def get_fusion_tracks():
    """
    Get all active fused tracks.
    Returns unified tracks with multi-sensor correlation.
    """
    if redis_client is None:
        return {"error": "Redis not connected", "tracks": []}

    try:
        # Get all active track IDs
        track_ids = await redis_client.smembers("fusion:active_tracks")
        if not track_ids:
            return {"tracks": [], "count": 0}

        # Fetch all tracks in parallel
        pipeline = redis_client.pipeline()
        for track_id in track_ids:
            pipeline.hgetall(f"fusion:track:{track_id}")

        results = await pipeline.execute()

        tracks = []
        for data in results:
            if data:
                tracks.append({
                    "track_id": data.get("track_id", ""),
                    "latitude": float(data.get("latitude", 0)),
                    "longitude": float(data.get("longitude", 0)),
                    "speed_knots": float(data.get("speed_knots", 0)) if data.get("speed_knots") else None,
                    "course": float(data.get("course", 0)) if data.get("course") else None,
                    "mmsi": data.get("mmsi"),
                    "ship_name": data.get("ship_name"),
                    "vessel_type": data.get("vessel_type"),
                    "status": data.get("status", "UNKNOWN"),
                    "is_dark_ship": data.get("is_dark_ship", "False") == "True",
                    "dark_ship_confidence": float(data.get("dark_ship_confidence", 0)),
                    "contributing_sensors": data.get("contributing_sensors", "").split(",") if data.get("contributing_sensors") else [],
                    "track_quality": int(data.get("track_quality", 0)),
                    "position_uncertainty_m": float(data.get("position_uncertainty_m", 0)),
                    "updated_at": data.get("updated_at", ""),
                })

        return {
            "tracks": tracks,
            "count": len(tracks),
            "dark_count": len([t for t in tracks if t["is_dark_ship"]]),
        }
    except Exception as e:
        logger.error(f"Error fetching fusion tracks: {e}")
        return {"error": str(e), "tracks": []}


@app.get("/api/fusion/dark-ships")
async def get_dark_ships():
    """
    Get all flagged dark ships.
    Returns ships with AIS turned off or never had AIS.
    """
    if redis_client is None:
        return {"error": "Redis not connected", "dark_ships": []}

    try:
        # Get recent dark ship alerts from stream
        alerts = await redis_client.xrevrange("fusion:dark_ships", count=100)

        dark_ships = []
        for msg_id, data in alerts:
            dark_ships.append({
                "alert_id": msg_id,
                "track_id": data.get("track_id", ""),
                "latitude": float(data.get("latitude", 0)),
                "longitude": float(data.get("longitude", 0)),
                "confidence": float(data.get("confidence", 0)),
                "alert_reason": data.get("alert_reason", ""),
                "detected_by": data.get("detected_by", "").split(",") if data.get("detected_by") else [],
                "timestamp": data.get("timestamp", ""),
            })

        return {
            "dark_ships": dark_ships,
            "count": len(dark_ships),
        }
    except Exception as e:
        logger.error(f"Error fetching dark ships: {e}")
        return {"error": str(e), "dark_ships": []}


@app.get("/api/fusion/track/{track_id}")
async def get_fusion_track(track_id: str):
    """Get detailed information about a specific fused track"""
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")

    try:
        data = await redis_client.hgetall(f"fusion:track:{track_id}")
        if not data:
            raise HTTPException(status_code=404, detail=f"Track not found: {track_id}")

        return {
            "track_id": data.get("track_id", ""),
            "latitude": float(data.get("latitude", 0)),
            "longitude": float(data.get("longitude", 0)),
            "speed_knots": float(data.get("speed_knots", 0)) if data.get("speed_knots") else None,
            "course": float(data.get("course", 0)) if data.get("course") else None,
            "velocity_north_ms": float(data.get("velocity_north_ms", 0)),
            "velocity_east_ms": float(data.get("velocity_east_ms", 0)),
            "mmsi": data.get("mmsi"),
            "ship_name": data.get("ship_name"),
            "vessel_type": data.get("vessel_type"),
            "vessel_length_m": float(data.get("vessel_length_m", 0)) if data.get("vessel_length_m") else None,
            "status": data.get("status", "UNKNOWN"),
            "identity_source": data.get("identity_source", "UNKNOWN"),
            "is_dark_ship": data.get("is_dark_ship", "False") == "True",
            "dark_ship_confidence": float(data.get("dark_ship_confidence", 0)),
            "alert_reason": data.get("alert_reason"),
            "ais_gap_seconds": float(data.get("ais_gap_seconds", 0)) if data.get("ais_gap_seconds") else None,
            "contributing_sensors": data.get("contributing_sensors", "").split(",") if data.get("contributing_sensors") else [],
            "track_quality": int(data.get("track_quality", 0)),
            "position_uncertainty_m": float(data.get("position_uncertainty_m", 0)),
            "correlation_confidence": float(data.get("correlation_confidence", 0)),
            "update_count": int(data.get("update_count", 0)),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ WebSocket Endpoint ============

# Track connected WebSocket clients
websocket_clients: list[WebSocket] = []


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Sends JSON messages containing:
    - status: Current status of all ingesters
    - logs: Recent logs from all running ingesters
    - streams: Redis stream statistics (if connected)
    """
    await websocket.accept()
    websocket_clients.append(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(websocket_clients)}")

    try:
        manager = get_manager()

        while True:
            # Gather current state
            status = manager.get_all_status()
            logs = manager.get_all_logs()

            # Get stream stats if Redis is connected
            streams = {}
            fleet = {"total_ships": 0, "dark_ships": 0}
            fusion = {"running": False, "active_tracks": 0, "dark_ships": 0}
            if redis_client:
                for stream_name in ["ais:positions", "radar:contacts", "satellite:detections", "drone:detections", "fusion:tracks", "fusion:dark_ships"]:
                    try:
                        info = await redis_client.xinfo_stream(stream_name)
                        streams[stream_name] = info.get("length", 0)
                    except Exception:
                        streams[stream_name] = 0

                # Get fleet metadata
                try:
                    metadata = await redis_client.hgetall("maritime:fleet:metadata")
                    fleet = {
                        "total_ships": int(metadata.get("total_ships", 0)),
                        "dark_ships": int(metadata.get("dark_ships", 0)),
                    }
                except Exception:
                    pass

                # Get fusion status
                try:
                    fusion_status = await redis_client.hgetall("fusion:status")
                    if fusion_status:
                        fusion = {
                            "running": fusion_status.get("running", "False") == "True",
                            "active_tracks": int(fusion_status.get("active_tracks", 0)),
                            "dark_ships": int(fusion_status.get("dark_ships", 0)),
                            "correlations_made": int(fusion_status.get("correlations_made", 0)),
                        }
                except Exception:
                    pass

            # Send update to client
            await websocket.send_json({
                "type": "update",
                "status": status,
                "logs": logs,
                "streams": streams,
                "fleet": fleet,
                "fusion": fusion,
                "redis_connected": redis_client is not None
            })

            # Wait before next update (100ms for responsive logs)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in websocket_clients:
            websocket_clients.remove(websocket)


# ============ HTML Dashboard ============

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Maritime Unified Simulation Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }
        h1 {
            color: #00d9ff;
            margin-bottom: 5px;
            font-size: 24px;
        }
        h2 {
            color: #00d9ff;
            margin: 20px 0 15px 0;
            font-size: 16px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .subtitle {
            color: #888;
            font-size: 13px;
            margin-bottom: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .fleet-banner {
            background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #00d9ff;
            display: flex;
            justify-content: space-around;
            text-align: center;
        }
        .fleet-stat {
            padding: 10px;
        }
        .fleet-stat .value {
            font-size: 36px;
            font-weight: bold;
            color: #00d9ff;
        }
        .fleet-stat .label {
            font-size: 12px;
            color: #888;
            text-transform: uppercase;
        }
        .fleet-stat.dark .value {
            color: #ff5252;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #0f3460;
        }
        .card.world {
            border-color: #feca57;
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        }
        .card h3 {
            color: #00d9ff;
            margin-bottom: 10px;
            text-transform: uppercase;
            font-size: 14px;
            letter-spacing: 1px;
        }
        .card.world h3 {
            color: #feca57;
        }
        .card p {
            color: #aaa;
            font-size: 12px;
            margin-bottom: 15px;
            line-height: 1.4;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 15px;
        }
        .status.running { background: #00c853; color: #000; }
        .status.stopped { background: #ff5252; color: #fff; }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: bold;
            transition: all 0.2s;
        }
        .btn-start {
            background: #00d9ff;
            color: #000;
        }
        .btn-start:hover { background: #00b8d4; }
        .btn-stop {
            background: #ff5252;
            color: #fff;
        }
        .btn-stop:hover { background: #ff1744; }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .stats {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #0f3460;
        }
        .stats h3 {
            color: #00d9ff;
            margin-bottom: 15px;
            font-size: 14px;
        }
        .stat-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #0f3460;
            font-size: 13px;
        }
        .stat-row:last-child { border: none; }
        .stat-value {
            color: #00d9ff;
            font-weight: bold;
        }
        .refresh-btn {
            background: #0f3460;
            color: #00d9ff;
            padding: 8px 16px;
            border: 1px solid #00d9ff;
            border-radius: 6px;
            cursor: pointer;
            margin-left: 10px;
        }
        .header {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }
        .sensor-tag {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
        }
        .tag-ais { background: #00d9ff; color: #000; }
        .tag-radar { background: #ff6b6b; color: #fff; }
        .tag-sat { background: #feca57; color: #000; }
        .tag-drone { background: #1dd1a1; color: #000; }
        .tag-world { background: #feca57; color: #000; }
        .sensor-info {
            font-size: 11px;
            color: #666;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #0f3460;
        }
        .sensor-info span {
            display: block;
            margin: 3px 0;
        }
        .dark-indicator {
            color: #ff5252;
        }
        .visible-indicator {
            color: #00c853;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Maritime Unified Simulation</h1>
            <button class="refresh-btn" onclick="refresh()">Refresh</button>
        </div>
        <p class="subtitle">All sensors detect the same ground truth ships. Dark ships are invisible to AIS but visible to other sensors.</p>

        <div class="fleet-banner" id="fleet-banner">
            <div class="fleet-stat">
                <div class="value" id="total-ships">--</div>
                <div class="label">Total Ships</div>
            </div>
            <div class="fleet-stat">
                <div class="value" id="visible-ships">--</div>
                <div class="label">AIS Visible</div>
            </div>
            <div class="fleet-stat dark">
                <div class="value" id="dark-ships">--</div>
                <div class="label">Dark Ships</div>
            </div>
        </div>

        <h2>Ground Truth</h2>
        <div class="grid" id="world-ingester">
            <!-- World Simulator card -->
        </div>

        <h2>Sensor Ingesters</h2>
        <div class="grid" id="sensor-ingesters">
            <!-- Sensor cards -->
        </div>

        <h2>Statistics</h2>
        <div class="stats-grid">
            <div class="stats">
                <h3>Redis Stream Counts</h3>
                <div id="stream-stats">Loading...</div>
            </div>
            <div class="stats">
                <h3>Sensor Capabilities</h3>
                <div class="stat-row">
                    <span>AIS</span>
                    <span><span class="dark-indicator">Cannot</span> see dark ships</span>
                </div>
                <div class="stat-row">
                    <span>Radar</span>
                    <span><span class="visible-indicator">Can</span> see dark ships (no ID)</span>
                </div>
                <div class="stat-row">
                    <span>Satellite</span>
                    <span><span class="visible-indicator">Can</span> see & flag dark ships</span>
                </div>
                <div class="stat-row">
                    <span>Drone</span>
                    <span><span class="visible-indicator">Can</span> see & identify dark ships</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API = '';

        const sensorTags = {
            'world': ['GROUND TRUTH', 'tag-world'],
            'ais': ['NMEA 0183', 'tag-ais'],
            'radar': ['7 STATIONS', 'tag-radar'],
            'satellite': ['4 SATELLITES', 'tag-sat'],
            'drone': ['5 ZONES', 'tag-drone']
        };

        const sensorInfo = {
            'world': 'Ships: 500 | Dark: 5% | Rate: 1Hz',
            'ais': 'Accuracy: ±10m | Packet loss: 5%',
            'radar': 'Range: 45-60nm | Accuracy: ±500m',
            'satellite': 'Accuracy: ±2km | Passes: periodic',
            'drone': 'Accuracy: ±50m | Patrol zones: 5'
        };

        async function fetchIngesters() {
            const res = await fetch(API + '/api/ingesters');
            return res.json();
        }

        async function fetchStats() {
            const res = await fetch(API + '/api/streams/stats');
            return res.json();
        }

        async function fetchFleet() {
            const res = await fetch(API + '/api/fleet/metadata');
            return res.json();
        }

        async function startIngester(name) {
            await fetch(API + '/api/ingesters/' + name + '/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: '{}'
            });
            refresh();
        }

        async function stopIngester(name) {
            await fetch(API + '/api/ingesters/' + name + '/stop', {
                method: 'POST'
            });
            refresh();
        }

        function renderIngesters(data) {
            const worldContainer = document.getElementById('world-ingester');
            const sensorContainer = document.getElementById('sensor-ingesters');
            worldContainer.innerHTML = '';
            sensorContainer.innerHTML = '';

            for (const [name, info] of Object.entries(data)) {
                const running = info.running;
                const [tagText, tagClass] = sensorTags[name] || ['', ''];
                const card = document.createElement('div');
                card.className = name === 'world' ? 'card world' : 'card';
                card.innerHTML = `
                    <h3>${name.toUpperCase()} <span class="sensor-tag ${tagClass}">${tagText}</span></h3>
                    <p>${info.description}</p>
                    <div class="status ${running ? 'running' : 'stopped'}">${running ? 'RUNNING' : 'STOPPED'}</div>
                    <br>
                    ${running
                        ? `<button class="btn btn-stop" onclick="stopIngester('${name}')">Stop</button>`
                        : `<button class="btn btn-start" onclick="startIngester('${name}')">Start</button>`
                    }
                    <div class="sensor-info">${sensorInfo[name] || ''}</div>
                `;

                if (name === 'world') {
                    worldContainer.appendChild(card);
                } else {
                    sensorContainer.appendChild(card);
                }
            }
        }

        function renderStats(data) {
            const container = document.getElementById('stream-stats');
            if (data.error) {
                container.innerHTML = '<p style="color: #ff5252;">' + data.error + '</p>';
                return;
            }

            let html = '';
            for (const [stream, count] of Object.entries(data.streams)) {
                html += `
                    <div class="stat-row">
                        <span>${stream}</span>
                        <span class="stat-value">${count.toLocaleString()}</span>
                    </div>
                `;
            }
            container.innerHTML = html;
        }

        function renderFleet(data) {
            document.getElementById('total-ships').textContent = data.total_ships || '--';
            document.getElementById('dark-ships').textContent = data.dark_ships || '--';
            document.getElementById('visible-ships').textContent =
                (data.total_ships && data.dark_ships) ? (data.total_ships - data.dark_ships) : '--';
        }

        async function refresh() {
            const [ingesters, stats, fleet] = await Promise.all([
                fetchIngesters(),
                fetchStats(),
                fetchFleet()
            ]);
            renderIngesters(ingesters);
            renderStats(stats);
            renderFleet(fleet);
        }

        // Initial load
        refresh();

        // Auto-refresh every 3 seconds
        setInterval(refresh, 3000);
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the admin dashboard"""
    return DASHBOARD_HTML


# ============ Run Server ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
