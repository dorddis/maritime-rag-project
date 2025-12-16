"""
NMEA 0183 AIS Message Generator

Generates valid NMEA 0183 AIS sentences for testing.
Demonstrates understanding of:
- 6-bit ASCII encoding
- Bit packing for AIS message types
- Checksum calculation
- Multi-sentence message generation

This generates messages that can be parsed by the nmea_parser.
"""

import random
import math
from typing import List, Optional, Generator
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class MockShip:
    """Mock ship for generating AIS data"""
    mmsi: int
    name: str
    callsign: str
    ship_type: int
    latitude: float
    longitude: float
    speed: float  # knots
    course: float  # degrees
    heading: float  # degrees
    nav_status: int
    length: int
    width: int
    destination: str
    draught: float

    def move(self, seconds: float = 1.0):
        """Update position based on speed and course"""
        # Convert speed (knots) to degrees per second
        distance_nm = (self.speed * seconds) / 3600
        distance_deg = distance_nm / 60

        rad_course = math.radians(self.course)
        self.latitude += distance_deg * math.cos(rad_course)
        self.longitude += distance_deg * math.sin(rad_course) / math.cos(math.radians(self.latitude))

        # Boundary checks (Indian Ocean)
        self.latitude = max(5, min(25, self.latitude))
        self.longitude = max(65, min(100, self.longitude))

        # Random adjustments
        if random.random() < 0.02:
            self.course = (self.course + random.uniform(-10, 10)) % 360
            self.heading = self.course + random.uniform(-5, 5)


