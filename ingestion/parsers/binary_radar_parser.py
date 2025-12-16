"""
Binary Radar Protocol Parser

Parses binary radar track messages (ASTERIX-like format).
Demonstrates understanding of:
- Binary protocol parsing with struct.unpack
- Fixed-length message headers
- Variable message types
- Coordinate encoding at integer precision

Protocol Design (simplified ASTERIX CAT-240):
- Header: 8 bytes (msg_type, length, timestamp)
- Body: Variable based on message type

Message Types:
- 0x0100: Track Update (position, speed, course)
- 0x0101: Track Lost
- 0x0200: System Status
"""

import struct
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum


class RadarMessageType(IntEnum):
    """Radar message type identifiers"""
    TRACK_UPDATE = 0x0100
    TRACK_LOST = 0x0101
    SYSTEM_STATUS = 0x0200
    HEARTBEAT = 0x0300


@dataclass
class RadarTrackUpdate:
    """Parsed radar track update"""
    message_type: RadarMessageType
    timestamp: datetime
    track_id: int
    latitude: float
    longitude: float
    speed_knots: float
    course: float
    rcs_dbsm: float  # Radar Cross Section in dBsm
    range_nm: float  # Distance from radar in nautical miles
    bearing: float  # Angle from radar in degrees
    quality: int  # Detection quality 0-100


@dataclass
class RadarTrackLost:
    """Notification that track is lost"""
    message_type: RadarMessageType
    timestamp: datetime
    track_id: int
    last_latitude: float
    last_longitude: float
    reason: int  # 0=timeout, 1=merged, 2=manual


@dataclass
class RadarSystemStatus:
    """Radar system status message"""
    message_type: RadarMessageType
    timestamp: datetime
    station_id: str
    operational: bool
    tracks_active: int
    rotation_rpm: float


