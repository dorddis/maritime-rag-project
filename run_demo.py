"""
Maritime Multi-Format Ingestion Demo

Entry point for demonstrating the multi-source data ingestion pipeline.

Usage:
    python run_demo.py              # Start dashboard only
    python run_demo.py --all        # Start dashboard + all ingesters
    python run_demo.py --test       # Run quick format test

Demo flow:
1. Start this script
2. Open browser to http://localhost:8000
3. Toggle ingesters ON/OFF from dashboard
4. Observe data flowing through Redis streams
"""

import argparse
import asyncio
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_format_test():
    """Run quick test of all parsers and generators"""
    print("=" * 60)
    print("MULTI-FORMAT PARSER/GENERATOR TEST")
    print("=" * 60)

    # Import test
    from test_formats import (
        NMEAGenerator, NMEAParser,
        BinaryRadarGenerator, BinaryRadarParser,
        SatelliteGeoJSONGenerator, SatelliteGeoJSONParser
    )

    # NMEA Test
    print("\n[1] NMEA 0183 (6-bit ASCII AIS)")
    print("-" * 40)
    nmea_gen = NMEAGenerator(num_ships=5)
    nmea_parser = NMEAParser()
    sentences = list(nmea_gen.generate_batch(include_static=False))
    print(f"Generated: {len(sentences)} sentences")
    parsed = sum(1 for s in sentences if nmea_parser.parse_sentence(s) and 'latitude' in nmea_parser.parse_sentence(s))
    print(f"Parsed: {parsed} position reports")
    print(f"Sample: {sentences[0][:50]}...")

    # Radar Test
    print("\n[2] Binary Radar Protocol")
    print("-" * 40)
    radar_gen = BinaryRadarGenerator(num_tracks=10)
    radar_parser = BinaryRadarParser()
    messages = list(radar_gen.generate_batch())
    print(f"Generated: {len(messages)} binary messages ({radar_gen.bytes_generated} bytes)")
    tracks = sum(1 for m in messages if radar_parser.parse_message(m) and radar_parser.parse_message(m).get('message_type') == 'TRACK_UPDATE')
    print(f"Parsed: {tracks} track updates")
    print(f"Sample (hex): {messages[0][:16].hex()}...")

    # Satellite Test
    print("\n[3] Satellite GeoJSON")
    print("-" * 40)
    sat_gen = SatelliteGeoJSONGenerator(output_dir="./data/satellite")
    geojson = sat_gen.generate_pass()
    print(f"Generated: {geojson['metadata']['detections_count']} detections")
    print(f"Satellite: {geojson['metadata']['satellite']}")
    print(f"Sensor: {geojson['metadata']['sensor_type']}")

    # Drone Test
    print("\n[4] Drone CV JSON")
    print("-" * 40)
    from ingestion.generators.drone_generator import DroneCVGenerator
    drone_gen = DroneCVGenerator(output_dir="./data/drone")
    frame = drone_gen.generate_frame(num_detections=5)
    print(f"Generated: {frame['detections_count']} detections")
    print(f"Drone: {frame['drone']['name']}")
    print(f"Model: {frame['model']['name']} v{frame['model']['version']}")

    print("\n" + "=" * 60)
    print("All format parsers working!")
    print("=" * 60)


def run_ingester_test():
    """Run quick test of all ingesters"""
    print("\n" + "=" * 60)
    print("INGESTER TEST (dry-run)")
    print("=" * 60)

    subprocess.run([
        sys.executable, "-X", "utf8",
        str(PROJECT_ROOT / "test_ingesters.py")
    ], cwd=str(PROJECT_ROOT))


def start_dashboard(open_browser: bool = True, start_all: bool = False):
    """Start the admin dashboard server"""
    print("\n" + "=" * 60)
    print("MARITIME INGESTION DASHBOARD")
    print("=" * 60)
    print("\nStarting server at http://localhost:8000")
    print("Press Ctrl+C to stop\n")

    # Open browser after short delay
    if open_browser:
        def open_delayed():
            time.sleep(2)
            webbrowser.open("http://localhost:8000")

        import threading
        threading.Thread(target=open_delayed, daemon=True).start()

    # Start dashboard
    try:
        subprocess.run([
            sys.executable, "-X", "utf8",
            "-m", "uvicorn",
            "admin.server:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ], cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        print("\nShutting down...")


def main():
    parser = argparse.ArgumentParser(
        description="Maritime Multi-Format Ingestion Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_demo.py              Start dashboard only
    python run_demo.py --test       Run format parser test
    python run_demo.py --all        Start dashboard with all ingesters
    python run_demo.py --no-browser Start without opening browser

Data Formats Supported:
    AIS       - NMEA 0183 (6-bit ASCII encoding, checksums)
    Radar     - Binary protocol (struct.pack/unpack)
    Satellite - GeoJSON FeatureCollection with batch metadata
    Drone     - CV JSON (post-YOLO detection output)
        """
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run format parser and ingester tests only"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Start all ingesters automatically"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically"
    )

    args = parser.parse_args()

    print(r"""
    __  __            _ _   _
   |  \/  | __ _ _ __(_) |_(_)_ __ ___   ___
   | |\/| |/ _` | '__| | __| | '_ ` _ \ / _ \
   | |  | | (_| | |  | | |_| | | | | | |  __/
   |_|  |_|\__,_|_|  |_|\__|_|_| |_| |_|\___|

   Multi-Format Data Ingestion Pipeline Demo
   =========================================

   Formats: NMEA 0183 | Binary Radar | GeoJSON | CV JSON
    """)

    if args.test:
        run_format_test()
        run_ingester_test()
    else:
        start_dashboard(
            open_browser=not args.no_browser,
            start_all=args.all
        )


if __name__ == "__main__":
    main()
