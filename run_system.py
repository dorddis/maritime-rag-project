"""
Maritime System - Run All Ingesters
Starts all 3 data ingesters concurrently
"""

import asyncio
import logging
import sys
import os

# Add ingestion to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ingestion'))

from ingestion.ais_ingester import AISIngester
from ingestion.weather_ingester import WeatherIngester
from ingestion.satellite_ingester import SatelliteIngester, generate_sample_csv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_ais():
    """Run AIS ingester"""
    ingester = AISIngester()
    await ingester.run()


async def run_weather():
    """Run Weather ingester"""
    ingester = WeatherIngester()
    await ingester.run()


async def run_satellite():
    """Run Satellite ingester"""
    # Generate sample data first
    generate_sample_csv()
    ingester = SatelliteIngester()
    await ingester.run()


async def main():
    """Run all ingesters concurrently"""

    logger.info("="*60)
    logger.info("MARITIME DOMAIN AWARENESS SYSTEM")
    logger.info("Starting all ingesters...")
    logger.info("="*60)

    logger.info("""
    Data Sources:
    1. AIS Stream   (WebSocket JSON)  - aisstream.io
    2. Weather API  (REST JSON)       - Open-Meteo
    3. Satellite    (CSV/GeoJSON)     - File watch

    Redis Streams:
    - maritime:ais-positions
    - maritime:weather
    - maritime:satellite
    - maritime:alerts

    Press Ctrl+C to stop
    """)

    # Run all ingesters concurrently
    await asyncio.gather(
        run_ais(),
        run_weather(),
        run_satellite(),
        return_exceptions=True
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
