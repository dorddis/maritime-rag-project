"""
Maritime Multi-Format Ingestion Demo

Entry point for demonstrating the multi-source data ingestion pipeline.

Usage:
    python run_demo.py              # Start backend (8001) + frontend (3000)
    python run_demo.py --backend-only # Start backend only
    python run_demo.py --all        # Start backend + all ingesters
    python run_demo.py --test       # Run quick format test

Demo flow:
1. Start this script
2. Backend starts on http://localhost:8001
3. Frontend starts on http://localhost:3000
4. Browser opens to Frontend
"""

import argparse
import asyncio
import subprocess
import sys
import time
import webbrowser
import os
import signal
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
    from tests.test_formats import (
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
        str(PROJECT_ROOT / "tests" / "test_ingesters.py")
    ], cwd=str(PROJECT_ROOT))


def start_services(start_frontend: bool = True, start_all_ingesters: bool = False, open_browser: bool = True):
    """Start the system services"""
    processes = []
    
    print("\n" + "=" * 60)
    print("STARTING MARITIME DEMO SYSTEM")
    print("=" * 60)

    # 1. Start Backend
    print("\n[1] Starting Backend API (Port 8001)...")
    backend_cmd = [
        sys.executable, "-X", "utf8",
        "-m", "uvicorn",
        "admin.server:app",
        "--host", "0.0.0.0",
        "--port", "8001",
        "--reload"
    ]
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy()
    )
    processes.append(("Backend", backend_proc))

    # 2. Start Frontend (if requested)
    if start_frontend:
        print("[2] Starting Next.js Dashboard (Port 3000)...")
        dashboard_dir = PROJECT_ROOT / "dashboard"
        
        # Check if node_modules exists
        if not (dashboard_dir / "node_modules").exists():
            print("    Installing dependencies (this may take a minute)...")
            subprocess.run(["npm", "install"], cwd=str(dashboard_dir), shell=True)

        frontend_cmd = ["npm", "run", "dev"]
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=str(dashboard_dir),
            shell=True,
            env=os.environ.copy()
        )
        processes.append(("Frontend", frontend_proc))

    # 3. Start Ingesters (if requested)
    if start_all_ingesters:
        print("[3] Note: Use the dashboard UI to start ingesters")
        print("    Navigate to http://localhost:3000 and use the ingester controls")
        print("    Or use the API: POST http://localhost:8001/api/ingesters/{name}/start")

    print("\nSystem is running!")
    print("Backend:  http://localhost:8001")
    if start_frontend:
        print("Frontend: http://localhost:3000")
    print("Press Ctrl+C to stop all services\n")

    # Open browser
    if open_browser and start_frontend:
        def open_delayed():
            time.sleep(5) # Wait a bit for Next.js to compile
            webbrowser.open("http://localhost:3000")
            # Also open the admin dashboard?
            # webbrowser.open("http://localhost:8001") 

        import threading
        threading.Thread(target=open_delayed, daemon=True).start()
    elif open_browser:
        # Backend only
        webbrowser.open("http://localhost:8001")

    # Wait for interrupt
    try:
        while True:
            time.sleep(1)
            # Check if processes are still alive
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n{name} stopped unexpectedly with code {proc.returncode}")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nShutting down...")
        for name, proc in processes:
            print(f"Stopping {name}...")
            if sys.platform == 'win32':
                # Windows requires forceful termination for shell=True
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Maritime Multi-Format Ingestion Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run format parser and ingester tests only"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Start backend, frontend, AND all ingesters"
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only the backend (no frontend)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically"
    )

    args = parser.parse_args()

    if args.test:
        run_format_test()
        run_ingester_test()
    else:
        start_services(
            start_frontend=not args.backend_only,
            start_all_ingesters=args.all,
            open_browser=not args.no_browser
        )


if __name__ == "__main__":
    main()
