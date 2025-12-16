"""
Binary Radar Message Generator

Generates binary radar track messages for testing.
Compatible with binary_radar_parser.py

Protocol matches the parser's expected format:
- Header: 8 bytes (msg_type, length, timestamp)
- Body: Variable based on message type
"""

import struct
import random
import math
from typing import List, Generator, Optional
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RadarStation:
    """Radar station configuration"""
    station_id: str
    name: str
    latitude: float
    longitude: float
    range_nm: float  # Detection range in nautical miles
    rotation_rpm: float = 15.0  # Antenna rotation speed


@dataclass
class RadarTrack:
    """Tracked target (may or may not be a real ship)"""
    track_id: int
    latitude: float
    longitude: float
    speed: float  # knots
    course: float  # degrees
    rcs: float  # Radar cross section in square meters
    first_seen: datetime
    is_real_ship: bool = True  # False for noise/clutter


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in nautical miles"""
    R = 3440.065  # Earth radius in nm
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2 in degrees"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


class BinaryRadarGenerator:
    """
    Generate binary radar messages.

    Simulates multiple coastal radar stations tracking ships.
    """

    # Message type constants (match parser)
    MSG_TRACK_UPDATE = 0x0100
    MSG_TRACK_LOST = 0x0101
    MSG_SYSTEM_STATUS = 0x0200
    MSG_HEARTBEAT = 0x0300

    # Default radar stations (Indian coastal) - 7 stations covering major ports
    DEFAULT_STATIONS = [
        RadarStation("RAD-MUM", "Mumbai Coastal", 18.94, 72.84, 50),
        RadarStation("RAD-CHN", "Chennai Coastal", 13.08, 80.27, 50),
        RadarStation("RAD-KOC", "Kochi Coastal", 9.93, 76.27, 40),
        RadarStation("RAD-VIZ", "Vizag Naval", 17.69, 83.22, 80),
        RadarStation("RAD-KAR", "Karwar Naval", 14.81, 74.13, 60),
        RadarStation("RAD-KOL", "Kolkata Port", 22.55, 88.35, 45),
        RadarStation("RAD-TUT", "Tuticorin Coastal", 8.76, 78.13, 40),
    ]

    def __init__(self, stations: Optional[List[RadarStation]] = None, num_tracks: int = 100):
        self.stations = stations or self.DEFAULT_STATIONS
        self.tracks: List[RadarTrack] = []
        self.num_tracks = num_tracks
        self.message_count = 0
        self.bytes_generated = 0
        self._generate_tracks()

    def _generate_tracks(self):
        """Generate initial radar tracks (ships) - positioned near radar stations"""
        for i in range(self.num_tracks):
            # Place tracks near random radar station for guaranteed detection
            station = random.choice(self.stations)
            # Position within station range
            angle = random.uniform(0, 2 * math.pi)
            distance_deg = random.uniform(0.1, station.range_nm / 60 * 0.8)  # Within 80% of range

            track = RadarTrack(
                track_id=i + 1,
                latitude=station.latitude + distance_deg * math.cos(angle),
                longitude=station.longitude + distance_deg * math.sin(angle),
                speed=random.uniform(5, 20),
                course=random.uniform(0, 360),
                rcs=random.uniform(10, 1000),  # m^2
                first_seen=datetime.now(timezone.utc),
                is_real_ship=random.random() > 0.05  # 5% are clutter
            )
            self.tracks.append(track)

    def _move_track(self, track: RadarTrack, seconds: float = 1.0):
        """Update track position"""
        distance_nm = (track.speed * seconds) / 3600
        distance_deg = distance_nm / 60

        rad_course = math.radians(track.course)
        track.latitude += distance_deg * math.cos(rad_course)
        track.longitude += distance_deg * math.sin(rad_course) / math.cos(math.radians(track.latitude))

        # Boundary reflection
        if track.latitude < 5 or track.latitude > 25:
            track.course = 180 - track.course
            track.latitude = max(5, min(25, track.latitude))
        if track.longitude < 65 or track.longitude > 100:
            track.course = -track.course
            track.longitude = max(65, min(100, track.longitude))

        track.course = track.course % 360

        # Random adjustments
        if random.random() < 0.02:
            track.course += random.uniform(-10, 10)
            track.speed += random.uniform(-1, 1)
            track.speed = max(2, min(30, track.speed))

    def generate_track_update(
        self,
        station: RadarStation,
        track: RadarTrack,
        timestamp: Optional[datetime] = None
    ) -> bytes:
        """
        Generate binary track update message.

        Format (34 bytes):
        - Header (8 bytes): type(2), length(2), timestamp(4)
        - Body (26 bytes): track_id(4), lat(4), lon(4), speed(2), course(2),
                          rcs(4), range(2), bearing(2), quality(1), reserved(1)
        """
        ts = timestamp or datetime.now(timezone.utc)
        ts_epoch = int(ts.timestamp())

        # Calculate range and bearing from station
        range_nm = haversine_distance(
            station.latitude, station.longitude,
            track.latitude, track.longitude
        )
        bearing = calculate_bearing(
            station.latitude, station.longitude,
            track.latitude, track.longitude
        )

        # Add radar measurement noise
        lat_noisy = track.latitude + random.uniform(-0.005, 0.005)
        lon_noisy = track.longitude + random.uniform(-0.005, 0.005)
        speed_noisy = track.speed + random.uniform(-0.5, 0.5)
        course_noisy = track.course + random.uniform(-2, 2)

        # Convert RCS to dBsm
        rcs_dbsm = 10 * math.log10(track.rcs) if track.rcs > 0 else -10

        # Calculate quality based on range (further = lower quality)
        quality = int(100 * (1 - range_nm / station.range_nm))
        quality = max(50, min(95, quality + random.randint(-10, 10)))

        # Pack message
        header = struct.pack('>HHI',
            self.MSG_TRACK_UPDATE,  # Message type
            34,                     # Message length
            ts_epoch                # Timestamp
        )

        body = struct.pack('>IiiHHfHHBB',
            track.track_id,
            int(lat_noisy * 1e6),
            int(lon_noisy * 1e6),
            int(speed_noisy * 10),
            int(course_noisy * 10) % 3600,
            rcs_dbsm,
            int(range_nm * 10),
            int(bearing * 10),
            quality,
            0  # Reserved
        )

        message = header + body
        self.message_count += 1
        self.bytes_generated += len(message)

        return message

    def generate_track_lost(
        self,
        station: RadarStation,
        track: RadarTrack,
        reason: int = 0,
        timestamp: Optional[datetime] = None
    ) -> bytes:
        """
        Generate track lost message.

        Format (24 bytes):
        - Header (8 bytes)
        - Body (16 bytes): track_id(4), lat(4), lon(4), reason(1), reserved(3)
        """
        ts = timestamp or datetime.now(timezone.utc)
        ts_epoch = int(ts.timestamp())

        header = struct.pack('>HHI',
            self.MSG_TRACK_LOST,
            24,
            ts_epoch
        )

        body = struct.pack('>IiiBBBB',
            track.track_id,
            int(track.latitude * 1e6),
            int(track.longitude * 1e6),
            reason,
            0, 0, 0  # Reserved
        )

        message = header + body
        self.message_count += 1
        self.bytes_generated += len(message)

        return message

    def generate_system_status(
        self,
        station: RadarStation,
        operational: bool = True,
        tracks_active: int = 0,
        timestamp: Optional[datetime] = None
    ) -> bytes:
        """
        Generate system status message.

        Format (28 bytes):
        - Header (8 bytes)
        - Body (20 bytes): station_id(8), operational(1), tracks(2), rpm(4), reserved(5)
        """
        ts = timestamp or datetime.now(timezone.utc)
        ts_epoch = int(ts.timestamp())

        station_bytes = station.station_id[:8].encode('ascii').ljust(8, b'\x00')

        header = struct.pack('>HHI',
            self.MSG_SYSTEM_STATUS,
            28,
            ts_epoch
        )

        body = struct.pack('>8sBHf5s',
            station_bytes,
            1 if operational else 0,
            tracks_active,
            station.rotation_rpm,
            b'\x00' * 5  # Reserved
        )

        message = header + body
        self.message_count += 1
        self.bytes_generated += len(message)

        return message

    def generate_heartbeat(
        self,
        station: RadarStation,
        timestamp: Optional[datetime] = None
    ) -> bytes:
        """Generate heartbeat message (header only)"""
        ts = timestamp or datetime.now(timezone.utc)
        ts_epoch = int(ts.timestamp())

        message = struct.pack('>HHI',
            self.MSG_HEARTBEAT,
            8,
            ts_epoch
        )

        self.message_count += 1
        self.bytes_generated += len(message)

        return message

    def generate_batch(self) -> Generator[bytes, None, None]:
        """
        Generate a batch of radar messages for all stations and tracks.

        Simulates realistic radar behavior:
        - Each station only sees tracks within range
        - Detection probability decreases with distance
        - Occasional system status messages
        """
        timestamp = datetime.now(timezone.utc)

        for station in self.stations:
            tracks_detected = 0

            # Occasionally send system status
            if random.random() < 0.1:
                yield self.generate_system_status(
                    station,
                    operational=True,
                    tracks_active=len([t for t in self.tracks
                        if haversine_distance(station.latitude, station.longitude,
                                            t.latitude, t.longitude) < station.range_nm]),
                    timestamp=timestamp
                )

            for track in self.tracks:
                # Move track
                self._move_track(track)

                # Check if in range
                distance = haversine_distance(
                    station.latitude, station.longitude,
                    track.latitude, track.longitude
                )

                if distance > station.range_nm:
                    continue

                # Detection probability decreases with distance
                detection_prob = (1 - distance / station.range_nm) * 0.95
                if track.rcs < 50:  # Small targets harder to detect
                    detection_prob *= 0.7

                if random.random() > detection_prob:
                    continue

                yield self.generate_track_update(station, track, timestamp)
                tracks_detected += 1

                # Occasionally lose a track
                if random.random() < 0.01:
                    yield self.generate_track_lost(station, track, reason=0, timestamp=timestamp)

    def get_stats(self) -> dict:
        """Get generator statistics"""
        return {
            "stations": len(self.stations),
            "tracks": len(self.tracks),
            "messages_generated": self.message_count,
            "bytes_generated": self.bytes_generated,
        }


# Demo/test
if __name__ == "__main__":
    generator = BinaryRadarGenerator(num_tracks=20)

    print("Binary Radar Generator Demo")
    print("="*60)

    # Generate batch
    messages = list(generator.generate_batch())

    print(f"\nGenerated {len(messages)} binary messages")
    print(f"Stats: {generator.get_stats()}")

    # Show hex of first few messages
    print("\nSample messages (hex):")
    for msg in messages[:3]:
        print(f"  {msg.hex()} ({len(msg)} bytes)")

    # Verify with parser
    print("\n" + "="*60)
    print("Verification with Parser:")

    import sys
    sys.path.insert(0, '..')
    from parsers.binary_radar_parser import BinaryRadarParser

    parser = BinaryRadarParser()
    for msg in messages[:5]:
        result = parser.parse_message(msg)
        if result and result.get('message_type') == 'TRACK_UPDATE':
            print(f"  Track: {result['track_id']} | "
                  f"Pos: {result['latitude']:.4f}, {result['longitude']:.4f} | "
                  f"Quality: {result['quality']}")
