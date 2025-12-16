"""
PostgreSQL Setup Script

Creates the maritime database and runs the RAG schema.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_database(host="localhost", port=5432, user="postgres", password="password"):
    """Create the maritime database if it doesn't exist."""
    print(f"Connecting to PostgreSQL at {host}:{port}...")

    try:
        # Connect to default postgres database
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        print("Connected successfully!")

        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'maritime'")
        exists = cursor.fetchone()

        if exists:
            print("Database 'maritime' already exists.")
        else:
            print("Creating database 'maritime'...")
            cursor.execute("CREATE DATABASE maritime")
            print("Database created!")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def run_schema(host="localhost", port=5432, user="postgres", password="password"):
    """Run the RAG schema SQL file, handling pgvector gracefully."""
    print("Setting up schema...")

    try:
        # Connect to maritime database
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="maritime"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Step 1: Enable uuid-ossp extension
        print("  Enabling uuid-ossp extension...")
        cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        # Step 2: Try to enable pgvector
        print("  Checking pgvector extension...")
        pgvector_available = False
        try:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
            pgvector_available = True
            print("  pgvector: ENABLED")
        except Exception as e:
            print(f"  pgvector: NOT AVAILABLE (will skip vector tables)")
            print(f"    Reason: {e}")

        # Step 3: Create core tables (no vector dependency)
        print("  Creating unified_tracks table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unified_tracks (
                track_id VARCHAR(50) PRIMARY KEY,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                speed_knots DOUBLE PRECISION,
                course DOUBLE PRECISION,
                heading DOUBLE PRECISION,
                position_uncertainty_m DOUBLE PRECISION DEFAULT 1000.0,
                velocity_north_ms DOUBLE PRECISION DEFAULT 0.0,
                velocity_east_ms DOUBLE PRECISION DEFAULT 0.0,
                identity_source VARCHAR(20),
                mmsi VARCHAR(20),
                ship_name VARCHAR(100),
                vessel_type VARCHAR(50),
                vessel_length_m DOUBLE PRECISION,
                imo VARCHAR(20),
                is_dark_ship BOOLEAN DEFAULT FALSE,
                dark_ship_confidence DOUBLE PRECISION DEFAULT 0.0,
                ais_last_seen TIMESTAMPTZ,
                ais_gap_seconds DOUBLE PRECISION,
                contributing_sensors TEXT[],
                track_status VARCHAR(20) DEFAULT 'tentative',
                track_quality INTEGER DEFAULT 0,
                correlation_confidence DOUBLE PRECISION DEFAULT 0.0,
                update_count INTEGER DEFAULT 0,
                flagged_for_review BOOLEAN DEFAULT FALSE,
                alert_reason TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                last_synced_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Create indexes for unified_tracks
        print("  Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_updated ON unified_tracks(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_mmsi ON unified_tracks(mmsi) WHERE mmsi IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_ship_name ON unified_tracks(ship_name) WHERE ship_name IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_vessel_type ON unified_tracks(vessel_type) WHERE vessel_type IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_dark ON unified_tracks(is_dark_ship) WHERE is_dark_ship = TRUE",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_status ON unified_tracks(track_status)",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_location ON unified_tracks(latitude, longitude)",
            "CREATE INDEX IF NOT EXISTS idx_unified_tracks_speed ON unified_tracks(speed_knots) WHERE speed_knots IS NOT NULL",
        ]
        for idx in indexes:
            cursor.execute(idx)

        # Create dark_ship_events table
        print("  Creating dark_ship_events table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dark_ship_events (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                track_id VARCHAR(50) NOT NULL,
                event_timestamp TIMESTAMPTZ NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                confidence DOUBLE PRECISION,
                alert_reason TEXT,
                detected_by TEXT[],
                ais_gap_seconds DOUBLE PRECISION,
                speed_at_detection DOUBLE PRECISION,
                heading_at_detection DOUBLE PRECISION,
                acknowledged BOOLEAN DEFAULT FALSE,
                resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dark_events_timestamp ON dark_ship_events(event_timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dark_events_track ON dark_ship_events(track_id)")

        # Create ports table
        print("  Creating ports table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ports (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                country VARCHAR(50),
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                port_type VARCHAR(50)
            )
        """)

        # Seed ports
        cursor.execute("""
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
            ON CONFLICT (name) DO NOTHING
        """)

        # Create sync_state table
        print("  Creating sync_state table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                id SERIAL PRIMARY KEY,
                stream_name VARCHAR(100) NOT NULL UNIQUE,
                last_message_id VARCHAR(50) DEFAULT '0-0',
                last_sync_at TIMESTAMPTZ DEFAULT NOW(),
                messages_synced BIGINT DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO sync_state (stream_name) VALUES
                ('fusion:tracks'),
                ('fusion:dark_ships')
            ON CONFLICT (stream_name) DO NOTHING
        """)

        # Create haversine function
        print("  Creating helper functions...")
        cursor.execute("""
            CREATE OR REPLACE FUNCTION haversine_distance(
                lat1 DOUBLE PRECISION,
                lon1 DOUBLE PRECISION,
                lat2 DOUBLE PRECISION,
                lon2 DOUBLE PRECISION
            ) RETURNS DOUBLE PRECISION AS $$
            DECLARE
                r DOUBLE PRECISION := 6371.0;
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
            $$ LANGUAGE plpgsql IMMUTABLE
        """)

        # Create find_ships_near_point function
        cursor.execute("""
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
            $$ LANGUAGE plpgsql
        """)

        # Create find_ships_near_port function
        cursor.execute("""
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
            $$ LANGUAGE plpgsql
        """)

        # Create views
        print("  Creating views...")
        cursor.execute("""
            CREATE OR REPLACE VIEW latest_unified_tracks AS
            SELECT DISTINCT ON (mmsi)
                track_id, mmsi, ship_name, vessel_type,
                latitude, longitude, speed_knots, course, heading,
                is_dark_ship, dark_ship_confidence, contributing_sensors,
                track_status, track_quality, updated_at
            FROM unified_tracks
            WHERE mmsi IS NOT NULL AND track_status NOT IN ('dropped')
            ORDER BY mmsi, updated_at DESC
        """)

        cursor.execute("""
            CREATE OR REPLACE VIEW active_dark_ships AS
            SELECT
                track_id, mmsi, ship_name, vessel_type,
                latitude, longitude, speed_knots,
                dark_ship_confidence, ais_gap_seconds,
                contributing_sensors, updated_at
            FROM unified_tracks
            WHERE is_dark_ship = TRUE AND track_status NOT IN ('dropped')
        """)

        # Step 4: Create vector tables if pgvector is available
        if pgvector_available:
            print("  Creating vector embedding tables...")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_embeddings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    content TEXT NOT NULL,
                    document_type VARCHAR(50) NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    embedding vector(768),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_embeddings_type ON document_embeddings(document_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_embeddings_metadata ON document_embeddings USING GIN (metadata)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS track_history_embeddings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    track_id VARCHAR(50) NOT NULL,
                    window_start TIMESTAMPTZ NOT NULL,
                    window_end TIMESTAMPTZ NOT NULL,
                    description TEXT NOT NULL,
                    embedding vector(768),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_history_track ON track_history_embeddings(track_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_history_time ON track_history_embeddings(window_start DESC)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_embeddings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    source_type VARCHAR(50) NOT NULL,
                    source_id VARCHAR(100),
                    description TEXT NOT NULL,
                    embedding vector(768),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_embeddings_source ON anomaly_embeddings(source_type, source_id)")

            # Try to create vector indexes (may fail if not enough data)
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_history_vector ON track_history_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_embeddings_vector ON anomaly_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)")
            except Exception as e:
                print(f"  Note: Vector indexes not created yet (need data first): {e}")

        # Verify tables were created
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cursor.fetchall()

        print(f"\nCreated {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()

        return True, pgvector_available

    except Exception as e:
        print(f"Error running schema: {e}")
        return False, False


def check_connection(host="localhost", port=5432, user="postgres", password="password"):
    """Test database connection."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"PostgreSQL version: {version}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Maritime RAG - PostgreSQL Setup")
    print("=" * 60)

    # Configuration
    config = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", 5432)),
        "user": os.environ.get("POSTGRES_USER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD", "password"),
    }

    print(f"\nConfig: {config['user']}@{config['host']}:{config['port']}")
    print()

    # Step 1: Check connection
    print("Step 1: Testing PostgreSQL connection...")
    if not check_connection(**config):
        print("\nFailed to connect. Please check:")
        print("  - PostgreSQL is running")
        print("  - Password is correct")
        print("  - Host/port are correct")
        sys.exit(1)

    print()

    # Step 2: Create database
    print("Step 2: Creating database...")
    if not create_database(**config):
        sys.exit(1)

    print()

    # Step 3: Run schema
    print("Step 3: Running RAG schema...")
    success, pgvector_available = run_schema(**config)
    if not success:
        sys.exit(1)

    print()
    print("=" * 60)
    print("Setup complete!")
    print("=" * 60)

    if not pgvector_available:
        print("\nWARNING: pgvector extension is not installed.")
        print("Vector embedding tables were NOT created.")
        print("To enable semantic search, install pgvector:")
        print("  1. Download from: https://github.com/pgvector/pgvector/releases")
        print("  2. Extract to PostgreSQL extensions folder")
        print("  3. Re-run this script")
        print("\nThe SQL Agent will work without pgvector.")
    else:
        print("\nAll features enabled including vector search!")
