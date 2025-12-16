"""
NMEA 0183 AIS Message Parser

Parses real AIS messages in NMEA 0183 format.
Demonstrates understanding of:
- 6-bit ASCII encoding (armoring)
- Bit-level message parsing
- Multi-sentence message reassembly
- Checksum validation

Format: !AIVDM,1,1,,A,15NG6V0P01PrRcsQVCoP8ch2089h,0*30
        |     | | || |                            | |
        |     | | || |                            | +-- Checksum (XOR)
        |     | | || |                            +---- Fill bits
        |     | | || +--------------------------------- Payload (6-bit ASCII)
        |     | | |+----------------------------------- Radio channel
        |     | | +------------------------------------ Sequential message ID
        |     | +-------------------------------------- Sentence number
        |     +---------------------------------------- Total sentences
        +---------------------------------------------- Talker ID

Reference: https://gpsd.gitlab.io/gpsd/AIVDM.html
"""

from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class AISPosition:
    """Parsed AIS position report"""
    message_type: int
    mmsi: int
    nav_status: int
    rate_of_turn: Optional[float]
    speed_over_ground: float  # knots
    position_accuracy: bool
    longitude: float
    latitude: float
    course_over_ground: float
    true_heading: Optional[int]
    timestamp_seconds: int
    raw_sentence: str


@dataclass
class AISStaticData:
    """Parsed AIS static/voyage data (Type 5)"""
    message_type: int
    mmsi: int
    imo: int
    callsign: str
    ship_name: str
    ship_type: int
    dimension_bow: int
    dimension_stern: int
    dimension_port: int
    dimension_starboard: int
    eta_month: int
    eta_day: int
    eta_hour: int
    eta_minute: int
    draught: float
    destination: str
    raw_sentence: str


