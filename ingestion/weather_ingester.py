"""
Weather Data Ingester
Polls Open-Meteo API for weather conditions at key maritime locations

Format: REST API JSON (polling)
Source: https://open-meteo.com/ (FREE, no API key needed)
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict

import httpx
import redis.asyncio as redis
from dotenv import load_dotenv
import os

from schema import WeatherObservation

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Key maritime locations to monitor
MONITORING_POINTS = [
    {"name": "Mumbai", "lat": 18.94, "lon": 72.84},
    {"name": "Chennai", "lat": 13.08, "lon": 80.27},
    {"name": "Kochi", "lat": 9.93, "lon": 76.27},
    {"name": "Visakhapatnam", "lat": 17.69, "lon": 83.22},
    {"name": "Kandla", "lat": 23.03, "lon": 70.22},
    {"name": "Arabian Sea Central", "lat": 15.0, "lon": 68.0},
    {"name": "Bay of Bengal Central", "lat": 14.0, "lon": 88.0},
    {"name": "Lakshadweep", "lat": 10.57, "lon": 72.64},
]

POLL_INTERVAL_SECONDS = 900  # 15 minutes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeatherIngester:
    """Polls weather API and publishes to Redis"""

    def __init__(self):
        self.redis_client = None
        self.http_client = None

    async def connect(self):
        """Initialize connections"""
        self.redis_client = redis.from_url(REDIS_URL)
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Weather ingester initialized")

    async def fetch_weather(self, location: Dict) -> WeatherObservation:
        """Fetch weather for a single location"""

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": location["lat"],
            "longitude": location["lon"],
            "current_weather": "true",
            "windspeed_unit": "kn"  # knots for maritime
        }

        response = await self.http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        current = data.get("current_weather", {})

        return WeatherObservation(
            timestamp=datetime.fromisoformat(current.get("time", datetime.utcnow().isoformat())),
            latitude=location["lat"],
            longitude=location["lon"],
            temperature_c=current.get("temperature"),
            wind_speed_knots=current.get("windspeed"),
            wind_direction=current.get("winddirection"),
            weather_code=current.get("weathercode"),
            source=f"open-meteo:{location['name']}"
        )

    async def publish_weather(self, obs: WeatherObservation):
        """Publish to Redis stream"""
        await self.redis_client.xadd(
            "maritime:weather",
            {
                "id": obs.id,
                "timestamp": obs.timestamp.isoformat(),
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "temperature_c": obs.temperature_c or 0,
                "wind_speed_knots": obs.wind_speed_knots or 0,
                "wind_direction": obs.wind_direction or 0,
                "weather_code": obs.weather_code or 0,
                "source": obs.source,
                "ingested_at": obs.ingested_at.isoformat()
            },
            maxlen=10000
        )

    async def poll_all_locations(self):
        """Fetch weather for all monitoring points"""

        logger.info(f"Polling weather for {len(MONITORING_POINTS)} locations...")

        for location in MONITORING_POINTS:
            try:
                obs = await self.fetch_weather(location)
                await self.publish_weather(obs)
                logger.info(f"  {location['name']}: {obs.temperature_c}C, wind {obs.wind_speed_knots}kn")
            except Exception as e:
                logger.error(f"  {location['name']}: Error - {e}")

            # Small delay between requests to be polite
            await asyncio.sleep(0.5)

        logger.info("Weather poll complete")

    async def run(self):
        """Main polling loop"""

        await self.connect()

        while True:
            try:
                await self.poll_all_locations()
            except Exception as e:
                logger.error(f"Poll cycle error: {e}")

            logger.info(f"Next poll in {POLL_INTERVAL_SECONDS} seconds...")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main():
    ingester = WeatherIngester()

    try:
        await ingester.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
