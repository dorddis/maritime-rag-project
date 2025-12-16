-- ============================================
-- Maritime RAG System - PostgreSQL Schema
-- ============================================
-- Prerequisites: PostgreSQL 17+ with pgvector extension
-- Run: psql -U postgres -d maritime -f setup_db_rag.sql

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- CORE TABLES
-- ============================================

-- Unified Tracks: Synced from Redis fusion layer
-- Contains fused vessel tracks from multiple sensors (AIS, Radar, Satellite, Drone)
CREATE TABLE IF NOT EXISTS unified_tracks (
    track_id VARCHAR(50) PRIMARY KEY,

    -- Position state (fused from multiple sensors)
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    speed_knots DOUBLE PRECISION,
    course DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    position_uncertainty_m DOUBLE PRECISION DEFAULT 1000.0,

    -- Velocity components (for prediction)
    velocity_north_ms DOUBLE PRECISION DEFAULT 0.0,
    velocity_east_ms DOUBLE PRECISION DEFAULT 0.0,

    -- Identity
    identity_source VARCHAR(20), -- 'ais', 'drone', 'unknown'
    mmsi VARCHAR(20),
    ship_name VARCHAR(100),
    vessel_type VARCHAR(50),
    vessel_length_m DOUBLE PRECISION,
    imo VARCHAR(20),

    -- Dark ship detection
    is_dark_ship BOOLEAN DEFAULT FALSE,
    dark_ship_confidence DOUBLE PRECISION DEFAULT 0.0,
    ais_last_seen TIMESTAMPTZ,
    ais_gap_seconds DOUBLE PRECISION,

    -- Sensor contributions (which sensors contributed to this track)
    contributing_sensors TEXT[], -- Array: ['ais', 'radar', 'satellite', 'drone']

    -- Track metadata
    track_status VARCHAR(20) DEFAULT 'tentative', -- tentative, confirmed, coasting, dropped
    track_quality INTEGER DEFAULT 0, -- 0-100 composite score
    correlation_confidence DOUBLE PRECISION DEFAULT 0.0,
    update_count INTEGER DEFAULT 0,

    -- Alert status
    flagged_for_review BOOLEAN DEFAULT FALSE,
    alert_reason TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for unified_tracks
CREATE INDEX IF NOT EXISTS idx_unified_tracks_updated ON unified_tracks(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_unified_tracks_mmsi ON unified_tracks(mmsi) WHERE mmsi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_unified_tracks_ship_name ON unified_tracks(ship_name) WHERE ship_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_unified_tracks_vessel_type ON unified_tracks(vessel_type) WHERE vessel_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_unified_tracks_dark ON unified_tracks(is_dark_ship) WHERE is_dark_ship = TRUE;
CREATE INDEX IF NOT EXISTS idx_unified_tracks_status ON unified_tracks(track_status);
CREATE INDEX IF NOT EXISTS idx_unified_tracks_location ON unified_tracks(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_unified_tracks_speed ON unified_tracks(speed_knots) WHERE speed_knots IS NOT NULL;

-- Dark Ship Events: Point-in-time alerts when vessels go dark
CREATE TABLE IF NOT EXISTS dark_ship_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    track_id VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,

    -- Position at time of alert
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,

    -- Detection details
    confidence DOUBLE PRECISION,
    alert_reason TEXT,
    detected_by TEXT[], -- Sensors that detected this dark ship

    -- Context
    ais_gap_seconds DOUBLE PRECISION,
    speed_at_detection DOUBLE PRECISION,
    heading_at_detection DOUBLE PRECISION,

    -- Metadata
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_dark_event_track FOREIGN KEY (track_id)
        REFERENCES unified_tracks(track_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dark_events_timestamp ON dark_ship_events(event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dark_events_track ON dark_ship_events(track_id);
CREATE INDEX IF NOT EXISTS idx_dark_events_unresolved ON dark_ship_events(resolved) WHERE resolved = FALSE;

-- ============================================
-- VECTOR EMBEDDING TABLES (for Semantic RAG)
-- ============================================

-- Document Embeddings: For semantic search over text documents
-- Stores ship reports, port activity reports, anomaly descriptions
CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Document content
    content TEXT NOT NULL,
    document_type VARCHAR(50) NOT NULL, -- 'ship_report', 'port_report', 'anomaly_alert', 'incident_report'

    -- Metadata (flexible JSONB for different doc types)
    metadata JSONB DEFAULT '{}',
    -- Example metadata:
    -- ship_report: {"ship_name": "X", "mmsi": "Y", "route": "A to B"}
    -- port_report: {"port_name": "Mumbai", "ship_count": 5}
    -- anomaly_alert: {"anomaly_type": "AIS_gap", "severity": "high"}

    -- Vector embedding (Gemini embedding-001 is 768 dimensions)
    embedding vector(768),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity index (IVFFlat for production, can switch to HNSW for smaller datasets)
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector
ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- GIN index for metadata JSONB queries
CREATE INDEX IF NOT EXISTS idx_document_embeddings_metadata ON document_embeddings USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_type ON document_embeddings(document_type);

-- Track History Embeddings: For semantic search over vessel trajectories
-- Stores summarized track segments (e.g., "MARITIME PRIDE traveled from Mumbai to Dubai, went dark for 2 hours")
CREATE TABLE IF NOT EXISTS track_history_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    track_id VARCHAR(50) NOT NULL,

    -- Time window this embedding represents
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,

    -- Textual description of the track segment
    description TEXT NOT NULL,

    -- Vector embedding of the description
    embedding vector(768),

    -- Summary statistics for this window
    metadata JSONB DEFAULT '{}',
    -- Example: {"avg_speed": 15.5, "max_speed": 20.0, "distance_nm": 150,
    --           "sensors_used": ["ais", "radar"], "dark_events": 1}

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_track_history_track FOREIGN KEY (track_id)
        REFERENCES unified_tracks(track_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_track_history_vector
ON track_history_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX IF NOT EXISTS idx_track_history_track ON track_history_embeddings(track_id);
CREATE INDEX IF NOT EXISTS idx_track_history_time ON track_history_embeddings(window_start DESC);

-- Anomaly Embeddings: For semantic search over anomaly descriptions
CREATE TABLE IF NOT EXISTS anomaly_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Link to source (can be unified_track or dark_ship_event)
    source_type VARCHAR(50) NOT NULL, -- 'dark_ship', 'speed_anomaly', 'route_deviation', etc.
    source_id VARCHAR(100), -- Reference to source record

    -- Anomaly description for embedding
    description TEXT NOT NULL,

    -- Vector embedding
    embedding vector(768),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_embeddings_vector
ON anomaly_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX IF NOT EXISTS idx_anomaly_embeddings_source ON anomaly_embeddings(source_type, source_id);

-- ============================================
-- HELPER VIEWS
-- ============================================

-- Latest position per vessel (for quick lookups)
CREATE OR REPLACE VIEW latest_unified_tracks AS
SELECT DISTINCT ON (mmsi)
    track_id,
    mmsi,
    ship_name,
    vessel_type,
    latitude,
    longitude,
    speed_knots,
    course,
    heading,
    is_dark_ship,
    dark_ship_confidence,
    contributing_sensors,
    track_status,
    track_quality,
    updated_at
FROM unified_tracks
WHERE mmsi IS NOT NULL
  AND track_status NOT IN ('dropped')
ORDER BY mmsi, updated_at DESC;

-- Active dark ships (currently flagged, not resolved)
CREATE OR REPLACE VIEW active_dark_ships AS
SELECT
    ut.track_id,
    ut.mmsi,
    ut.ship_name,
    ut.vessel_type,
    ut.latitude,
    ut.longitude,
    ut.speed_knots,
    ut.dark_ship_confidence,
    ut.ais_gap_seconds,
    ut.contributing_sensors,
    ut.updated_at
FROM unified_tracks ut
WHERE ut.is_dark_ship = TRUE
  AND ut.track_status NOT IN ('dropped');

-- Recent dark ship events (last 24 hours)
CREATE OR REPLACE VIEW recent_dark_events AS
SELECT
    de.id,
    de.track_id,
    ut.ship_name,
    ut.mmsi,
    de.latitude,
    de.longitude,
    de.confidence,
    de.alert_reason,
    de.detected_by,
    de.ais_gap_seconds,
    de.event_timestamp,
    de.resolved
FROM dark_ship_events de
JOIN unified_tracks ut ON de.track_id = ut.track_id
WHERE de.event_timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY de.event_timestamp DESC;

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Haversine distance calculation (returns kilometers)
CREATE OR REPLACE FUNCTION haversine_distance(
    lat1 DOUBLE PRECISION,
    lon1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION,
    lon2 DOUBLE PRECISION
) RETURNS DOUBLE PRECISION AS $$
DECLARE
    r DOUBLE PRECISION := 6371.0; -- Earth radius in km
    dlat DOUBLE PRECISION;
    dlon DOUBLE PRECISION;
    a DOUBLE PRECISION;
    c DOUBLE PRECISION;
BEGIN
    dlat := radians(lat2 - lat1);
    dlon := radians(lon2 - lon1);
    a := sin(dlat/2) * sin(dlat/2) +
         cos(radians(lat1)) * cos(radians(lat2)) *
         sin(dlon/2) * sin(dlon/2);
    c := 2 * atan2(sqrt(a), sqrt(1-a));
    RETURN r * c;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Find ships within radius of a point (returns tracks with distance)
CREATE OR REPLACE FUNCTION find_ships_near_point(
    center_lat DOUBLE PRECISION,
    center_lon DOUBLE PRECISION,
    radius_km DOUBLE PRECISION,
    max_results INTEGER DEFAULT 100
) RETURNS TABLE (
    track_id VARCHAR(50),
    mmsi VARCHAR(20),
    ship_name VARCHAR(100),
    vessel_type VARCHAR(50),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    speed_knots DOUBLE PRECISION,
    distance_km DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ut.track_id,
        ut.mmsi,
        ut.ship_name,
        ut.vessel_type,
        ut.latitude,
        ut.longitude,
        ut.speed_knots,
        haversine_distance(center_lat, center_lon, ut.latitude, ut.longitude) AS distance_km
    FROM unified_tracks ut
    WHERE ut.track_status NOT IN ('dropped')
      AND haversine_distance(center_lat, center_lon, ut.latitude, ut.longitude) <= radius_km
    ORDER BY distance_km
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Search documents by vector similarity
CREATE OR REPLACE FUNCTION search_documents_by_similarity(
    query_embedding vector(768),
    match_count INTEGER DEFAULT 5,
    doc_type VARCHAR DEFAULT NULL,
    similarity_threshold DOUBLE PRECISION DEFAULT 0.5
) RETURNS TABLE (
    id UUID,
    content TEXT,
    document_type VARCHAR(50),
    metadata JSONB,
    similarity DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.content,
        d.document_type,
        d.metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM document_embeddings d
    WHERE (doc_type IS NULL OR d.document_type = doc_type)
      AND 1 - (d.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Search track histories by vector similarity
CREATE OR REPLACE FUNCTION search_track_history_by_similarity(
    query_embedding vector(768),
    match_count INTEGER DEFAULT 5,
    time_start TIMESTAMPTZ DEFAULT NULL,
    time_end TIMESTAMPTZ DEFAULT NULL
) RETURNS TABLE (
    id UUID,
    track_id VARCHAR(50),
    description TEXT,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    metadata JSONB,
    similarity DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        th.id,
        th.track_id,
        th.description,
        th.window_start,
        th.window_end,
        th.metadata,
        1 - (th.embedding <=> query_embedding) AS similarity
    FROM track_history_embeddings th
    WHERE (time_start IS NULL OR th.window_start >= time_start)
      AND (time_end IS NULL OR th.window_end <= time_end)
    ORDER BY th.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- KNOWN PORT LOCATIONS (for geo queries)
-- ============================================

CREATE TABLE IF NOT EXISTS ports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    country VARCHAR(50),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    port_type VARCHAR(50) -- 'major', 'minor', 'fishing', 'military'
);

-- Seed common Indian Ocean ports
INSERT INTO ports (name, country, latitude, longitude, port_type) VALUES
    ('Mumbai', 'India', 18.9388, 72.8354, 'major'),
    ('Chennai', 'India', 13.0827, 80.2707, 'major'),
    ('Kochi', 'India', 9.9312, 76.2673, 'major'),
    ('Visakhapatnam', 'India', 17.6868, 83.2185, 'major'),
    ('Kandla', 'India', 23.0333, 70.2167, 'major'),
    ('Colombo', 'Sri Lanka', 6.9271, 79.8612, 'major'),
    ('Singapore', 'Singapore', 1.3521, 103.8198, 'major'),
    ('Dubai', 'UAE', 25.2048, 55.2708, 'major'),
    ('Karachi', 'Pakistan', 24.8607, 67.0011, 'major'),
    ('Chittagong', 'Bangladesh', 22.3569, 91.7832, 'major')
ON CONFLICT (name) DO NOTHING;

-- Function to find ships near a named port
CREATE OR REPLACE FUNCTION find_ships_near_port(
    port_name_param VARCHAR,
    radius_km DOUBLE PRECISION DEFAULT 50.0,
    max_results INTEGER DEFAULT 100
) RETURNS TABLE (
    track_id VARCHAR(50),
    mmsi VARCHAR(20),
    ship_name VARCHAR(100),
    vessel_type VARCHAR(50),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    speed_knots DOUBLE PRECISION,
    distance_km DOUBLE PRECISION,
    port VARCHAR(100)
) AS $$
DECLARE
    port_lat DOUBLE PRECISION;
    port_lon DOUBLE PRECISION;
BEGIN
    -- Get port coordinates
    SELECT p.latitude, p.longitude INTO port_lat, port_lon
    FROM ports p
    WHERE LOWER(p.name) = LOWER(port_name_param);

    IF port_lat IS NULL THEN
        RAISE EXCEPTION 'Port not found: %', port_name_param;
    END IF;

    RETURN QUERY
    SELECT
        r.track_id,
        r.mmsi,
        r.ship_name,
        r.vessel_type,
        r.latitude,
        r.longitude,
        r.speed_knots,
        r.distance_km,
        port_name_param AS port
    FROM find_ships_near_point(port_lat, port_lon, radius_km, max_results) r;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- SYNC METADATA TABLE
-- ============================================

-- Track sync state for Redis → PostgreSQL sync service
CREATE TABLE IF NOT EXISTS sync_state (
    id SERIAL PRIMARY KEY,
    stream_name VARCHAR(100) NOT NULL UNIQUE,
    last_message_id VARCHAR(50) DEFAULT '0-0',
    last_sync_at TIMESTAMPTZ DEFAULT NOW(),
    messages_synced BIGINT DEFAULT 0
);

-- Initialize sync state for fusion streams
INSERT INTO sync_state (stream_name) VALUES
    ('fusion:tracks'),
    ('fusion:dark_ships')
ON CONFLICT (stream_name) DO NOTHING;

-- ============================================
-- COMMENTS FOR SQL AGENT CONTEXT
-- ============================================

COMMENT ON TABLE unified_tracks IS 'Fused vessel tracks from multiple sensors (AIS, Radar, Satellite, Drone). Updated every 0.5s from Redis fusion layer.';
COMMENT ON COLUMN unified_tracks.is_dark_ship IS 'True if vessel has AIS disabled but is detected by other sensors (radar, satellite, drone).';
COMMENT ON COLUMN unified_tracks.dark_ship_confidence IS 'Confidence score 0-1 that this is a dark ship. Higher = more suspicious.';
COMMENT ON COLUMN unified_tracks.contributing_sensors IS 'Array of sensor types that contributed to this track: ais, radar, satellite, drone.';
COMMENT ON COLUMN unified_tracks.track_quality IS 'Composite quality score 0-100. Higher = better track with more sensor coverage.';

COMMENT ON TABLE dark_ship_events IS 'Point-in-time alerts when vessels go dark (AIS disabled while still being tracked by other sensors).';
COMMENT ON TABLE document_embeddings IS 'Vector embeddings for semantic search. Contains ship reports, port activity, anomaly descriptions.';
COMMENT ON TABLE track_history_embeddings IS 'Vector embeddings summarizing vessel trajectory segments for semantic search.';

COMMENT ON FUNCTION haversine_distance IS 'Calculate great-circle distance between two lat/lon points in kilometers.';
COMMENT ON FUNCTION find_ships_near_point IS 'Find all ships within radius_km of a lat/lon point.';
COMMENT ON FUNCTION find_ships_near_port IS 'Find all ships within radius_km of a named port (Mumbai, Chennai, etc).';
COMMENT ON FUNCTION search_documents_by_similarity IS 'Semantic search over document embeddings using cosine similarity.';

-- ============================================
-- GRANT PERMISSIONS (adjust user as needed)
-- ============================================

-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maritime_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maritime_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO maritime_user;
