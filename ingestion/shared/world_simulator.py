"""
World Simulator - Moves Ships in Real-Time

This is the "physics engine" of the simulation.
Runs as a separate process and continuously updates ship positions.
"""

import asyncio
import random
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis

from .fleet_manager import FleetManager, Ship

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - WORLD - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorldSimulator:
    """
    Simulates the physical world - ships moving through the ocean.

    This runs continuously and updates the ground truth ship positions
    that all sensors read from.
    """

    def __init__(
        self,
        fleet_manager: FleetManager,
        update_rate_hz: float = 1.0,
        dark_toggle_probability: float = 0.001,
        speed_multiplier: float = 1.0,
    ):
        self.fleet = fleet_manager
        self.update_rate_hz = update_rate_hz
        self.dark_toggle_prob = dark_toggle_probability
        self.speed_mult = speed_multiplier  # Time acceleration factor
        self.running = False
        self.stats = {
            "updates": 0,
            "dark_toggles": 0,
        }
        self.start_time: Optional[datetime] = None

    async def run(self):
        """Main simulation loop - moves all ships"""
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        interval = 1.0 / self.update_rate_hz

        logger.info(f"World simulator started (rate={self.update_rate_hz}Hz)")

        try:
            while self.running:
                loop_start = asyncio.get_event_loop().time()

                # Get all ships
                ships = await self.fleet.get_all_ships()
                if not ships:
                    logger.warning("No ships in fleet - waiting...")
                    await asyncio.sleep(1.0)
                    continue

                # Move each ship (with time acceleration)
                for ship in ships:
                    ship.move(interval * self.speed_mult)

                    # Random AIS toggle (ships going dark or coming back online)
                    if random.random() < self.dark_toggle_prob:
                        ship.ais_enabled = not ship.ais_enabled
                        self.stats["dark_toggles"] += 1
                        status = "DARK" if not ship.ais_enabled else "ONLINE"
                        logger.info(f"Ship {ship.mmsi} ({ship.vessel_type}) went {status}")

                # Batch update all ships
                await self.fleet.update_ships_batch(ships)
                self.stats["updates"] += 1

                # Update metadata periodically
                if self.stats["updates"] % 10 == 0:
                    await self.fleet.update_metadata()

                # Log stats every 10 seconds
                if self.stats["updates"] % int(10 * self.update_rate_hz) == 0:
                    elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                    dark_count = len([s for s in ships if not s.ais_enabled])
                    logger.info(
                        f"[{elapsed:.0f}s] Ships: {len(ships)} | "
                        f"Dark: {dark_count} | "
                        f"Updates: {self.stats['updates']} | "
                        f"Dark toggles: {self.stats['dark_toggles']}"
                    )

                # Maintain update rate
                elapsed = asyncio.get_event_loop().time() - loop_start
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("World simulator cancelled")
        except Exception as e:
            logger.error(f"World simulator error: {e}")
            raise
        finally:
            self.running = False
            logger.info("World simulator stopped")

    def stop(self):
        """Stop the simulator"""
        self.running = False


async def main():
    parser = argparse.ArgumentParser(description="Maritime World Simulator")
    parser.add_argument("--redis-url", default="redis://localhost:6379",
                        help="Redis URL")
    parser.add_argument("--ships", type=int, default=500,
                        help="Number of ships to simulate")
    parser.add_argument("--dark-pct", type=float, default=5.0,
                        help="Percentage of ships starting dark")
    parser.add_argument("--rate", type=float, default=1.0,
                        help="Update rate in Hz")
    parser.add_argument("--speed-mult", type=float, default=60.0,
                        help="Speed multiplier (time acceleration). 60 = 1 min per second")
    parser.add_argument("--init-only", action="store_true",
                        help="Only initialize fleet, don't run simulator")
    args = parser.parse_args()

    # Connect to Redis (decode_responses=True for string handling)
    redis_client = redis.from_url(args.redis_url, decode_responses=True)
    await redis_client.ping()
    logger.info(f"Connected to Redis at {args.redis_url}")

    # Initialize fleet manager
    fleet = FleetManager(redis_client)

    # Initialize fleet
    logger.info(f"Initializing fleet with {args.ships} ships ({args.dark_pct}% dark)...")
    ships = await fleet.initialize_fleet(
        num_ships=args.ships,
        dark_ship_pct=args.dark_pct
    )
    dark_count = len([s for s in ships if not s.ais_enabled])
    logger.info(f"Fleet initialized: {len(ships)} ships, {dark_count} dark")

    if args.init_only:
        logger.info("Init only mode - exiting")
        return

    # Run simulator
    logger.info(f"Speed multiplier: {args.speed_mult}x (1 sec = {args.speed_mult} sec simulated)")
    simulator = WorldSimulator(
        fleet_manager=fleet,
        update_rate_hz=args.rate,
        speed_multiplier=args.speed_mult,
    )

    try:
        await simulator.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
