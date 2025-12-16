"""
Drone CV JSON Parser

Parses computer vision detection output from drone surveillance.
Handles YOLO-style detection JSON format.
"""

import json
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class DroneFrameMetadata:
    """Metadata from a drone frame"""
    frame_id: str
    timestamp: datetime
    drone_id: str
    drone_name: str
    drone_latitude: float
    drone_longitude: float
    drone_altitude_m: float
    drone_heading: float
    model_name: str
    model_version: str
    inference_time_ms: int
    detections_count: int


@dataclass
class CVDetection:
    """Single CV detection from frame"""
    detection_id: str
    object_class: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_width: int
    bbox_height: int
    latitude: float
    longitude: float
    estimated_length_m: Optional[float]
    estimated_width_m: Optional[float]
    tracking_id: Optional[str]


class DroneCVParser:
    """
    Parse drone computer vision JSON output.

    Handles the output format from onboard YOLO-style detection pipelines.
    """

    def __init__(self):
        self.frames_parsed = 0
        self.detections_parsed = 0

    def parse_frame(self, data: Dict) -> Tuple[DroneFrameMetadata, List[CVDetection]]:
        """
        Parse a single frame's CV output.

        Returns (metadata, list of detections)
        """
        # Parse metadata
        drone_info = data.get('drone', {})
        drone_pos = drone_info.get('position', {})
        model_info = data.get('model', {})

        metadata = DroneFrameMetadata(
            frame_id=data.get('frame_id', ''),
            timestamp=datetime.fromisoformat(data.get('timestamp', '').replace('Z', '+00:00')),
            drone_id=drone_info.get('drone_id', ''),
            drone_name=drone_info.get('name', ''),
            drone_latitude=drone_pos.get('latitude', 0.0),
            drone_longitude=drone_pos.get('longitude', 0.0),
            drone_altitude_m=drone_pos.get('altitude_m', 0.0),
            drone_heading=drone_pos.get('heading', 0.0),
            model_name=model_info.get('name', ''),
            model_version=model_info.get('version', ''),
            inference_time_ms=model_info.get('inference_time_ms', 0),
            detections_count=data.get('detections_count', 0)
        )

        # Parse detections
        detections = []
        for det_data in data.get('detections', []):
            bbox = det_data.get('bbox', {})
            geo = det_data.get('geo_position', {})
            dims = det_data.get('estimated_dimensions', {})

            detection = CVDetection(
                detection_id=det_data.get('detection_id', ''),
                object_class=det_data.get('class', 'unknown'),
                confidence=det_data.get('confidence', 0.0),
                bbox_x=bbox.get('x', 0),
                bbox_y=bbox.get('y', 0),
                bbox_width=bbox.get('width', 0),
                bbox_height=bbox.get('height', 0),
                latitude=geo.get('latitude', 0.0),
                longitude=geo.get('longitude', 0.0),
                estimated_length_m=dims.get('length_m'),
                estimated_width_m=dims.get('width_m'),
                tracking_id=det_data.get('tracking_id')
            )
            detections.append(detection)

        self.frames_parsed += 1
        self.detections_parsed += len(detections)

        return metadata, detections

    def parse_file(self, filepath: str) -> Tuple[DroneFrameMetadata, List[CVDetection]]:
        """Parse frame from JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self.parse_frame(data)

    def parse_directory(self, dirpath: str) -> List[Tuple[DroneFrameMetadata, List[CVDetection]]]:
        """Parse all JSON files in directory"""
        results = []
        dir_path = Path(dirpath)

        for filepath in sorted(dir_path.glob('*.json')):
            try:
                result = self.parse_file(str(filepath))
                results.append(result)
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")

        return results

    def get_stats(self) -> dict:
        """Get parser statistics"""
        return {
            "frames_parsed": self.frames_parsed,
            "detections_parsed": self.detections_parsed,
        }


# Demo/test
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from generators.drone_generator import DroneCVGenerator

    print("Drone CV Parser Demo")
    print("=" * 60)

    # Generate sample data
    generator = DroneCVGenerator(output_dir="./data/drone")
    frame_data = generator.generate_frame(num_detections=5)

    # Parse it
    parser = DroneCVParser()
    metadata, detections = parser.parse_frame(frame_data)

    print(f"\nFrame: {metadata.frame_id}")
    print(f"Drone: {metadata.drone_name} ({metadata.drone_id})")
    print(f"Position: ({metadata.drone_latitude:.4f}, {metadata.drone_longitude:.4f})")
    print(f"Altitude: {metadata.drone_altitude_m}m, Heading: {metadata.drone_heading}")
    print(f"Model: {metadata.model_name} v{metadata.model_version}")
    print(f"Inference: {metadata.inference_time_ms}ms")

    print(f"\nDetections ({len(detections)}):")
    for det in detections:
        print(f"  {det.detection_id}: {det.object_class} "
              f"(conf: {det.confidence:.2f}) "
              f"at ({det.latitude:.4f}, {det.longitude:.4f})")
        if det.estimated_length_m:
            print(f"    Estimated size: {det.estimated_length_m}m x {det.estimated_width_m}m")

    print(f"\nParser stats: {parser.get_stats()}")
