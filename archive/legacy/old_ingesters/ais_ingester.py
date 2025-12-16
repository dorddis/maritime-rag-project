"""
AIS Data Ingester
Connects to aisstream.io WebSocket and publishes to Redis

Format: WebSocket JSON (streaming)
Source: https://aisstream.io/
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from typing import Optional

import websockets
import redis.asyncio as redis
from dotenv import load_dotenv

from schema import MaritimePosition, DataSource

load_dotenv()

# Configuration
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY")
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Indian Ocean bounding box (covers India, Sri Lanka, Arabian Sea)
BOUNDING_BOX = [[[5, 65], [25, 100]]]

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AISIngester:
    """WebSocket client for aisstream.io"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.message_count = 0
        self.start_time = None

    async def connect_redis(self):
        """Connect to Redis"""
        self.redis_client = redis.from_url(REDIS_URL)
        logger.info(f"Connected to Redis at {REDIS_URL}")

    async def publish_position(self, position: MaritimePosition):
        """Publish position to Redis stream"""
        await self.redis_client.xadd(
            "maritime:ais-positions",
            position.to_redis_dict(),
            maxlen=100000  # Keep last 100k messages
        )
        self.message_count += 1

        if self.message_count % 100 == 0:
            elapsed = (datetime.utcnow() - self.start_time).total_seconds()
            rate = self.message_count / elapsed if elapsed > 0 else 0
            logger.info(f"Processed {self.message_count} messages ({rate:.1f} msg/sec)")

    def parse_ais_message(self, message: dict) -> Optional[MaritimePosition]:
        """Parse aisstream.io message to unified schema"""

        try:
            message_type = message.get("MessageType")

            if message_type == "PositionReport":
                pos = message["Message"]["PositionReport"]
                meta = message.get("MetaData", {})

                return MaritimePosition(
                    source=DataSource.AIS,
                    timestamp=datetime.fromisoformat(meta.get("time_utc", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
                    latitude=pos["Latitude"],
                    longitude=pos["Longitude"],
                    mmsi=pos.get("UserID") or meta.get("MMSI"),
                    ship_name=meta.get("ShipName"),
                    speed_knots=pos.get("Sog"),
                    heading=pos.get("TrueHeading"),
                    course=pos.get("Cog"),
                    nav_status=pos.get("NavigationalStatus"),
                    raw_payload=message
                )

            elif message_type == "ShipStaticData":
                # Static data (ship name, type, dimensions)
                static = message["Message"]["ShipStaticData"]
                meta = message.get("MetaData", {})

                return MaritimePosition(
                    source=DataSource.AIS,
                    timestamp=datetime.fromisoformat(meta.get("time_utc", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
                    latitude=meta.get("latitude", 0),
                    longitude=meta.get("longitude", 0),
                    mmsi=static.get("UserID") or meta.get("MMSI"),
                    ship_name=static.get("Name") or meta.get("ShipName"),
                    imo=static.get("ImoNumber"),
                    ship_type=str(static.get("Type", "")),
                    vessel_length_m=static.get("Dimension", {}).get("A", 0) + static.get("Dimension", {}).get("B", 0),
                    raw_payload=message
                )

            return None

        except Exception as e:
            logger.error(f"Error parsing AIS message: {e}")
            return None

    async def run(self):
        """Main ingestion loop"""

        if not AISSTREAM_API_KEY:
            logger.error("AISSTREAM_API_KEY not set!")
            logger.info("Get your free API key at: https://aisstream.io/")
            return

        await self.connect_redis()
        self.start_time = datetime.utcnow()

        logger.info(f"Connecting to aisstream.io...")
        logger.info(f"Bounding box: {BOUNDING_BOX}")

        async with websockets.connect(AISSTREAM_URL) as ws:
            # Send subscription
            subscribe_message = {
                "APIKey": AISSTREAM_API_KEY,
                "BoundingBoxes": BOUNDING_BOX,
                "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
            }

            await ws.send(json.dumps(subscribe_message))
            logger.info("Subscribed to AIS stream")

            # Process messages
            async for message_json in ws:
                try:
                    message = json.loads(message_json)
                    position = self.parse_ais_message(message)

                    if position:
                        await self.publish_position(position)

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")


async def main():
    """Entry point"""
    ingester = AISIngester()

    try:
        await ingester.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