class NMEAParser:
    """
    NMEA 0183 AIS Message Parser

    Handles 6-bit ASCII decoding and message type parsing.
    Supports message types 1, 2, 3 (position reports) and 5 (static data).
    """

    # 6-bit ASCII armoring table
    # Characters 0-39 map to values 0-39
    # Characters 40-63 map to values 48-87 (with gap)
    ARMOR_TABLE = {
        '0': 0,  '1': 1,  '2': 2,  '3': 3,  '4': 4,  '5': 5,  '6': 6,  '7': 7,
        '8': 8,  '9': 9,  ':': 10, ';': 11, '<': 12, '=': 13, '>': 14, '?': 15,
        '@': 16, 'A': 17, 'B': 18, 'C': 19, 'D': 20, 'E': 21, 'F': 22, 'G': 23,
        'H': 24, 'I': 25, 'J': 26, 'K': 27, 'L': 28, 'M': 29, 'N': 30, 'O': 31,
        'P': 32, 'Q': 33, 'R': 34, 'S': 35, 'T': 36, 'U': 37, 'V': 38, 'W': 39,
        '`': 40, 'a': 41, 'b': 42, 'c': 43, 'd': 44, 'e': 45, 'f': 46, 'g': 47,
        'h': 48, 'i': 49, 'j': 50, 'k': 51, 'l': 52, 'm': 53, 'n': 54, 'o': 55,
        'p': 56, 'q': 57, 'r': 58, 's': 59, 't': 60, 'u': 61, 'v': 62, 'w': 63,
    }

    # Navigation status codes
    NAV_STATUS = {
        0: "Under way using engine",
        1: "At anchor",
        2: "Not under command",
        3: "Restricted manoeuverability",
        4: "Constrained by draught",
        5: "Moored",
        6: "Aground",
        7: "Engaged in fishing",
        8: "Under way sailing",
        9: "Reserved for HSC",
        10: "Reserved for WIG",
        11: "Reserved",
        12: "Reserved",
        13: "Reserved",
        14: "AIS-SART active",
        15: "Not defined",
    }

    # Ship type codes (simplified)
    SHIP_TYPES = {
        0: "Not available",
        20: "WIG",
        30: "Fishing",
        31: "Towing",
        32: "Towing large",
        33: "Dredging",
        34: "Diving ops",
        35: "Military ops",
        36: "Sailing",
        37: "Pleasure craft",
        40: "HSC",
        50: "Pilot vessel",
        51: "SAR",
        52: "Tug",
        53: "Port tender",
        54: "Anti-pollution",
        55: "Law enforcement",
        60: "Passenger",
        70: "Cargo",
        80: "Tanker",
        90: "Other",
    }

    def __init__(self):
        self.multi_sentence_buffer: Dict[str, List[str]] = {}

    def validate_checksum(self, sentence: str) -> bool:
        """
        Validate NMEA checksum.
        Checksum is XOR of all characters between ! and *
        """
        if '*' not in sentence:
            return False

        try:
            # Split at checksum
            if sentence.startswith('!') or sentence.startswith('$'):
                data = sentence[1:sentence.index('*')]
            else:
                data = sentence[:sentence.index('*')]

            expected_checksum = sentence[sentence.index('*')+1:sentence.index('*')+3]

            # Calculate XOR checksum
            calculated = 0
            for char in data:
                calculated ^= ord(char)

            return calculated == int(expected_checksum, 16)
        except (ValueError, IndexError):
            return False

    def decode_payload(self, payload: str, fill_bits: int = 0) -> List[int]:
        """
        Decode 6-bit ASCII payload to list of bits.

        Each character maps to 6 bits using the armor table.
        """
        bits = []

        for char in payload:
            if char not in self.ARMOR_TABLE:
                continue
            value = self.ARMOR_TABLE[char]
            # Convert to 6 bits (MSB first)
            for i in range(5, -1, -1):
                bits.append((value >> i) & 1)

        # Remove fill bits from end
        if fill_bits > 0:
            bits = bits[:-fill_bits]

        return bits

    def extract_unsigned(self, bits: List[int], start: int, length: int) -> int:
        """Extract unsigned integer from bit array"""
        value = 0
        for i in range(length):
            if start + i < len(bits):
                value = (value << 1) | bits[start + i]
        return value

    def extract_signed(self, bits: List[int], start: int, length: int) -> int:
        """Extract signed integer (two's complement) from bit array"""
        value = self.extract_unsigned(bits, start, length)
        # Check sign bit
        if value & (1 << (length - 1)):
            value -= (1 << length)
        return value

    def extract_string(self, bits: List[int], start: int, length: int) -> str:
        """
        Extract 6-bit ASCII string from bit array.
        Each character is 6 bits.
        """
        result = []
        num_chars = length // 6

        for i in range(num_chars):
            char_value = self.extract_unsigned(bits, start + i * 6, 6)
            # Convert 6-bit value to ASCII
            if char_value < 32:
                char_value += 64  # @ A B C ...
            if 32 <= char_value < 64:
                result.append(chr(char_value))
            elif char_value == 0:
                result.append('@')  # Represents space in AIS
            else:
                result.append(chr(char_value))

        return ''.join(result).strip('@').strip()

    def parse_sentence(self, sentence: str) -> Optional[Dict]:
        """
        Parse a single NMEA sentence.
        Returns parsed data or None if invalid/incomplete.
        """
        sentence = sentence.strip()

        # Validate checksum
        if not self.validate_checksum(sentence):
            return None

        # Parse sentence structure
        # !AIVDM,1,1,,A,payload,fill_bits*checksum
        try:
            parts = sentence.split(',')
            if len(parts) < 7:
                return None

            talker = parts[0]  # !AIVDM or !AIVDO
            total_sentences = int(parts[1])
            sentence_num = int(parts[2])
            seq_id = parts[3]  # Sequential message ID (for multi-sentence)
            channel = parts[4]  # A or B
            payload = parts[5]
            fill_checksum = parts[6]
            fill_bits = int(fill_checksum.split('*')[0])

            # Handle multi-sentence messages
            if total_sentences > 1:
                return self._handle_multi_sentence(
                    seq_id, total_sentences, sentence_num,
                    payload, fill_bits, sentence
                )

            # Single sentence message
            return self._parse_payload(payload, fill_bits, sentence)

        except (ValueError, IndexError) as e:
            return None

    def _handle_multi_sentence(
        self,
        seq_id: str,
        total: int,
        current: int,
        payload: str,
        fill_bits: int,
        sentence: str
    ) -> Optional[Dict]:
        """Handle multi-sentence message reassembly"""

        key = seq_id or "default"

        if key not in self.multi_sentence_buffer:
            self.multi_sentence_buffer[key] = [''] * total

        self.multi_sentence_buffer[key][current - 1] = payload

        # Check if all sentences received
        if all(self.multi_sentence_buffer[key]):
            combined_payload = ''.join(self.multi_sentence_buffer[key])
            del self.multi_sentence_buffer[key]
            return self._parse_payload(combined_payload, fill_bits, sentence)

        return None  # Still waiting for more sentences

    def _parse_payload(self, payload: str, fill_bits: int, raw_sentence: str) -> Optional[Dict]:
        """Parse the decoded payload based on message type"""

        bits = self.decode_payload(payload, fill_bits)

        if len(bits) < 6:
            return None

        message_type = self.extract_unsigned(bits, 0, 6)

        if message_type in [1, 2, 3]:
            return self._parse_position_report(bits, message_type, raw_sentence)
        elif message_type == 5:
            return self._parse_static_data(bits, raw_sentence)
        elif message_type == 18:
            return self._parse_class_b_position(bits, raw_sentence)
        else:
            return {"message_type": message_type, "raw": raw_sentence}

    def _parse_position_report(self, bits: List[int], msg_type: int, raw: str) -> Dict:
        """
        Parse Message Type 1, 2, 3: Class A Position Report

        Bit layout:
        0-5:    Message Type
        6-7:    Repeat Indicator
        8-37:   MMSI (30 bits)
        38-41:  Navigation Status
        42-49:  Rate of Turn
        50-59:  Speed Over Ground (1/10 knot steps)
        60:     Position Accuracy
        61-88:  Longitude (1/10000 min, signed)
        89-115: Latitude (1/10000 min, signed)
        116-127: Course Over Ground (1/10 degree)
        128-136: True Heading (degrees)
        137-142: Time Stamp (seconds)
        """

        mmsi = self.extract_unsigned(bits, 8, 30)
        nav_status = self.extract_unsigned(bits, 38, 4)

        # Rate of turn (special encoding)
        rot_raw = self.extract_signed(bits, 42, 8)
        if rot_raw == -128:
            rot = None  # Not available
        else:
            rot = (rot_raw / 4.733) ** 2
            if rot_raw < 0:
                rot = -rot

        sog = self.extract_unsigned(bits, 50, 10) / 10.0  # Speed in knots
        if sog >= 102.2:
            sog = None  # Not available

        pos_accuracy = bool(self.extract_unsigned(bits, 60, 1))

        # Longitude: 1/10000 min, signed, divide by 600000 for degrees
        lon_raw = self.extract_signed(bits, 61, 28)
        longitude = lon_raw / 600000.0

        # Latitude: 1/10000 min, signed
        lat_raw = self.extract_signed(bits, 89, 27)
        latitude = lat_raw / 600000.0

        # Course over ground
        cog = self.extract_unsigned(bits, 116, 12) / 10.0
        if cog >= 360.0:
            cog = None

        # True heading
        heading = self.extract_unsigned(bits, 128, 9)
        if heading >= 511:
            heading = None

        timestamp = self.extract_unsigned(bits, 137, 6)

        return {
            "message_type": msg_type,
            "mmsi": mmsi,
            "nav_status": nav_status,
            "nav_status_text": self.NAV_STATUS.get(nav_status, "Unknown"),
            "rate_of_turn": rot,
            "speed_over_ground": sog,
            "position_accuracy": pos_accuracy,
            "longitude": longitude,
            "latitude": latitude,
            "course_over_ground": cog,
            "true_heading": heading,
            "timestamp_seconds": timestamp,
            "raw_sentence": raw
        }

    def _parse_static_data(self, bits: List[int], raw: str) -> Dict:
        """
        Parse Message Type 5: Static and Voyage Related Data

        424 bits total (requires 2 sentences)
        """

        if len(bits) < 424:
            return {"message_type": 5, "error": "incomplete", "raw": raw}

        mmsi = self.extract_unsigned(bits, 8, 30)
        ais_version = self.extract_unsigned(bits, 38, 2)
        imo = self.extract_unsigned(bits, 40, 30)
        callsign = self.extract_string(bits, 70, 42)
        ship_name = self.extract_string(bits, 112, 120)
        ship_type = self.extract_unsigned(bits, 232, 8)

        dim_bow = self.extract_unsigned(bits, 240, 9)
        dim_stern = self.extract_unsigned(bits, 249, 9)
        dim_port = self.extract_unsigned(bits, 258, 6)
        dim_starboard = self.extract_unsigned(bits, 264, 6)

        eta_month = self.extract_unsigned(bits, 274, 4)
        eta_day = self.extract_unsigned(bits, 278, 5)
        eta_hour = self.extract_unsigned(bits, 283, 5)
        eta_minute = self.extract_unsigned(bits, 288, 6)

        draught = self.extract_unsigned(bits, 294, 8) / 10.0  # meters
        destination = self.extract_string(bits, 302, 120)

        return {
            "message_type": 5,
            "mmsi": mmsi,
            "imo": imo,
            "callsign": callsign,
            "ship_name": ship_name,
            "ship_type": ship_type,
            "ship_type_text": self.SHIP_TYPES.get(ship_type // 10 * 10, "Unknown"),
            "dimension_bow": dim_bow,
            "dimension_stern": dim_stern,
            "dimension_port": dim_port,
            "dimension_starboard": dim_starboard,
            "length": dim_bow + dim_stern,
            "width": dim_port + dim_starboard,
            "eta_month": eta_month,
            "eta_day": eta_day,
            "eta_hour": eta_hour,
            "eta_minute": eta_minute,
            "draught": draught,
            "destination": destination,
            "raw_sentence": raw
        }

    def _parse_class_b_position(self, bits: List[int], raw: str) -> Dict:
        """Parse Message Type 18: Class B Position Report"""

        mmsi = self.extract_unsigned(bits, 8, 30)
        sog = self.extract_unsigned(bits, 46, 10) / 10.0

        lon_raw = self.extract_signed(bits, 57, 28)
        longitude = lon_raw / 600000.0

        lat_raw = self.extract_signed(bits, 85, 27)
        latitude = lat_raw / 600000.0

        cog = self.extract_unsigned(bits, 112, 12) / 10.0
        heading = self.extract_unsigned(bits, 124, 9)
        if heading >= 511:
            heading = None

        return {
            "message_type": 18,
            "mmsi": mmsi,
            "speed_over_ground": sog,
            "longitude": longitude,
            "latitude": latitude,
            "course_over_ground": cog,
            "true_heading": heading,
            "raw_sentence": raw
        }


# Demo/test
if __name__ == "__main__":
    parser = NMEAParser()

    # Test sentences (real AIS data)
    test_sentences = [
        "!AIVDM,1,1,,A,15N4cJ`005Jrek0H@9n`DW5608EP,0*13",
        "!AIVDM,1,1,,B,13u@pdP01FPG>68H@9sPD0000000,0*6E",
        "!AIVDM,2,1,3,B,55?MbV02>H97ac<H4F220l4r>0Hth00000015>P8824v3FrF;l0Emp@0,0*28",
        "!AIVDM,2,2,3,B,00000000000,2*23",
    ]

    print("NMEA Parser Demo")
    print("="*60)

    for sentence in test_sentences:
        print(f"\nInput: {sentence}")
        result = parser.parse_sentence(sentence)
        if result:
            print(f"Type: {result.get('message_type')}")
            if 'mmsi' in result:
                print(f"MMSI: {result['mmsi']}")
            if 'latitude' in result and result.get('latitude'):
                print(f"Position: {result['latitude']:.6f}, {result['longitude']:.6f}")
            if 'ship_name' in result:
                print(f"Ship: {result['ship_name']}")
            if 'speed_over_ground' in result and result.get('speed_over_ground'):
                print(f"Speed: {result['speed_over_ground']} knots")
