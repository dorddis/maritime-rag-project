"""
Correlation Engine

Gated Global Nearest Neighbor (GNN) algorithm for correlating
sensor detections to unified tracks.
"""

import math
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from scipy.optimize import linear_sum_assignment
import numpy as np

from .schema import UnifiedTrack
from .config import CorrelationGates, SENSOR_CONFIG


class CorrelationEngine:
    """
    Correlates sensor detections to unified tracks using
    spatial-temporal gating and GNN assignment.
    """

    def __init__(self, gates: CorrelationGates):
        self.gates = gates

    def correlate_detection(
        self,
        detection: dict,
        sensor_type: str,
        tracks: Dict[str, UnifiedTrack],
        timestamp: datetime
    ) -> Tuple[Optional[str], float]:
        """
        Correlate a single detection to existing tracks.

        Returns:
            (track_id, confidence) if correlated
            (None, 0) if no correlation found (new track needed)
        """
        if not tracks:
            return None, 0.0

        sensor_char = SENSOR_CONFIG[sensor_type]
        det_lat = detection["latitude"]
        det_lon = detection["longitude"]

        # Find candidate tracks within spatial gate
        candidates = []
        for track_id, track in tracks.items():
            # Predict track position to detection time
            predicted_lat, predicted_lon = self._predict_position(track, timestamp)

            # Calculate distance
            distance_m = self._haversine_m(det_lat, det_lon, predicted_lat, predicted_lon)

            # Adaptive gate based on combined uncertainty
            gate_size = self._calculate_gate_size(
                track.position_uncertainty_m,
                sensor_char.position_error_m
            )

            if distance_m < gate_size:
                candidates.append((track_id, track, distance_m))

        if not candidates:
            return None, 0.0

        # Score candidates and find best match
        best_track_id = None
        best_score = float("inf")

        for track_id, track, distance_m in candidates:
            # Normalized distance score
            combined_uncertainty = math.sqrt(
                track.position_uncertainty_m**2 +
                sensor_char.position_error_m**2
            )
            normalized_distance = distance_m / combined_uncertainty

            # Kinematic consistency score
            kinematic_score = self._kinematic_consistency(track, detection)

            # Combined score (lower is better)
            score = normalized_distance + kinematic_score

            if score < best_score:
                best_score = score
                best_track_id = track_id

        # Convert score to confidence (0-1, higher is better)
        confidence = max(0.0, min(1.0, 1.0 - best_score / 10.0))

        return best_track_id, confidence

    def batch_correlate(
        self,
        detections: List[Tuple[dict, str]],  # (detection, sensor_type)
        tracks: Dict[str, UnifiedTrack],
        timestamp: datetime
    ) -> Dict[str, List[Tuple[dict, str, float]]]:
        """
        Correlate multiple detections using GNN assignment.
        Handles MMSI-based correlation first (deterministic), then spatial.

        Returns:
            Dict mapping track_id to list of (detection, sensor_type, confidence)
            Key "NEW" contains detections that need new tracks
        """
        if not detections:
            return {}

        results: Dict[str, List[Tuple[dict, str, float]]] = {"NEW": []}

        # Phase 1: MMSI-based correlation (deterministic)
        # Build MMSI -> track_id map
        mmsi_to_track: Dict[str, str] = {}
        for track_id, track in tracks.items():
            if track.mmsi:
                mmsi_to_track[track.mmsi] = track_id

        remaining_detections = []
        for det, sensor_type in detections:
            det_mmsi = det.get("mmsi")
            if det_mmsi and str(det_mmsi) in mmsi_to_track:
                # Deterministic correlation by MMSI
                track_id = mmsi_to_track[str(det_mmsi)]
                if track_id not in results:
                    results[track_id] = []
                results[track_id].append((det, sensor_type, 1.0))  # Perfect confidence
            else:
                remaining_detections.append((det, sensor_type))

        # Phase 2: Spatial correlation for remaining detections
        if not remaining_detections:
            return results

        if not tracks:
            results["NEW"].extend([(d, s, 0.0) for d, s in remaining_detections])
            return results

        track_list = list(tracks.items())
        n_det = len(remaining_detections)
        n_tracks = len(track_list)

        # Build cost matrix
        # Rows = detections, Columns = tracks + dummy columns for new tracks
        cost_matrix = np.full((n_det, n_tracks + n_det), 1e6)

        for i, (det, sensor_type) in enumerate(remaining_detections):
            for j, (track_id, track) in enumerate(track_list):
                _, confidence = self.correlate_detection(
                    det, sensor_type, {track_id: track}, timestamp
                )
                if confidence > 0:
                    cost_matrix[i, j] = 1.0 - confidence  # Convert to cost

            # Cost for creating new track (configurable, higher = prefer existing)
            cost_matrix[i, n_tracks + i] = self.gates.new_track_cost

        # Solve assignment using Hungarian algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # Build results
        for i, j in zip(row_ind, col_ind):
            det, sensor_type = remaining_detections[i]
            if j >= n_tracks:
                # Assigned to new track
                results["NEW"].append((det, sensor_type, 0.0))
            else:
                track_id = track_list[j][0]
                confidence = 1.0 - cost_matrix[i, j]
                if track_id not in results:
                    results[track_id] = []
                results[track_id].append((det, sensor_type, confidence))

        return results

    def _predict_position(
        self,
        track: UnifiedTrack,
        target_time: datetime
    ) -> Tuple[float, float]:
        """Predict track position using velocity extrapolation"""
        dt = (target_time - track.updated_at).total_seconds()

        # Limit prediction time to avoid runaway extrapolation
        dt = min(dt, self.gates.max_time_delta_s)

        # Convert velocity (m/s) to degrees
        v_north_deg = track.velocity_north_ms * dt / 111000
        v_east_deg = track.velocity_east_ms * dt / (
            111000 * max(0.1, math.cos(math.radians(track.latitude)))
        )

        return (
            track.latitude + v_north_deg,
            track.longitude + v_east_deg
        )

    def _calculate_gate_size(
        self,
        track_uncertainty: float,
        sensor_uncertainty: float
    ) -> float:
        """Calculate adaptive gate size based on combined uncertainty"""
        combined = math.sqrt(track_uncertainty**2 + sensor_uncertainty**2)
        # N-sigma gate
        gate = combined * self.gates.sigma_multiplier
        # Ensure gate is within bounds
        gate = max(self.gates.min_distance_m, gate)
        return min(self.gates.max_distance_m, gate)

    def _haversine_m(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """Calculate distance in meters between two points"""
        R = 6371000  # Earth radius in meters
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return 2 * R * math.asin(math.sqrt(a))

    def _kinematic_consistency(
        self,
        track: UnifiedTrack,
        detection: dict
    ) -> float:
        """
        Score kinematic consistency between track and detection.
        Returns 0 for perfect match, higher for worse match.
        """
        score = 0.0

        # Speed consistency
        det_speed = detection.get("speed_knots")
        if track.speed_knots and det_speed:
            speed_diff = abs(track.speed_knots - det_speed)
            score += speed_diff / self.gates.max_speed_change_knots

        # Course consistency
        det_course = detection.get("course")
        if track.course and det_course:
            course_diff = abs(track.course - det_course)
            course_diff = min(course_diff, 360 - course_diff)  # Handle wrap-around
            score += course_diff / self.gates.max_course_change_deg

        return score
