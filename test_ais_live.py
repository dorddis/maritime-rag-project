"""
Quick AIS Test - See real ship data in 30 seconds
Run: python test_ais_live.py
"""

import asyncio
import json
import os
from datetime import datetime, timezone

import websockets
import redis
from dotenv import load_dotenv

load_dotenv()

AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

# Indian Ocean bounding box
BOUNDING_BOX = [[[5, 65], [25, 100]]]

async def test_ais():
    print("=" * 60)
    print("MARITIME AIS LIVE TEST")
    print("=" * 60)
    print(f"API Key: {AISSTREAM_API_KEY[:10]}...")
    print(f"Redis: {REDIS_URL[:30]}...")
    print(f"Region: Indian Ocean ({BOUNDING_BOX})")
    print("=" * 60)

    # Connect Redis
    r = redis.from_url(REDIS_URL)
    r.ping()
    print("[OK] Redis connected")

    # Connect WebSocket
    print("[..] Connecting to aisstream.io...")

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        # Subscribe
        await ws.send(json.dumps({
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": BOUNDING_BOX,
            "FilterMessageTypes": ["PositionReport"]
        }))
        print("[OK] Subscribed to AIS stream")
        print()
        print("Waiting for ship data...")
        print("-" * 60)

        count = 0
        async for msg in ws:
            data = json.loads(msg)

            if data.get("MessageType") == "PositionReport":
                pos = data["Message"]["PositionReport"]
                meta = data.get("MetaData", {})

                count += 1
                ship_name = meta.get("ShipName", "Unknown")
                mmsi = pos.get("UserID") or meta.get("MMSI")
                lat = pos["Latitude"]
                lon = pos["Longitude"]
                speed = pos.get("Sog", 0)

                print(f"[{count:03d}] {ship_name[:20]:<20} | MMSI: {mmsi} | {lat:.4f}, {lon:.4f} | {speed:.1f} kn")

                # Publish to Redis
                r.xadd("maritime:ais-positions", {
                    "mmsi": str(mmsi),
                    "ship_name": ship_name,
                    "latitude": str(lat),
                    "longitude": str(lon),
                    "speed_knots": str(speed),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, maxlen=10000)

                if count >= 20:
                    print("-" * 60)
                    print(f"Received {count} ship positions!")
                    print(f"Redis stream length: {r.xlen('maritime:ais-positions')}")
                    break

if __name__ == "__main__":
    asyncio.run(test_ais())
