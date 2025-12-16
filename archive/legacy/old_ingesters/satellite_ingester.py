"""
Satellite/Radar Data Ingester
Watches directory for incoming CSV/GeoJSON files and ingests them

Format: CSV or GeoJSON (batch files)
Source: Simulated satellite detections (or real NOAA data)
"""

import asyncio
import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

import redis.asyncio as redis
from dotenv import load_dotenv

from schema import SatelliteDetection, DataSource

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WATCH_DIRECTORY = os.getenv("SATELLITE_WATCH_DIR", "./satellite_data")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SatelliteIngester:
    """Watches for satellite detection files and ingests them"""

    def __init__(self):
        self.redis_client = None
        self.processed_files = set()

    async def connect_redis(self):
        """Connect to Redis"""
        self.redis_client = redis.from_url(REDIS_URL)
        logger.info(f"Connected to Redis at {REDIS_URL}")

    def parse_csv(self, filepath: str) -> List[SatelliteDetection]:
        """Parse CSV satellite detection file"""

        detections = []

        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    detection = SatelliteDetection(
                        detection_id=row.get("detection_id", f"DET-{datetime.utcnow().timestamp()}"),
                        timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        confidence=float(row.get("confidence", 0.5)),
                        vessel_length_m=float(row.get("vessel_length_m", 0)) if row.get("vessel_length_m") else None,
                        source_satellite=row.get("source", "unknown"),
                    )
                    detections.append(detection)
                except Exception as e:
                    logger.error(f"Error parsing CSV row: {e}")

        return detections

    def parse_geojson(self, filepath: str) -> List[SatelliteDetection]:
        """Parse GeoJSON satellite detection file"""

        detections = []

        with open(filepath, 'r') as f:
            data = json.load(f)

        features = data.get("features", [])

        for feature in features:
            try:
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [0, 0])

                detection = SatelliteDetection(
                    detection_id=props.get("detection_id", f"DET-{datetime.utcnow().timestamp()}"),
                    timestamp=datetime.fromisoformat(props["timestamp"].replace("Z", "+00:00")),
                    latitude=coords[1],  # GeoJSON is [lon, lat]
                    longitude=coords[0],
                    confidence=float(props.get("confidence", 0.5)),
                    vessel_length_m=float(props.get("vessel_length_m", 0)) if props.get("vessel_length_m") else None,
                    source_satellite=props.get("source", "unknown"),
                )
                detections.append(detection)
            except Exception as e:
                logger.error(f"Error parsing GeoJSON feature: {e}")

        return detections

    async def publish_detection(self, detection: SatelliteDetection):
        """Publish detection to Redis stream"""

        await self.redis_client.xadd(
            "maritime:satellite",
            {
                "id": detection.id,
                "detection_id": detection.detection_id,
                "timestamp": detection.timestamp.isoformat(),
                "latitude": detection.latitude,
                "longitude": detection.longitude,
                "confidence": detection.confidence,
                "vessel_length_m": detection.vessel_length_m or 0,
                "source_satellite": detection.source_satellite,
                "is_dark_ship": str(detection.is_dark_ship),
                "ingested_at": detection.ingested_at.isoformat()
            },
            maxlen=50000
        )

    async def process_file(self, filepath: str):
        """Process a single file"""

        if filepath in self.processed_files:
            return

        logger.info(f"Processing file: {filepath}")

        try:
            if filepath.endswith('.csv'):
                detections = self.parse_csv(filepath)
            elif filepath.endswith('.geojson') or filepath.endswith('.json'):
                detections = self.parse_geojson(filepath)
            else:
                logger.warning(f"Unknown file format: {filepath}")
                return

            for detection in detections:
                await self.publish_detection(detection)

            self.processed_files.add(filepath)
            logger.info(f"Processed {len(detections)} detections from {filepath}")

            # Optionally move file to processed directory
            # os.rename(filepath, filepath + ".processed")

        except Exception as e:
            logger.error(f"Error processing file {filepath}: {e}")

    async def scan_directory(self):
        """Scan directory for existing files"""

        watch_path = Path(WATCH_DIRECTORY)

        if not watch_path.exists():
            watch_path.mkdir(parents=True)
            logger.info(f"Created watch directory: {WATCH_DIRECTORY}")

        for filepath in watch_path.glob("*"):
            if filepath.suffix in ['.csv', '.geojson', '.json']:
                await self.process_file(str(filepath))

    async def run(self):
        """Main loop - scan directory periodically"""

        await self.connect_redis()

        logger.info(f"Watching directory: {WATCH_DIRECTORY}")
        logger.info("Drop CSV or GeoJSON files here to ingest satellite detections")

        while True:
            await self.scan_directory()
            await asyncio.sleep(30)  # Check every 30 seconds


def generate_sample_csv():
    """Generate sample satellite detection CSV for testing"""

    import random

    filepath = os.path.join(WATCH_DIRECTORY, f"satellite_detections_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv")

    os.makedirs(WATCH_DIRECTORY, exist_ok=True)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["detection_id", "timestamp", "latitude", "longitude", "confidence", "vessel_length_m", "source"])

        # Generate 10 random detections in Indian Ocean
        for i in range(10):
            lat = random.uniform(8, 22)  # Indian Ocean latitude range
            lon = random.uniform(68, 95)  # Indian Ocean longitude range

            writer.writerow([
                f"SAT-{i+1:03d}",
                datetime.utcnow().isoformat() + "Z",
                f"{lat:.6f}",
                f"{lon:.6f}",
                f"{random.uniform(0.6, 0.95):.2f}",
                f"{random.randint(50, 300)}",
                random.choice(["Sentinel-2", "Sentinel-1", "Planet", "Maxar"])
            ])

    logger.info(f"Generated sample file: {filepath}")
    return filepath


async def main():
    ingester = SatelliteIngester()

    # Generate sample data for testing
    generate_sample_csv()

    try:
        await ingester.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
