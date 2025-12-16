"""
Track Manager

Manages the lifecycle of unified tracks including creation,
update, aging, and dark ship detection.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .schema import UnifiedTrack, TrackStatus, IdentitySource, SensorContribution
from .config import CorrelationGates, DarkShipDetectionConfig, SENSOR_CONFIG

logger = logging.getLogger(__name__)


class TrackManager:
    """
    Manages unified track lifecycle and dark ship detection.

    Responsibilities:
    - Create new tracks from unassigned detections
    - Update existing tracks with new measurements
    - Handle track aging and deletion
    - Detect and flag dark ships
    """

    def __init__(
        self,
        gates: CorrelationGates,
        dark_config: DarkShipDetectionConfig
    ):
        self.gates = gates
        self.dark_config = dark_config
        self.tracks: Dict[str, UnifiedTrack] = {}

        # Statistics
        self.stats = {
            "tracks_created": 0,
            "tracks_dropped": 0,
            "dark_ships_flagged": 0,
            "correlations": {"ais": 0, "radar": 0, "satellite": 0, "drone": 0},
        }

    def create_track(
        self,
        detection: dict,
        sensor_type: str,
        sensor_id: str
    ) -> UnifiedTrack:
        """Create a new track from an initial detection"""
        now = datetime.now(timezone.utc)

        track = UnifiedTrack(
            latitude=detection["latitude"],
            longitude=detection["longitude"],
            speed_knots=detection.get("speed_knots"),
            course=detection.get("course"),
            position_uncertainty_m=SENSOR_CONFIG[sensor_type].position_error_m,
            status=TrackStatus.TENTATIVE,
        )

        # Set identity and kinematics if available
        self._apply_detection_data(track, detection, sensor_type, now)

        # Record sensor contribution
        track.sensor_contributions[sensor_type] = SensorContribution(
            sensor_type=sensor_type,
            sensor_id=sensor_id,
            last_update=now,
            measurement_count=1,
            last_position=(detection["latitude"], detection["longitude"]),
            confidence=1.0
        )
        track.contributing_sensors.append(sensor_type)
        track.update_count = 1

        self.tracks[track.track_id] = track
        self.stats["tracks_created"] += 1
        self.stats["correlations"][sensor_type] += 1

        logger.info(
            f"Created track {track.track_id} from {sensor_type} "
            f"at ({track.latitude:.4f}, {track.longitude:.4f})"
        )

        return track

    def update_track(
        self,
        track_id: str,
        detection: dict,
        sensor_type: str,
        sensor_id: str,
        confidence: float
    ) -> UnifiedTrack:
        """Update an existing track with a new detection"""
        track = self.tracks[track_id]
        now = datetime.now(timezone.utc)
        sensor_char = SENSOR_CONFIG[sensor_type]

        # Weighted average position update (inverse variance weighting)
        track_weight = 1.0 / (track.position_uncertainty_m ** 2)
        det_weight = 1.0 / (sensor_char.position_error_m ** 2)
        total_weight = track_weight + det_weight

        track.latitude = (
            track.latitude * track_weight +
            detection["latitude"] * det_weight
        ) / total_weight

        track.longitude = (
            track.longitude * track_weight +
            detection["longitude"] * det_weight
        ) / total_weight

        # Update uncertainty (combined estimate is better)
        track.position_uncertainty_m = 1.0 / math.sqrt(total_weight)

        # Update velocity from detection if available
        self._update_velocity(track, detection)

        # Apply identity and other detection data
        self._apply_detection_data(track, detection, sensor_type, now)

        # Update sensor contribution
        if sensor_type in track.sensor_contributions:
            contrib = track.sensor_contributions[sensor_type]
            contrib.last_update = now
            contrib.measurement_count += 1
            contrib.last_position = (detection["latitude"], detection["longitude"])
            contrib.confidence = max(contrib.confidence, confidence)
        else:
            track.sensor_contributions[sensor_type] = SensorContribution(
                sensor_type=sensor_type,
                sensor_id=sensor_id,
                last_update=now,
                measurement_count=1,
                last_position=(detection["latitude"], detection["longitude"]),
                confidence=confidence
            )
            track.contributing_sensors.append(sensor_type)

        track.updated_at = now
        track.update_count += 1
        track.correlation_confidence = max(track.correlation_confidence, confidence)

        # Update track status
        self._update_track_status(track)

        # Update track quality score
        self._update_track_quality(track)

        self.stats["correlations"][sensor_type] += 1

        return track

    def _apply_detection_data(
        self,
        track: UnifiedTrack,
        detection: dict,
        sensor_type: str,
        now: datetime
    ):
        """Apply sensor-specific data to track"""

        if sensor_type == "ais":
            # AIS provides authoritative identity
            if detection.get("mmsi"):
                track.identity_source = IdentitySource.AIS
                track.mmsi = str(detection["mmsi"])
                track.ship_name = detection.get("ship_name")
                track.vessel_type = detection.get("ship_type")
                track.ais_last_seen = now
                # If we got AIS, this is NOT a dark ship
                track.is_dark_ship = False
                track.dark_ship_confidence = 0.0
                track.flagged_for_review = False
                track.alert_reason = None

        elif sensor_type == "drone":
            # Drone can provide visual identification
            track.vessel_type = detection.get("object_class") or track.vessel_type
            track.vessel_length_m = detection.get("estimated_length_m") or track.vessel_length_m

        elif sensor_type == "satellite":
            track.vessel_length_m = detection.get("vessel_length_m") or track.vessel_length_m
            # Satellite explicitly flags dark ships
            if detection.get("is_dark_ship"):
                if track.identity_source != IdentitySource.AIS:
                    track.is_dark_ship = True
                    track.dark_ship_confidence = max(
                        track.dark_ship_confidence,
                        0.6
                    )

    def _update_velocity(self, track: UnifiedTrack, detection: dict):
        """Update track velocity from detection"""
        speed = detection.get("speed_knots")
        course = detection.get("course")

        if speed is not None and course is not None:
            track.speed_knots = speed
            track.course = course

            # Convert to velocity components
            course_rad = math.radians(course)
            speed_ms = speed * 0.5144  # knots to m/s
            track.velocity_north_ms = speed_ms * math.cos(course_rad)
            track.velocity_east_ms = speed_ms * math.sin(course_rad)

    def _update_track_status(self, track: UnifiedTrack):
        """Update track lifecycle status"""
        if track.status == TrackStatus.TENTATIVE:
            if track.update_count >= self.gates.tentative_to_confirmed_updates:
                track.status = TrackStatus.CONFIRMED
                logger.info(f"Track {track.track_id} confirmed")
        elif track.status == TrackStatus.COASTING:
            track.status = TrackStatus.CONFIRMED

    def _update_track_quality(self, track: UnifiedTrack):
        """Calculate track quality score (0-100)"""
        quality = 0

        # Sensor diversity bonus (up to 40 points)
        quality += len(track.contributing_sensors) * 10

        # Update count bonus (up to 30 points)
        quality += min(track.update_count, 6) * 5

        # Low uncertainty bonus (up to 30 points)
        if track.position_uncertainty_m < 100:
            quality += 30
        elif track.position_uncertainty_m < 500:
            quality += 20
        elif track.position_uncertainty_m < 1000:
            quality += 10

        track.track_quality = min(100, quality)

    def check_dark_ships(self, now: datetime):
        """
        Check for dark ships - vessels detected by non-AIS sensors
        but not seen by AIS.
        """
        for track_id, track in self.tracks.items():
            if track.status == TrackStatus.DROPPED:
                continue

            # Check AIS-identified ships for AIS gaps
            if track.identity_source == IdentitySource.AIS and track.ais_last_seen:
                gap = (now - track.ais_last_seen).total_seconds()
                track.ais_gap_seconds = gap

                if gap > self.dark_config.ais_gap_threshold_s:
                    # AIS went silent - check if other sensors still see it
                    recent_non_ais = self._has_recent_non_ais_updates(track, now, 120)

                    if recent_non_ais and not track.is_dark_ship:
                        track.is_dark_ship = True
                        track.dark_ship_confidence = min(1.0, gap / 3600)
                        track.flagged_for_review = True
                        track.alert_reason = f"AIS gap: {gap/60:.0f} minutes"
                        self.stats["dark_ships_flagged"] += 1
                        logger.warning(
                            f"DARK SHIP DETECTED: {track_id} "
                            f"(AIS gap: {gap/60:.0f} min)"
                        )
                continue

            # For tracks without AIS identity, check multi-sensor non-AIS correlation
            if track.identity_source == IdentitySource.UNKNOWN:
                non_ais_sensors = [s for s in track.contributing_sensors if s != "ais"]

                if len(non_ais_sensors) >= 2 or "drone" in non_ais_sensors:
                    # Multiple non-AIS sensors agree - likely dark ship
                    if not track.is_dark_ship:
                        track.is_dark_ship = True
                        track.dark_ship_confidence = self._calculate_dark_confidence(track)

                        if track.dark_ship_confidence >= self.dark_config.dark_ship_alert_threshold:
                            track.flagged_for_review = True
                            track.alert_reason = f"Dark ship (sensors: {', '.join(non_ais_sensors)})"
                            self.stats["dark_ships_flagged"] += 1
                            logger.warning(
                                f"DARK SHIP DETECTED: {track_id} "
                                f"(sensors: {', '.join(non_ais_sensors)})"
                            )

    def _has_recent_non_ais_updates(
        self,
        track: UnifiedTrack,
        now: datetime,
        threshold_s: float
    ) -> bool:
        """Check if track has recent updates from non-AIS sensors"""
        for sensor_type, contrib in track.sensor_contributions.items():
            if sensor_type != "ais":
                if (now - contrib.last_update).total_seconds() < threshold_s:
                    return True
        return False

    def _calculate_dark_confidence(self, track: UnifiedTrack) -> float:
        """Calculate confidence that track is a dark ship"""
        confidence = 0.5  # Base confidence

        if "radar" in track.contributing_sensors:
            radar_contrib = track.sensor_contributions.get("radar")
            if radar_contrib and radar_contrib.measurement_count >= self.dark_config.min_radar_correlations:
                confidence += self.dark_config.radar_confidence_boost

        if "satellite" in track.contributing_sensors:
            confidence += self.dark_config.satellite_confidence_boost

        if "drone" in track.contributing_sensors:
            confidence += self.dark_config.drone_confidence_boost

        return min(1.0, confidence)

    def age_tracks(self, now: datetime):
        """Age tracks and handle coasting/dropping"""
        for track_id, track in list(self.tracks.items()):
            if track.status == TrackStatus.DROPPED:
                continue

            time_since_update = (now - track.updated_at).total_seconds()

            if time_since_update > self.gates.drop_timeout_s:
                track.status = TrackStatus.DROPPED
                self.stats["tracks_dropped"] += 1
                logger.info(f"Dropped track {track_id} (no updates for {time_since_update:.0f}s)")

            elif time_since_update > self.gates.coasting_timeout_s:
                if track.status != TrackStatus.COASTING:
                    track.status = TrackStatus.COASTING
                    # Increase uncertainty while coasting
                    track.position_uncertainty_m = min(
                        5000,
                        track.position_uncertainty_m * 1.5
                    )

    def get_active_tracks(self) -> Dict[str, UnifiedTrack]:
        """Get all non-dropped tracks"""
        return {
            tid: track for tid, track in self.tracks.items()
            if track.status != TrackStatus.DROPPED
        }

    def get_dark_ships(self) -> List[UnifiedTrack]:
        """Get all flagged dark ships"""
        return [
            track for track in self.tracks.values()
            if track.is_dark_ship and track.status != TrackStatus.DROPPED
        ]

    def get_stats(self) -> dict:
        """Get track manager statistics"""
        active = len(self.get_active_tracks())
        dark = len(self.get_dark_ships())

        return {
            **self.stats,
            "active_tracks": active,
            "dark_ships_current": dark,
        }
