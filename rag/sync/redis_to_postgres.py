"""
Redis to PostgreSQL Sync Service

Continuously syncs unified tracks from Redis fusion layer to PostgreSQL
for historical querying and RAG analytics.

Sync frequency: 2 Hz (configurable)
Data sources:
  - fusion:active_tracks (set) → unified_tracks table
  - fusion:track:{id} (hash) → unified_tracks table
  - fusion:dark_ships (stream) → dark_ship_events table
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import asyncpg
import redis.asyncio as redis

from ..config import settings, get_postgres_url, get_redis_url

logger = logging.getLogger(__name__)


class RedisSyncService:
    """
    Sync service to transfer Redis fusion data to PostgreSQL.

    Runs continuously at configurable rate (default 2 Hz).
    """

    def __init__(
        self,
        redis_url: str = None,
        postgres_url: str = None,
        sync_rate_hz: float = None,
    ):
        self.redis_url = redis_url or get_redis_url()
        self.postgres_url = postgres_url or get_postgres_url()
        self.sync_rate_hz = sync_rate_hz or settings.sync_rate_hz

        self.redis_client: Optional[redis.Redis] = None
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.running = False

        # Stats
        self.stats = {
            "tracks_synced": 0,
            "dark_events_synced": 0,
            "errors": 0,
            "last_sync": None,
        }

    async def connect(self):
        """Initialize connections to Redis and PostgreSQL."""
        logger.info("Connecting to Redis and PostgreSQL...")

        # Redis connection
        self.redis_client = await redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        # PostgreSQL connection pool
        self.pg_pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=10,
        )

        logger.info("Connected to Redis and PostgreSQL")

    async def close(self):
        """Close all connections."""
        if self.redis_client:
            await self.redis_client.close()
        if self.pg_pool:
            await self.pg_pool.close()
        logger.info("Connections closed")

    async def start(self):
        """Start the sync service loop."""
        await self.connect()
        self.running = True

        logger.info(f"Starting sync service at {self.sync_rate_hz} Hz")

        try:
            while self.running:
                loop_start = asyncio.get_event_loop().time()

                try:
                    # Sync unified tracks
                    await self._sync_unified_tracks()

                    # Sync dark ship events
                    await self._sync_dark_ship_events()

                    self.stats["last_sync"] = datetime.now(timezone.utc).isoformat()

                except Exception as e:
                    logger.error(f"Sync error: {e}")
                    self.stats["errors"] += 1

                # Rate limiting
                elapsed = asyncio.get_event_loop().time() - loop_start
                sleep_time = max(0, (1.0 / self.sync_rate_hz) - elapsed)
                await asyncio.sleep(sleep_time)

        finally:
            await self.close()

    async def stop(self):
        """Stop the sync service."""
        self.running = False
        logger.info("Stopping sync service...")

    async def _sync_unified_tracks(self):
        """
        Sync fusion:track:{id} hashes to unified_tracks table.

        Reads active track IDs from fusion:active_tracks set,
        fetches each track's data, and upserts to PostgreSQL.
        """
        # Get all active track IDs
        track_ids = await self.redis_client.smembers("fusion:active_tracks")

        if not track_ids:
            return

        # Fetch all track data
        tracks_to_sync = []
        for track_id in track_ids:
            track_data = await self.redis_client.hgetall(f"fusion:track:{track_id}")
            if track_data:
                try:
                    parsed = self._parse_track_data(track_id, track_data)
                    if parsed:
                        tracks_to_sync.append(parsed)
                except Exception as e:
                    logger.warning(f"Failed to parse track {track_id}: {e}")

        if not tracks_to_sync:
            return

        # Bulk upsert to PostgreSQL
        async with self.pg_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO unified_tracks (
                    track_id, latitude, longitude, speed_knots, course, heading,
                    position_uncertainty_m, velocity_north_ms, velocity_east_ms,
                    identity_source, mmsi, ship_name, vessel_type, vessel_length_m,
                    is_dark_ship, dark_ship_confidence, ais_last_seen, ais_gap_seconds,
                    contributing_sensors, track_status, track_quality,
                    correlation_confidence, update_count, flagged_for_review,
                    alert_reason, created_at, updated_at, last_synced_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28
                )
                ON CONFLICT (track_id) DO UPDATE SET
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    speed_knots = EXCLUDED.speed_knots,
                    course = EXCLUDED.course,
                    heading = EXCLUDED.heading,
                    position_uncertainty_m = EXCLUDED.position_uncertainty_m,
                    velocity_north_ms = EXCLUDED.velocity_north_ms,
                    velocity_east_ms = EXCLUDED.velocity_east_ms,
                    mmsi = EXCLUDED.mmsi,
                    ship_name = EXCLUDED.ship_name,
                    vessel_type = EXCLUDED.vessel_type,
                    is_dark_ship = EXCLUDED.is_dark_ship,
                    dark_ship_confidence = EXCLUDED.dark_ship_confidence,
                    ais_last_seen = EXCLUDED.ais_last_seen,
                    ais_gap_seconds = EXCLUDED.ais_gap_seconds,
                    contributing_sensors = EXCLUDED.contributing_sensors,
                    track_status = EXCLUDED.track_status,
                    track_quality = EXCLUDED.track_quality,
                    correlation_confidence = EXCLUDED.correlation_confidence,
                    update_count = EXCLUDED.update_count,
                    flagged_for_review = EXCLUDED.flagged_for_review,
                    alert_reason = EXCLUDED.alert_reason,
                    updated_at = EXCLUDED.updated_at,
                    last_synced_at = EXCLUDED.last_synced_at
                """,
                tracks_to_sync,
            )

        self.stats["tracks_synced"] += len(tracks_to_sync)
        logger.debug(f"Synced {len(tracks_to_sync)} unified tracks")

    async def _sync_dark_ship_events(self):
        """
        Sync fusion:dark_ships stream to dark_ship_events table.

        Uses Redis consumer group to track last processed message.
        """
        stream_name = "fusion:dark_ships"
        group_name = "postgres-sync"
        consumer_name = "sync-worker"

        # Create consumer group if not exists
        try:
            await self.redis_client.xgroup_create(
                stream_name,
                group_name,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Error creating consumer group: {e}")
                return

        # Read new messages
        try:
            messages = await self.redis_client.xreadgroup(
                group_name,
                consumer_name,
                {stream_name: ">"},
                count=100,
                block=100,
            )
        except Exception as e:
            logger.debug(f"No dark ship messages: {e}")
            return

        if not messages:
            return

        events_to_insert = []
        message_ids_to_ack = []

        for stream, stream_messages in messages:
            for msg_id, msg_data in stream_messages:
                try:
                    event = self._parse_dark_ship_event(msg_data)
                    if event:
                        events_to_insert.append(event)
                        message_ids_to_ack.append(msg_id)
                except Exception as e:
                    logger.warning(f"Failed to parse dark ship event {msg_id}: {e}")

        if not events_to_insert:
            return

        # Insert events
        async with self.pg_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO dark_ship_events (
                    track_id, event_timestamp, latitude, longitude,
                    confidence, alert_reason, detected_by, ais_gap_seconds,
                    speed_at_detection, heading_at_detection
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT DO NOTHING
                """,
                events_to_insert,
            )

        # Acknowledge messages
        for msg_id in message_ids_to_ack:
            await self.redis_client.xack(stream_name, group_name, msg_id)

        self.stats["dark_events_synced"] += len(events_to_insert)
        logger.debug(f"Synced {len(events_to_insert)} dark ship events")

    def _parse_track_data(self, track_id: str, redis_data: Dict[str, str]) -> tuple:
        """
        Parse Redis track hash to PostgreSQL row format.

        Returns tuple matching the INSERT statement column order.
        """
        now = datetime.now(timezone.utc)

        # Parse timestamps
        created_at = self._parse_timestamp(redis_data.get("created_at")) or now
        updated_at = self._parse_timestamp(redis_data.get("updated_at")) or now
        ais_last_seen = self._parse_timestamp(redis_data.get("ais_last_seen"))

        # Parse contributing_sensors as array
        sensors_str = redis_data.get("contributing_sensors", "")
        if sensors_str:
            sensors = [s.strip() for s in sensors_str.split(",") if s.strip()]
        else:
            sensors = []

        return (
            track_id,
            self._parse_float(redis_data.get("latitude")),
            self._parse_float(redis_data.get("longitude")),
            self._parse_float(redis_data.get("speed_knots")),
            self._parse_float(redis_data.get("course")),
            self._parse_float(redis_data.get("heading")),
            self._parse_float(redis_data.get("position_uncertainty_m"), 1000.0),
            self._parse_float(redis_data.get("velocity_north_ms"), 0.0),
            self._parse_float(redis_data.get("velocity_east_ms"), 0.0),
            redis_data.get("identity_source") or "unknown",
            redis_data.get("mmsi") or None,
            redis_data.get("ship_name") or None,
            redis_data.get("vessel_type") or None,
            self._parse_float(redis_data.get("vessel_length_m")),
            self._parse_bool(redis_data.get("is_dark_ship")),
            self._parse_float(redis_data.get("dark_ship_confidence"), 0.0),
            ais_last_seen,
            self._parse_float(redis_data.get("ais_gap_seconds")),
            sensors,  # TEXT[] array
            redis_data.get("status") or redis_data.get("track_status") or "tentative",
            self._parse_int(redis_data.get("track_quality"), 0),
            self._parse_float(redis_data.get("correlation_confidence"), 0.0),
            self._parse_int(redis_data.get("update_count"), 0),
            self._parse_bool(redis_data.get("flagged_for_review")),
            redis_data.get("alert_reason") or None,
            created_at,
            updated_at,
            now,  # last_synced_at
        )

    def _parse_dark_ship_event(self, redis_data: Dict[str, str]) -> tuple:
        """
        Parse Redis dark ship alert to PostgreSQL row format.

        Returns tuple matching the INSERT statement column order.
        """
        # Parse detected_by as array
        detected_by_str = redis_data.get("detected_by", "")
        if detected_by_str:
            detected_by = [s.strip() for s in detected_by_str.split(",") if s.strip()]
        else:
            detected_by = []

        return (
            redis_data.get("track_id"),
            self._parse_timestamp(redis_data.get("timestamp")) or datetime.now(timezone.utc),
            self._parse_float(redis_data.get("latitude")),
            self._parse_float(redis_data.get("longitude")),
            self._parse_float(redis_data.get("confidence"), 0.0),
            redis_data.get("alert_reason") or redis_data.get("reason"),
            detected_by,  # TEXT[] array
            self._parse_float(redis_data.get("ais_gap_seconds")),
            self._parse_float(redis_data.get("speed_knots")),
            self._parse_float(redis_data.get("heading")),
        )

    @staticmethod
    def _parse_float(value: Any, default: float = None) -> Optional[float]:
        """Parse string to float, returning default if invalid."""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_int(value: Any, default: int = None) -> Optional[int]:
        """Parse string to int, returning default if invalid."""
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        """Parse string to bool."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime."""
        if value is None or value == "":
            return None
        try:
            # Handle various ISO formats
            if isinstance(value, datetime):
                return value
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt
        except (ValueError, AttributeError):
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get sync service statistics."""
        return {
            **self.stats,
            "running": self.running,
            "sync_rate_hz": self.sync_rate_hz,
        }


async def run_sync_service():
    """Run the sync service (for direct execution)."""
    logging.basicConfig(level=logging.INFO)

    service = RedisSyncService()

    try:
        await service.start()
    except KeyboardInterrupt:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(run_sync_service())
