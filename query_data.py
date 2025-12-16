"""
Query Maritime Data from Redis
Explore the ship positions, find anomalies, run analytics
"""

import redis
import os
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

r = redis.from_url(os.getenv("REDIS_URL"))

def stream_stats():
    """Show stream statistics"""
    print("\n" + "="*60)
    print("REDIS STREAM STATS")
    print("="*60)

    streams = ["maritime:ais-positions", "maritime:weather", "maritime:satellite"]
    for stream in streams:
        length = r.xlen(stream)
        print(f"{stream}: {length:,} messages")

def latest_positions(n=10):
    """Show latest ship positions"""
    print("\n" + "="*60)
    print(f"LATEST {n} SHIP POSITIONS")
    print("="*60)

    messages = r.xrevrange("maritime:ais-positions", count=n)

    for msg_id, data in messages:
        name = data.get(b"ship_name", b"?").decode()
        mmsi = data.get(b"mmsi", b"?").decode()
        lat = data.get(b"latitude", b"0").decode()
        lon = data.get(b"longitude", b"0").decode()
        speed = data.get(b"speed_knots", b"0").decode()

        print(f"{name:<20} | MMSI: {mmsi:<12} | {lat}, {lon} | {speed} kn")

def find_speed_anomalies(threshold=25):
    """Find ships going faster than threshold"""
    print("\n" + "="*60)
    print(f"SPEED ANOMALIES (>{threshold} knots)")
    print("="*60)

    anomalies = []
    cursor = "0"

    # Scan through stream (sample last 50K)
    messages = r.xrevrange("maritime:ais-positions", count=50000)

    for msg_id, data in messages:
        speed = float(data.get(b"speed_knots", b"0").decode())
        if speed > threshold:
            anomalies.append({
                "name": data.get(b"ship_name", b"?").decode(),
                "mmsi": data.get(b"mmsi", b"?").decode(),
                "speed": speed,
                "lat": data.get(b"latitude", b"0").decode(),
                "lon": data.get(b"longitude", b"0").decode(),
            })

    print(f"Found {len(anomalies)} anomalies")
    for a in anomalies[:20]:  # Show top 20
        print(f"  {a['name']:<20} | {a['speed']:.1f} kn | {a['lat']}, {a['lon']}")

def vessel_type_breakdown():
    """Count ships by vessel type"""
    print("\n" + "="*60)
    print("VESSEL TYPE BREAKDOWN (from latest 10K positions)")
    print("="*60)

    type_counts = defaultdict(set)  # Use set to count unique MMSIs

    messages = r.xrevrange("maritime:ais-positions", count=10000)

    for msg_id, data in messages:
        vtype = data.get(b"vessel_type", b"unknown").decode()
        mmsi = data.get(b"mmsi", b"?").decode()
        type_counts[vtype].add(mmsi)

    for vtype, mmsis in sorted(type_counts.items(), key=lambda x: -len(x[1])):
        print(f"  {vtype:<15}: {len(mmsis)} unique vessels")

def geographic_distribution():
    """Show ship distribution by region"""
    print("\n" + "="*60)
    print("GEOGRAPHIC DISTRIBUTION")
    print("="*60)

    regions = {
        "Arabian Sea": {"lat": (10, 25), "lon": (55, 75)},
        "Bay of Bengal": {"lat": (5, 22), "lon": (80, 95)},
        "Indian West Coast": {"lat": (8, 23), "lon": (68, 77)},
        "Indian East Coast": {"lat": (8, 22), "lon": (77, 88)},
        "Sri Lanka": {"lat": (5, 12), "lon": (78, 85)},
    }

    region_counts = defaultdict(set)

    messages = r.xrevrange("maritime:ais-positions", count=10000)

    for msg_id, data in messages:
        lat = float(data.get(b"latitude", b"0").decode())
        lon = float(data.get(b"longitude", b"0").decode())
        mmsi = data.get(b"mmsi", b"?").decode()

        for region, bounds in regions.items():
            if bounds["lat"][0] <= lat <= bounds["lat"][1] and \
               bounds["lon"][0] <= lon <= bounds["lon"][1]:
                region_counts[region].add(mmsi)

    for region, mmsis in sorted(region_counts.items(), key=lambda x: -len(x[1])):
        print(f"  {region:<20}: {len(mmsis)} vessels")

def track_single_ship(mmsi_pattern="MOCK000001"):
    """Track a single ship's movement history"""
    print("\n" + "="*60)
    print(f"TRACKING: {mmsi_pattern}")
    print("="*60)

    positions = []
    messages = r.xrevrange("maritime:ais-positions", count=100000)

    for msg_id, data in messages:
        mmsi = data.get(b"mmsi", b"?").decode()
        if mmsi == mmsi_pattern:
            positions.append({
                "lat": float(data.get(b"latitude", b"0").decode()),
                "lon": float(data.get(b"longitude", b"0").decode()),
                "speed": float(data.get(b"speed_knots", b"0").decode()),
                "time": data.get(b"timestamp", b"?").decode()[:19]
            })

    print(f"Found {len(positions)} positions")

    # Show first and last 5
    if positions:
        print("\nLatest positions:")
        for p in positions[:5]:
            print(f"  {p['time']} | {p['lat']:.4f}, {p['lon']:.4f} | {p['speed']:.1f} kn")

        if len(positions) > 10:
            print("  ...")
            print("\nEarliest positions:")
            for p in positions[-5:]:
                print(f"  {p['time']} | {p['lat']:.4f}, {p['lon']:.4f} | {p['speed']:.1f} kn")

def main():
    print("\n" + "#"*60)
    print("# MARITIME DATA EXPLORER")
    print("#"*60)

    stream_stats()
    latest_positions(10)
    vessel_type_breakdown()
    geographic_distribution()
    find_speed_anomalies(30)
    track_single_ship("MOCK000001")

if __name__ == "__main__":
    main()
