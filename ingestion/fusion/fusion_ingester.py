"""
Sensor Fusion Ingester

Consumes from all 4 sensor streams, correlates detections,
manages unified tracks, and detects dark ships.

Usage:
    python -m ingestion.fusion.fusion_ingester
    python -m ingestion.fusion.fusion_ingester --rate 2.0
"""

import asyncio
import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingestion.fusion.schema import UnifiedTrack
from ingestion.fusion.config import CorrelationGates, DarkShipDetectionConfig
from ingestion.fusion.correlation import CorrelationEngine
from ingestion.fusion.track_manager import TrackManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - FUSION - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FusionIngester:
    """
    Multi-sensor fusion ingester.

    Reads from:
        - ais:positions
        - radar:contacts
        - satellite:detections
        - drone:detections

    Writes to:
        - fusion:tracks (stream)
        - fusion:track:{id} (hashes)
        - fusion:active_tracks (set)
        - fusion:dark_ships (stream)
        - fusion:status (hash)
    """

    INPUT_STREAMS = {
        "ais:positions": "ais",
        "radar:contacts": "radar",
        "satellite:detections": "satellite",
        "drone:detections": "drone",
    }

    OUTPUT_STREAM = "fusion:tracks"
    DARK_SHIPS_STREAM = "fusion:dark_ships"
    ACTIVE_TRACKS_KEY = "fusion:active_tracks"
    STATUS_KEY = "fusion:status"
    TRACK_PREFIX = "fusion:track:"

    def __init__(
        self,
        redis_client,
        rate_hz: float = 2.0,
        consumer_group: str = "fusion-group"
    ):
        self.redis = redis_client
        self.rate_hz = rate_hz
        self.consumer_group = consumer_group
        self.consumer_name = f"fusion-{int(time.time())}"

        # Initialize correlation engine and track manager
        self.gates = CorrelationGates()
        self.dark_config = DarkShipDetectionConfig()
        self.correlation_engine = CorrelationEngine(self.gates)
        self.track_manager = TrackManager(self.gates, self.dark_config)

        self.running = False
        self.start_time: Optional[datetime] = None

        # Statistics
        self.stats = {
            "messages_processed": 0,
            "correlations_made": 0,
            "tracks_published": 0,
            "dark_ship_alerts": 0,
            "errors": 0,
        }

    async def setup_consumer_groups(self):
        """Create consumer groups for all input streams"""
        for stream in self.INPUT_STREAMS.keys():
            try:
                await self.redis.xgroup_create(
                    stream, self.consumer_group, id="0", mkstream=True
                )
                logger.info(f"Created consumer group for {stream}")
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    logger.warning(f"Consumer group setup for {stream}: {e}")

    async def read_all_streams(self, timeout_ms: int = 100) -> List[Tuple[str, str, dict]]:
        """
        Read new messages from all input streams.

        Returns:
            List of (stream_name, message_id, message_data)
        """
        messages = []

        # Build streams dict for XREADGROUP
        streams = {stream: ">" for stream in self.INPUT_STREAMS.keys()}

        try:
            result = await self.redis.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                streams,
                count=100,
                block=timeout_ms
            )

            if result:
                for stream_name, stream_messages in result:
                    for msg_id, msg_data in stream_messages:
                        messages.append((stream_name, msg_id, msg_data))

        except Exception as e:
            if "NOGROUP" in str(e):
                await self.setup_consumer_groups()
            else:
                logger.error(f"Error reading streams: {e}")
                self.stats["errors"] += 1

        return messages

    def parse_detection(self, stream: str, data: dict) -> dict:
        """Parse detection from stream-specific format to common format"""
        sensor_type = self.INPUT_STREAMS[stream]

        detection = {
            "latitude": float(data.get("latitude", 0)),
            "longitude": float(data.get("longitude", 0)),
            "timestamp": data.get("timestamp"),
        }

        # Sensor-specific parsing
        if sensor_type == "ais":
            detection["mmsi"] = data.get("mmsi")
            detection["ship_name"] = data.get("ship_name")
            detection["ship_type"] = data.get("ship_type")
            detection["speed_knots"] = self._safe_float(data.get("speed_knots"))
            detection["course"] = self._safe_float(data.get("course"))
            detection["sensor_id"] = "AIS"

        elif sensor_type == "radar":
            detection["track_id"] = data.get("track_id")
            detection["speed_knots"] = self._safe_float(data.get("speed_knots"))
            detection["course"] = self._safe_float(data.get("course"))
            detection["sensor_id"] = data.get("station_id", "RADAR")
            detection["quality"] = int(data.get("quality", 0))

        elif sensor_type == "satellite":
            detection["detection_id"] = data.get("detection_id")
            detection["vessel_length_m"] = self._safe_float(data.get("vessel_length_m"))
            detection["confidence"] = self._safe_float(data.get("confidence"))
            detection["is_dark_ship"] = data.get("is_dark_ship", "False") == "True"
            detection["sensor_id"] = data.get("source_satellite", "SAT")

        elif sensor_type == "drone":
            detection["detection_id"] = data.get("detection_id")
            detection["object_class"] = data.get("object_class")
            detection["estimated_length_m"] = self._safe_float(data.get("estimated_length_m"))
            detection["confidence"] = self._safe_float(data.get("confidence"))
            detection["sensor_id"] = data.get("drone_id", "DRONE")

        return detection

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float, return None if invalid"""
        if value is None:
            return None
        try:
            f = float(value)
            return f if f != 0 else None
        except (ValueError, TypeError):
            return None

    async def process_batch(self, messages: List[Tuple[str, str, dict]]):
        """Process a batch of detections"""
        now = datetime.now(timezone.utc)

        # Parse all detections
        detections = []
        for stream, msg_id, data in messages:
            sensor_type = self.INPUT_STREAMS[stream]
            detection = self.parse_detection(stream, data)
            detections.append((detection, sensor_type))
            self.stats["messages_processed"] += 1

        # Get current tracks
        tracks = self.track_manager.get_active_tracks()

        # Batch correlation
        assignments = self.correlation_engine.batch_correlate(
            detections, tracks, now
        )

        # Process assignments
        for track_id, assigned_dets in assignments.items():
            if track_id == "NEW":
                # Create new tracks
                for det, sensor_type, _ in assigned_dets:
                    sensor_id = det.get("sensor_id", sensor_type.upper())
                    self.track_manager.create_track(det, sensor_type, sensor_id)
            else:
                # Update existing track
                for det, sensor_type, confidence in assigned_dets:
                    sensor_id = det.get("sensor_id", sensor_type.upper())
                    self.track_manager.update_track(
                        track_id, det, sensor_type, sensor_id, confidence
                    )
                    self.stats["correlations_made"] += 1

        # Check for dark ships
        self.track_manager.check_dark_ships(now)

        # Age tracks
        self.track_manager.age_tracks(now)

        # Acknowledge processed messages
        for stream, msg_id, _ in messages:
            try:
                await self.redis.xack(stream, self.consumer_group, msg_id)
            except Exception:
                pass

    async def publish_tracks(self):
        """Publish updated tracks to Redis"""
        now = datetime.now(timezone.utc)

        active_tracks = self.track_manager.get_active_tracks()
        dark_ships = self.track_manager.get_dark_ships()

        # Update active tracks set
        pipeline = self.redis.pipeline()

        if active_tracks:
            # Clear and rebuild active tracks set
            pipeline.delete(self.ACTIVE_TRACKS_KEY)
            pipeline.sadd(self.ACTIVE_TRACKS_KEY, *active_tracks.keys())

        # Publish each track
        for track_id, track in active_tracks.items():
            # Update track hash
            pipeline.hset(
                f"{self.TRACK_PREFIX}{track_id}",
                mapping=track.to_redis_dict()
            )

            # Publish to stream (only recently updated tracks)
            if (now - track.updated_at).total_seconds() < 5:
                pipeline.xadd(
                    self.OUTPUT_STREAM,
                    track.to_redis_dict(),
                    maxlen=10000
                )
                self.stats["tracks_published"] += 1

        # Publish dark ship alerts (only new ones)
        for track in dark_ships:
            if track.flagged_for_review:
                alert_data = {
                    "track_id": track.track_id,
                    "latitude": str(track.latitude),
                    "longitude": str(track.longitude),
                    "confidence": str(track.dark_ship_confidence),
                    "alert_reason": track.alert_reason or "",
                    "detected_by": ",".join(track.contributing_sensors),
                    "timestamp": now.isoformat(),
                }
                pipeline.xadd(
                    self.DARK_SHIPS_STREAM,
                    alert_data,
                    maxlen=1000
                )
                self.stats["dark_ship_alerts"] += 1
                # Clear flag after publishing
                track.flagged_for_review = False

        await pipeline.execute()

    async def update_status(self):
        """Update fusion ingester status"""
        now = datetime.now(timezone.utc)
        uptime = (now - self.start_time).total_seconds() if self.start_time else 0

        tm_stats = self.track_manager.get_stats()

        status = {
            "running": str(self.running),
            "active_tracks": str(tm_stats["active_tracks"]),
            "dark_ships": str(tm_stats["dark_ships_current"]),
            "messages_processed": str(self.stats["messages_processed"]),
            "correlations_made": str(self.stats["correlations_made"]),
            "tracks_created": str(tm_stats["tracks_created"]),
            "tracks_dropped": str(tm_stats["tracks_dropped"]),
            "tracks_merged": str(tm_stats.get("tracks_merged", 0)),
            "dark_ships_flagged": str(tm_stats["dark_ships_flagged"]),
            "errors": str(self.stats["errors"]),
            "uptime_seconds": str(int(uptime)),
            "rate_hz": str(self.rate_hz),
            "last_update": now.isoformat(),
        }

        await self.redis.hset(self.STATUS_KEY, mapping=status)

    async def run(self):
        """Main fusion loop"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        await self.setup_consumer_groups()

        logger.info(f"Fusion ingester started (rate={self.rate_hz}Hz)")
        logger.info(f"Reading from: {list(self.INPUT_STREAMS.keys())}")
        logger.info(f"Writing to: {self.OUTPUT_STREAM}, {self.DARK_SHIPS_STREAM}")

        cycle_count = 0

        try:
            while self.running:
                loop_start = time.time()

                # Read from all input streams
                messages = await self.read_all_streams(timeout_ms=100)

                if messages:
                    await self.process_batch(messages)

                # Periodic publishing and status update
                await self.publish_tracks()
                await self.update_status()

                cycle_count += 1

                # Rate limiting
                elapsed = time.time() - loop_start
                sleep_time = max(0, (1.0 / self.rate_hz) - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Log stats periodically
                if cycle_count % 50 == 0:
                    tm_stats = self.track_manager.get_stats()
                    logger.info(
                        f"Stats: msgs={self.stats['messages_processed']}, "
                        f"tracks={tm_stats['active_tracks']}, "
                        f"dark={tm_stats['dark_ships_current']}, "
                        f"correlations={self.stats['correlations_made']}"
                    )

        except asyncio.CancelledError:
            logger.info("Fusion ingester cancelled")
        except Exception as e:
            logger.error(f"Fusion error: {e}")
            raise
        finally:
            self.running = False
            await self.update_status()
            logger.info("Fusion ingester stopped")

    def stop(self):
        """Stop the fusion ingester"""
        self.running = False


async def main():
    parser = argparse.ArgumentParser(description="Sensor Fusion Ingester")
    parser.add_argument(
        "--rate", type=float, default=2.0,
        help="Processing rate in Hz"
    )
    parser.add_argument(
        "--redis-url", default="redis://localhost:6379",
        help="Redis URL"
    )
    parser.add_argument(
        "--consumer-group", default="fusion-group",
        help="Redis consumer group name"
    )
    args = parser.parse_args()

    import redis.asyncio as redis
    redis_client = redis.from_url(args.redis_url, decode_responses=True)

    try:
        await redis_client.ping()
        logger.info(f"Connected to Redis at {args.redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    ingester = FusionIngester(
        redis_client=redis_client,
        rate_hz=args.rate,
        consumer_group=args.consumer_group
    )

    try:
        await ingester.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
