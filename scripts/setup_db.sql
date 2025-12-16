-- Maritime System Database Schema
-- For Neon PostgreSQL (TimescaleDB features not available, using standard PostgreSQL)

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- AIS Positions Table (main time-series data)
CREATE TABLE IF NOT EXISTS ais_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    speed_knots DOUBLE PRECISION,
    course DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    nav_status VARCHAR(50),
    vessel_name VARCHAR(100),
    vessel_type INTEGER,
    destination VARCHAR(100),
    eta TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_ais_timestamp ON ais_positions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ais_mmsi ON ais_positions(mmsi);
CREATE INDEX IF NOT EXISTS idx_ais_location ON ais_positions(latitude, longitude);

-- Weather Observations Table
CREATE TABLE IF NOT EXISTS weather_observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    temperature_c DOUBLE PRECISION,
    wind_speed_knots DOUBLE PRECISION,
    wind_direction DOUBLE PRECISION,
    weather_code INTEGER,
    source VARCHAR(100),
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather_observations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_weather_location ON weather_observations(latitude, longitude);

-- Satellite Detections Table
CREATE TABLE IF NOT EXISTS satellite_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION,
    vessel_length_m DOUBLE PRECISION,
    source_satellite VARCHAR(50),
    matched_mmsi VARCHAR(20),
    is_dark_ship BOOLEAN DEFAULT FALSE,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_satellite_timestamp ON satellite_detections(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_satellite_detection_id ON satellite_detections(detection_id);

-- Anomaly Alerts Table
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    mmsi VARCHAR(20),
    description TEXT,
    metadata JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON anomaly_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON anomaly_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON anomaly_alerts(severity);

-- Vessels Table (master data)
CREATE TABLE IF NOT EXISTS vessels (
    mmsi VARCHAR(20) PRIMARY KEY,
    imo VARCHAR(20),
    name VARCHAR(100),
    callsign VARCHAR(20),
    vessel_type INTEGER,
    length_m DOUBLE PRECISION,
    width_m DOUBLE PRECISION,
    flag_country VARCHAR(50),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    total_positions INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_vessels_name ON vessels(name);

-- View for latest position per vessel
CREATE OR REPLACE VIEW latest_positions AS
SELECT DISTINCT ON (mmsi)
    mmsi,
    timestamp,
    latitude,
    longitude,
    speed_knots,
    course,
    heading,
    vessel_name
FROM ais_positions
ORDER BY mmsi, timestamp DESC;

-- Function to update vessel stats
CREATE OR REPLACE FUNCTION update_vessel_stats()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO vessels (mmsi, name, vessel_type, last_seen, total_positions)
    VALUES (NEW.mmsi, NEW.vessel_name, NEW.vessel_type, NEW.timestamp, 1)
    ON CONFLICT (mmsi) DO UPDATE SET
        name = COALESCE(EXCLUDED.name, vessels.name),
        vessel_type = COALESCE(EXCLUDED.vessel_type, vessels.vessel_type),
        last_seen = EXCLUDED.last_seen,
        total_positions = vessels.total_positions + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update vessel stats
DROP TRIGGER IF EXISTS trigger_update_vessel_stats ON ais_positions;
CREATE TRIGGER trigger_update_vessel_stats
    AFTER INSERT ON ais_positions
    FOR EACH ROW
    EXECUTE FUNCTION update_vessel_stats();

-- Sample query: Ships in a bounding box
-- SELECT * FROM latest_positions
-- WHERE latitude BETWEEN 8 AND 22
-- AND longitude BETWEEN 68 AND 95;

-- Sample query: Speed anomalies (>25 knots for cargo ships)
-- SELECT * FROM ais_positions
-- WHERE speed_knots > 25
-- AND vessel_type BETWEEN 70 AND 79
-- ORDER BY timestamp DESC LIMIT 100;
