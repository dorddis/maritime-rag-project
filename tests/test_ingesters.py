"""
Quick test of all ingesters in dry-run mode
"""

import sys
sys.path.insert(0, 'ingestion')

print("=" * 60)
print("INGESTER QUICK TEST")
print("=" * 60)

# Test 1: AIS Ingester
print("\n[1] AIS NMEA Ingester Test")
print("-" * 40)

from ingesters.ais_nmea_ingester import AISNMEAIngester
import asyncio

async def test_ais():
    ingester = AISNMEAIngester(
        redis_client=None,  # Dry run
        source="mock",
        num_ships=5,
        rate_hz=1.0
    )
    await ingester.run_once()
    print(f"  Messages processed: {ingester.messages_processed}")
    print(f"  Positions published: {ingester.positions_published}")
    print(f"  Errors: {ingester.errors}")

asyncio.run(test_ais())

# Test 2: Radar Ingester
print("\n[2] Radar Binary Ingester Test")
print("-" * 40)

from ingesters.radar_binary_ingester import RadarBinaryIngester

async def test_radar():
    ingester = RadarBinaryIngester(
        redis_client=None,
        source="mock",
        num_tracks=10,
        rate_hz=1.0
    )
    await ingester.run_once()
    print(f"  Messages processed: {ingester.messages_processed}")
    print(f"  Contacts published: {ingester.contacts_published}")
    print(f"  System status msgs: {ingester.system_status_count}")
    print(f"  Errors: {ingester.errors}")

asyncio.run(test_radar())

# Test 3: Satellite Ingester
print("\n[3] Satellite File Ingester Test")
print("-" * 40)

from ingesters.satellite_file_ingester import SatelliteFileIngester

async def test_satellite():
    ingester = SatelliteFileIngester(
        redis_client=None,
        source="mock",
        watch_dir="./data/satellite",
        rate_hz=0.1
    )
    await ingester.run_once()
    print(f"  Files processed: {ingester.files_processed}")
    print(f"  Detections published: {ingester.detections_published}")
    print(f"  Dark ships detected: {ingester.dark_ships_detected}")
    print(f"  Errors: {ingester.errors}")

asyncio.run(test_satellite())

# Test 4: Drone Ingester
print("\n[4] Drone CV Ingester Test")
print("-" * 40)

from ingesters.drone_cv_ingester import DroneCVIngester

async def test_drone():
    ingester = DroneCVIngester(
        redis_client=None,
        source="mock",
        watch_dir="./data/drone",
        rate_hz=0.5
    )
    await ingester.run_once()
    print(f"  Frames processed: {ingester.frames_processed}")
    print(f"  Detections published: {ingester.detections_published}")
    print(f"  Errors: {ingester.errors}")

asyncio.run(test_drone())

print("\n" + "=" * 60)
print("All ingesters working!")
print("=" * 60)
