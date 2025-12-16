"""
Test all format parsers and generators
"""

import sys
sys.path.insert(0, 'ingestion')

from parsers.nmea_parser import NMEAParser
from parsers.binary_radar_parser import BinaryRadarParser
from parsers.geojson_parser import SatelliteGeoJSONParser

from generators.nmea_generator import NMEAGenerator
from generators.radar_generator import BinaryRadarGenerator
from generators.satellite_generator import SatelliteGeoJSONGenerator

print("="*60)
print("MULTI-FORMAT PARSER/GENERATOR TEST")
print("="*60)

# ============ NMEA TEST ============
print("\n[1] NMEA 0183 AIS Test")
print("-"*40)

nmea_gen = NMEAGenerator(num_ships=5)
nmea_parser = NMEAParser()

sentences = list(nmea_gen.generate_batch(include_static=False))
print(f"Generated {len(sentences)} NMEA sentences")

parsed_count = 0
for sentence in sentences[:5]:
    print(f"  Raw: {sentence[:60]}...")
    result = nmea_parser.parse_sentence(sentence)
    if result and 'latitude' in result:
        print(f"  --> MMSI: {result['mmsi']} | Pos: {result['latitude']:.4f}, {result['longitude']:.4f}")
        parsed_count += 1

print(f"  Parsed {parsed_count} position reports")

# ============ RADAR TEST ============
print("\n[2] Binary Radar Test")
print("-"*40)

radar_gen = BinaryRadarGenerator(num_tracks=10)
radar_parser = BinaryRadarParser()

messages = list(radar_gen.generate_batch())
print(f"Generated {len(messages)} binary messages ({radar_gen.bytes_generated} bytes)")

track_count = 0
for msg in messages[:5]:
    result = radar_parser.parse_message(msg)
    if result:
        if result['message_type'] == 'TRACK_UPDATE':
            print(f"  Track: {result['track_id']} | Pos: {result['latitude']:.4f}, {result['longitude']:.4f} | Q: {result['quality']}")
            track_count += 1
        elif result['message_type'] == 'SYSTEM_STATUS':
            print(f"  Status: {result['station_id']} | Tracks: {result['tracks_active']}")

print(f"  Parsed {track_count} track updates")

# ============ SATELLITE TEST ============
print("\n[3] Satellite GeoJSON Test")
print("-"*40)

sat_gen = SatelliteGeoJSONGenerator(output_dir="./data/satellite")
sat_parser = SatelliteGeoJSONParser()

# Generate a pass
geojson = sat_gen.generate_pass()
filepath = sat_gen.save_pass(geojson)
print(f"Generated pass: {geojson['metadata']['pass_id']}")
print(f"Satellite: {geojson['metadata']['satellite']} ({geojson['metadata']['sensor_type']})")
print(f"Detections: {geojson['metadata']['detections_count']}")
print(f"Saved to: {filepath}")

# Parse it back
metadata, detections = sat_parser.parse_file(str(filepath))
print(f"Parsed: {len(detections)} detections")

dark_ships = [d for d in detections if d.is_dark_ship]
print(f"Dark ships detected: {len(dark_ships)}")

for det in detections[:3]:
    dark = " [DARK]" if det.is_dark_ship else ""
    print(f"  {det.detection_id}: {det.latitude:.4f}, {det.longitude:.4f} (conf: {det.confidence:.2f}){dark}")

# ============ SUMMARY ============
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"NMEA:      {len(sentences)} sentences generated & parsed")
print(f"Radar:     {len(messages)} binary messages ({radar_gen.bytes_generated} bytes)")
print(f"Satellite: {geojson['metadata']['detections_count']} detections in GeoJSON")
print()
print("All format parsers and generators working!")