class BinaryRadarParser:
    """
    Binary radar protocol parser.

    Binary Message Structure:
    ========================

    Header (8 bytes):
    - Bytes 0-1: Message Type (uint16, big-endian)
    - Bytes 2-3: Message Length (uint16, big-endian, total bytes)
    - Bytes 4-7: Timestamp (uint32, big-endian, Unix epoch seconds)

    Track Update Body (26 bytes):
    - Bytes 8-11:  Track ID (uint32)
    - Bytes 12-15: Latitude (int32, degrees * 1e6)
    - Bytes 16-19: Longitude (int32, degrees * 1e6)
    - Bytes 20-21: Speed (uint16, knots * 10)
    - Bytes 22-23: Course (uint16, degrees * 10)
    - Bytes 24-27: RCS (float32, dBsm)
    - Bytes 28-29: Range (uint16, nm * 10)
    - Bytes 30-31: Bearing (uint16, degrees * 10)
    - Byte 32:     Quality (uint8, 0-100)
    - Byte 33:     Reserved

    Total Track Update: 34 bytes
    """

    # Message sizes (including header)
    MESSAGE_SIZES = {
        RadarMessageType.TRACK_UPDATE: 34,
        RadarMessageType.TRACK_LOST: 24,
        RadarMessageType.SYSTEM_STATUS: 28,
        RadarMessageType.HEARTBEAT: 8,
    }

    # Track lost reason codes
    LOST_REASONS = {
        0: "Timeout",
        1: "Merged with another track",
        2: "Manual deletion",
        3: "Out of range",
    }

    def __init__(self, station_id: str = "RAD-001"):
        self.station_id = station_id
        self.bytes_parsed = 0
        self.messages_parsed = 0

    def parse_header(self, data: bytes) -> Tuple[RadarMessageType, int, datetime]:
        """
        Parse 8-byte message header.

        Returns: (message_type, message_length, timestamp)
        """
        if len(data) < 8:
            raise ValueError(f"Header too short: {len(data)} bytes")

        # Unpack header: big-endian uint16, uint16, uint32
        msg_type, msg_len, ts_epoch = struct.unpack('>HHI', data[:8])

        try:
            message_type = RadarMessageType(msg_type)
        except ValueError:
            raise ValueError(f"Unknown message type: 0x{msg_type:04X}")

        timestamp = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

        return message_type, msg_len, timestamp

    def parse_track_update(self, data: bytes) -> RadarTrackUpdate:
        """
        Parse Track Update message (0x0100).

        Format:
        - Header (8 bytes)
        - Body (26 bytes)
        """
        if len(data) < 34:
            raise ValueError(f"Track update too short: {len(data)} bytes")

        # Parse header
        msg_type, msg_len, timestamp = self.parse_header(data)

        # Parse body: track_id(I), lat(i), lon(i), speed(H), course(H), rcs(f), range(H), bearing(H), quality(B), reserved(B)
        (track_id, lat_raw, lon_raw, speed_raw, course_raw,
         rcs, range_raw, bearing_raw, quality, _) = struct.unpack(
            '>IiiHHfHHBB', data[8:34]
        )

        return RadarTrackUpdate(
            message_type=msg_type,
            timestamp=timestamp,
            track_id=track_id,
            latitude=lat_raw / 1e6,
            longitude=lon_raw / 1e6,
            speed_knots=speed_raw / 10.0,
            course=course_raw / 10.0,
            rcs_dbsm=rcs,
            range_nm=range_raw / 10.0,
            bearing=bearing_raw / 10.0,
            quality=quality
        )

    def parse_track_lost(self, data: bytes) -> RadarTrackLost:
        """
        Parse Track Lost message (0x0101).

        Format:
        - Header (8 bytes)
        - Body (16 bytes)
        """
        if len(data) < 24:
            raise ValueError(f"Track lost too short: {len(data)} bytes")

        msg_type, msg_len, timestamp = self.parse_header(data)

        # Parse body: track_id(I), lat(i), lon(i), reason(B), reserved(3B)
        track_id, lat_raw, lon_raw, reason = struct.unpack(
            '>IiiB', data[8:21]
        )

        return RadarTrackLost(
            message_type=msg_type,
            timestamp=timestamp,
            track_id=track_id,
            last_latitude=lat_raw / 1e6,
            last_longitude=lon_raw / 1e6,
            reason=reason
        )

    def parse_system_status(self, data: bytes) -> RadarSystemStatus:
        """
        Parse System Status message (0x0200).

        Format:
        - Header (8 bytes)
        - Body (20 bytes)
        """
        if len(data) < 28:
            raise ValueError(f"System status too short: {len(data)} bytes")

        msg_type, msg_len, timestamp = self.parse_header(data)

        # Parse body: station_id(8s), operational(B), tracks_active(H), rotation_rpm(f), reserved(5B)
        station_bytes, operational, tracks, rpm = struct.unpack(
            '>8sBHf', data[8:23]
        )

        station_id = station_bytes.decode('ascii').strip('\x00')

        return RadarSystemStatus(
            message_type=msg_type,
            timestamp=timestamp,
            station_id=station_id,
            operational=bool(operational),
            tracks_active=tracks,
            rotation_rpm=rpm
        )

    def parse_message(self, data: bytes) -> Optional[Dict]:
        """
        Parse a single binary message.

        Returns dict representation of parsed message, or None if invalid.
        """
        if len(data) < 8:
            return None

        try:
            msg_type, msg_len, timestamp = self.parse_header(data)

            self.bytes_parsed += len(data)
            self.messages_parsed += 1

            if msg_type == RadarMessageType.TRACK_UPDATE:
                track = self.parse_track_update(data)
                return {
                    "message_type": "TRACK_UPDATE",
                    "station_id": self.station_id,
                    "track_id": f"TRK-{track.track_id:08d}",
                    "timestamp": track.timestamp.isoformat(),
                    "latitude": track.latitude,
                    "longitude": track.longitude,
                    "speed_knots": track.speed_knots,
                    "course": track.course,
                    "rcs_dbsm": track.rcs_dbsm,
                    "range_nm": track.range_nm,
                    "bearing": track.bearing,
                    "quality": track.quality,
                }

            elif msg_type == RadarMessageType.TRACK_LOST:
                lost = self.parse_track_lost(data)
                return {
                    "message_type": "TRACK_LOST",
                    "station_id": self.station_id,
                    "track_id": f"TRK-{lost.track_id:08d}",
                    "timestamp": lost.timestamp.isoformat(),
                    "last_latitude": lost.last_latitude,
                    "last_longitude": lost.last_longitude,
                    "reason": self.LOST_REASONS.get(lost.reason, "Unknown"),
                }

            elif msg_type == RadarMessageType.SYSTEM_STATUS:
                status = self.parse_system_status(data)
                return {
                    "message_type": "SYSTEM_STATUS",
                    "station_id": status.station_id,
                    "timestamp": status.timestamp.isoformat(),
                    "operational": status.operational,
                    "tracks_active": status.tracks_active,
                    "rotation_rpm": status.rotation_rpm,
                }

            elif msg_type == RadarMessageType.HEARTBEAT:
                return {
                    "message_type": "HEARTBEAT",
                    "station_id": self.station_id,
                    "timestamp": timestamp.isoformat(),
                }

            return None

        except (struct.error, ValueError) as e:
            return None

    def parse_stream(self, data: bytes) -> List[Dict]:
        """
        Parse a stream of concatenated binary messages.

        Returns list of parsed messages.
        """
        messages = []
        offset = 0

        while offset < len(data):
            # Need at least header to determine message type
            if offset + 8 > len(data):
                break

            try:
                msg_type, msg_len, _ = self.parse_header(data[offset:])

                # Check if we have complete message
                if offset + msg_len > len(data):
                    break

                msg_data = data[offset:offset + msg_len]
                parsed = self.parse_message(msg_data)

                if parsed:
                    messages.append(parsed)

                offset += msg_len

            except ValueError:
                # Skip invalid message, try next byte
                offset += 1

        return messages

    def get_stats(self) -> Dict:
        """Get parser statistics"""
        return {
            "bytes_parsed": self.bytes_parsed,
            "messages_parsed": self.messages_parsed,
            "station_id": self.station_id,
        }


# Demo/test
if __name__ == "__main__":
    import time

    parser = BinaryRadarParser(station_id="RAD-MUM")

    print("Binary Radar Parser Demo")
    print("="*60)

    # Create test track update message
    timestamp = int(time.time())
    track_id = 12345
    lat = int(18.9388 * 1e6)  # Mumbai
    lon = int(72.8354 * 1e6)
    speed = int(12.5 * 10)
    course = int(245.0 * 10)
    rcs = 25.5
    range_nm = int(15.3 * 10)
    bearing = int(90.0 * 10)
    quality = 85

    # Pack the message
    header = struct.pack('>HHI', 0x0100, 34, timestamp)
    body = struct.pack('>IiiHHfHHBB',
        track_id, lat, lon, speed, course, rcs, range_nm, bearing, quality, 0
    )
    test_message = header + body

    print(f"\nTest message ({len(test_message)} bytes):")
    print(f"Hex: {test_message.hex()}")

    # Parse it
    result = parser.parse_message(test_message)

    if result:
        print(f"\nParsed:")
        for key, value in result.items():
            print(f"  {key}: {value}")

    print(f"\nParser stats: {parser.get_stats()}")