class NMEAGenerator:
    """
    Generate valid NMEA 0183 AIS sentences.

    Supports:
    - Message Type 1/2/3: Class A Position Report
    - Message Type 5: Static and Voyage Related Data
    - Message Type 18: Class B Position Report
    """

    # Reverse armor table for encoding
    ENCODE_TABLE = "0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVW`abcdefghijklmnopqrstuvw"

    # Vessel names for mock generation
    VESSEL_NAMES = [
        "EVER GIVEN", "MAERSK ALABAMA", "COSCO SHIPPING", "MSC OSCAR",
        "HANJIN BOSTON", "YANG MING UNITY", "CMA CGM MARCO POLO",
        "OOCL HONG KONG", "HAPAG LLOYD EXPRESS", "PIL ASIA",
        "HYUNDAI MERCHANT", "EVERGREEN MARINE", "MOL TRIUMPH",
        "NYK BLUE JAY", "K LINE CENTURY", "WAN HAI LINES",
    ]

    DESTINATIONS = [
        "MUMBAI", "SINGAPORE", "DUBAI", "COLOMBO", "CHENNAI",
        "SHANGHAI", "HONG KONG", "ROTTERDAM", "JEBEL ALI",
        "PORT KLANG", "TANJUNG PELEPAS", "JAWAHARLAL NEHRU",
    ]

    CALLSIGNS = [
        "VRAA", "VRBB", "VRCC", "VRDD", "VREE", "VRFF", "VRGG",
        "9VAA", "9VBB", "9VCC", "9VDD", "9VEE", "9VFF", "9VGG",
    ]

    def __init__(self, num_ships: int = 100):
        self.ships: List[MockShip] = []
        self.num_ships = num_ships
        self.message_count = 0
        self._generate_fleet()

    def _generate_fleet(self):
        """Generate fleet of mock ships"""
        for i in range(self.num_ships):
            ship_type = random.choice([70, 71, 72, 73, 74, 75, 80, 81, 82, 83, 30, 31, 60])

            ship = MockShip(
                mmsi=random.randint(200000000, 999999999),
                name=random.choice(self.VESSEL_NAMES) + f" {i:03d}",
                callsign=random.choice(self.CALLSIGNS) + str(random.randint(1, 9)),
                ship_type=ship_type,
                latitude=random.uniform(5, 25),
                longitude=random.uniform(65, 100),
                speed=random.uniform(8, 22),
                course=random.uniform(0, 360),
                heading=random.uniform(0, 360),
                nav_status=random.choice([0, 1, 5, 7, 8]),
                length=random.randint(100, 400),
                width=random.randint(15, 60),
                destination=random.choice(self.DESTINATIONS),
                draught=random.uniform(5, 15),
            )
            self.ships.append(ship)

    def _pack_bits(self, values: List[tuple]) -> List[int]:
        """
        Pack values into bit array.

        values: List of (value, num_bits) tuples
        """
        bits = []
        for value, num_bits in values:
            # Handle signed values
            if value < 0:
                value = value + (1 << num_bits)

            for i in range(num_bits - 1, -1, -1):
                bits.append((value >> i) & 1)

        return bits

    def _encode_payload(self, bits: List[int]) -> str:
        """
        Encode bit array to 6-bit ASCII payload.
        """
        # Pad to multiple of 6
        while len(bits) % 6 != 0:
            bits.append(0)

        payload = []
        for i in range(0, len(bits), 6):
            value = 0
            for j in range(6):
                value = (value << 1) | bits[i + j]
            payload.append(self.ENCODE_TABLE[value])

        return ''.join(payload)

    def _encode_string(self, text: str, num_chars: int) -> List[int]:
        """
        Encode string to 6-bit ASCII bits.
        """
        text = text.upper()[:num_chars].ljust(num_chars, '@')
        bits = []

        for char in text:
            if char == ' ' or char == '@':
                value = 0
            elif 'A' <= char <= 'Z':
                value = ord(char) - 64  # A=1, B=2, ...
            elif '0' <= char <= '9':
                value = ord(char) - 48 + 48  # 0=48, 1=49, ...
            else:
                value = 0

            for i in range(5, -1, -1):
                bits.append((value >> i) & 1)

        return bits

    def _calculate_checksum(self, data: str) -> str:
        """Calculate NMEA checksum"""
        checksum = 0
        for char in data:
            checksum ^= ord(char)
        return f"{checksum:02X}"

    def generate_type1(self, ship: MockShip, channel: str = 'A') -> str:
        """
        Generate Type 1 Position Report (Class A).

        168 bits total.
        """
        # Convert coordinates
        lon_val = int(ship.longitude * 600000)
        lat_val = int(ship.latitude * 600000)
        sog = int(ship.speed * 10)
        cog = int(ship.course * 10)
        heading = int(ship.heading) if ship.heading < 511 else 511
        timestamp = datetime.now(timezone.utc).second

        # Rate of turn (simplified - use 128 for not available)
        rot = -128

        bits = self._pack_bits([
            (1, 6),              # Message type
            (0, 2),              # Repeat indicator
            (ship.mmsi, 30),     # MMSI
            (ship.nav_status, 4),  # Navigation status
            (rot & 0xFF, 8),     # Rate of turn (signed)
            (sog, 10),           # Speed over ground
            (1, 1),              # Position accuracy
            (lon_val, 28),       # Longitude
            (lat_val, 27),       # Latitude
            (cog, 12),           # Course over ground
            (heading, 9),        # True heading
            (timestamp, 6),      # Time stamp
            (0, 2),              # Maneuver indicator
            (0, 3),              # Spare
            (1, 1),              # RAIM flag
            (0, 19),             # Radio status
        ])

        payload = self._encode_payload(bits)
        fill_bits = (len(bits) % 6) if len(bits) % 6 != 0 else 0

        # Format sentence
        sentence_data = f"AIVDM,1,1,,{channel},{payload},{fill_bits}"
        checksum = self._calculate_checksum(sentence_data)

        self.message_count += 1
        return f"!{sentence_data}*{checksum}"

    def generate_type5(self, ship: MockShip, channel: str = 'B') -> List[str]:
        """
        Generate Type 5 Static and Voyage Data.

        424 bits total - requires 2 sentences.
        """
        # IMO number (simplified)
        imo = ship.mmsi % 10000000

        # Dimensions
        dim_bow = ship.length // 2
        dim_stern = ship.length - dim_bow
        dim_port = ship.width // 2
        dim_starboard = ship.width - dim_port

        # ETA (random future time)
        eta_month = random.randint(1, 12)
        eta_day = random.randint(1, 28)
        eta_hour = random.randint(0, 23)
        eta_minute = random.randint(0, 59)

        draught = int(ship.draught * 10)

        # Build bit array
        bits = self._pack_bits([
            (5, 6),              # Message type
            (0, 2),              # Repeat indicator
            (ship.mmsi, 30),     # MMSI
            (0, 2),              # AIS version
            (imo, 30),           # IMO number
        ])

        # Add callsign (7 chars = 42 bits)
        bits.extend(self._encode_string(ship.callsign, 7))

        # Add ship name (20 chars = 120 bits)
        bits.extend(self._encode_string(ship.name, 20))

        # Continue with numeric fields
        bits.extend(self._pack_bits([
            (ship.ship_type, 8),   # Ship type
            (dim_bow, 9),         # Dimension to bow
            (dim_stern, 9),       # Dimension to stern
            (dim_port, 6),        # Dimension to port
            (dim_starboard, 6),   # Dimension to starboard
            (1, 4),               # Position fix type (GPS)
            (eta_month, 4),       # ETA month
            (eta_day, 5),         # ETA day
            (eta_hour, 5),        # ETA hour
            (eta_minute, 6),      # ETA minute
            (draught, 8),         # Draught
        ]))

        # Add destination (20 chars = 120 bits)
        bits.extend(self._encode_string(ship.destination, 20))

        # Final fields
        bits.extend(self._pack_bits([
            (0, 1),               # DTE
            (0, 1),               # Spare
        ]))

        # Encode full payload
        payload = self._encode_payload(bits)

        # Split into 2 sentences
        split_point = len(payload) // 2
        payload1 = payload[:split_point]
        payload2 = payload[split_point:]

        # Generate sentences
        seq_id = random.randint(0, 9)

        data1 = f"AIVDM,2,1,{seq_id},{channel},{payload1},0"
        data2 = f"AIVDM,2,2,{seq_id},{channel},{payload2},2"

        checksum1 = self._calculate_checksum(data1)
        checksum2 = self._calculate_checksum(data2)

        self.message_count += 2
        return [
            f"!{data1}*{checksum1}",
            f"!{data2}*{checksum2}"
        ]

    def generate_type18(self, ship: MockShip, channel: str = 'B') -> str:
        """
        Generate Type 18 Class B Position Report.

        168 bits total.
        """
        lon_val = int(ship.longitude * 600000)
        lat_val = int(ship.latitude * 600000)
        sog = int(ship.speed * 10)
        cog = int(ship.course * 10)
        heading = int(ship.heading) if ship.heading < 511 else 511
        timestamp = datetime.now(timezone.utc).second

        bits = self._pack_bits([
            (18, 6),             # Message type
            (0, 2),              # Repeat indicator
            (ship.mmsi, 30),     # MMSI
            (0, 8),              # Reserved
            (sog, 10),           # Speed over ground
            (1, 1),              # Position accuracy
            (lon_val, 28),       # Longitude
            (lat_val, 27),       # Latitude
            (cog, 12),           # Course over ground
            (heading, 9),        # True heading
            (timestamp, 6),      # Time stamp
            (0, 2),              # Regional reserved
            (1, 1),              # CS Unit
            (1, 1),              # Display flag
            (1, 1),              # DSC flag
            (1, 1),              # Band flag
            (1, 1),              # Message 22 flag
            (0, 1),              # Assigned
            (0, 1),              # RAIM flag
            (0, 20),             # Radio status
        ])

        payload = self._encode_payload(bits)
        fill_bits = 0

        sentence_data = f"AIVDM,1,1,,{channel},{payload},{fill_bits}"
        checksum = self._calculate_checksum(sentence_data)

        self.message_count += 1
        return f"!{sentence_data}*{checksum}"

    def generate_batch(self, include_static: bool = True) -> Generator[str, None, None]:
        """
        Generate a batch of NMEA sentences for all ships.

        Yields position reports for each ship, optionally with static data.
        """
        for ship in self.ships:
            # Move ship
            ship.move(1.0)

            # Generate position report (Type 1 or 18)
            if random.random() < 0.9:  # 90% Class A
                yield self.generate_type1(ship)
            else:
                yield self.generate_type18(ship)

            # Occasionally generate static data
            if include_static and random.random() < 0.05:
                for sentence in self.generate_type5(ship):
                    yield sentence

    def get_stats(self) -> dict:
        """Get generator statistics"""
        return {
            "ships": len(self.ships),
            "messages_generated": self.message_count,
        }


# Demo/test
if __name__ == "__main__":
    generator = NMEAGenerator(num_ships=5)

    print("NMEA Generator Demo")
    print("="*60)

    # Generate some sentences
    sentences = list(generator.generate_batch(include_static=True))

    for sentence in sentences[:10]:
        print(sentence)

    print(f"\nGenerated {len(sentences)} sentences")
    print(f"Stats: {generator.get_stats()}")

    # Verify with parser
    print("\n" + "="*60)
    print("Verification with Parser:")

    import sys
    sys.path.insert(0, '..')
    from parsers.nmea_parser import NMEAParser

    parser = NMEAParser()
    for sentence in sentences[:5]:
        result = parser.parse_sentence(sentence)
        if result and 'latitude' in result:
            print(f"  MMSI: {result.get('mmsi')} | "
                  f"Pos: {result.get('latitude', 0):.4f}, {result.get('longitude', 0):.4f}")
