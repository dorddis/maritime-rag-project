"""
Maritime Analytics Module
Anomaly detection and geospatial analysis on AIS data

Demonstrates:
1. Time-series anomaly detection
2. Geospatial queries (ships in zone)
3. Statistical analysis on streaming data patterns
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json


class MaritimeAnalytics:
    """Analytics engine for maritime AIS data"""

    def __init__(self, data_path="ais_data.csv"):
        """Load AIS data"""
        self.df = pd.read_csv(data_path)
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        print(f"Loaded {len(self.df)} AIS records")

    # ==================== ANOMALY DETECTION ====================

    def detect_speed_anomalies(self, threshold_knots=35) -> pd.DataFrame:
        """
        Detect ships with unrealistic speeds

        Most cargo ships: 10-25 knots
        Fast ferries: up to 35 knots
        Anything above is suspicious (data error or spoofing)
        """
        anomalies = self.df[self.df['speed_knots'] > threshold_knots].copy()
        anomalies['anomaly_reason'] = f'Speed exceeds {threshold_knots} knots'
        return anomalies

    def detect_ais_gaps(self, gap_hours=6) -> List[Dict]:
        """
        Detect suspicious AIS transmission gaps

        Ships typically transmit every 2-10 seconds when moving.
        A gap of several hours could indicate:
        - AIS turned off intentionally (dark ship)
        - Equipment failure
        - Spoofing attempt
        """
        gaps = []

        for ship_name in self.df['ship_name'].unique():
            ship_df = self.df[self.df['ship_name'] == ship_name].sort_values('timestamp')

            if len(ship_df) < 2:
                continue

            for i in range(1, len(ship_df)):
                time_diff = (ship_df.iloc[i]['timestamp'] - ship_df.iloc[i-1]['timestamp']).total_seconds() / 3600

                if time_diff > gap_hours:
                    gaps.append({
                        'ship_name': ship_name,
                        'mmsi': ship_df.iloc[i]['mmsi'],
                        'gap_hours': round(time_diff, 2),
                        'last_seen': ship_df.iloc[i-1]['timestamp'].isoformat(),
                        'last_position': (ship_df.iloc[i-1]['latitude'], ship_df.iloc[i-1]['longitude']),
                        'reappeared': ship_df.iloc[i]['timestamp'].isoformat(),
                        'new_position': (ship_df.iloc[i]['latitude'], ship_df.iloc[i]['longitude']),
                        'distance_jumped_nm': self._haversine_distance(
                            ship_df.iloc[i-1]['latitude'], ship_df.iloc[i-1]['longitude'],
                            ship_df.iloc[i]['latitude'], ship_df.iloc[i]['longitude']
                        )
                    })

        return gaps

    def detect_zone_violations(self, restricted_zones: List[Dict]) -> List[Dict]:
        """
        Detect ships entering restricted zones

        restricted_zones format:
        [{"name": "Zone A", "lat": 15.0, "lon": 72.0, "radius_nm": 50}, ...]
        """
        violations = []

        for zone in restricted_zones:
            for _, row in self.df.iterrows():
                distance = self._haversine_distance(
                    row['latitude'], row['longitude'],
                    zone['lat'], zone['lon']
                )

                if distance < zone['radius_nm']:
                    violations.append({
                        'ship_name': row['ship_name'],
                        'mmsi': row['mmsi'],
                        'zone_name': zone['name'],
                        'timestamp': row['timestamp'].isoformat(),
                        'position': (row['latitude'], row['longitude']),
                        'distance_from_center_nm': round(distance, 2)
                    })

        return violations

    # ==================== GEOSPATIAL QUERIES ====================

    def ships_near_port(self, port_lat: float, port_lon: float, radius_nm=50) -> pd.DataFrame:
        """Find all ships within radius of a port"""

        def calc_distance(row):
            return self._haversine_distance(row['latitude'], row['longitude'], port_lat, port_lon)

        self.df['distance_nm'] = self.df.apply(calc_distance, axis=1)
        nearby = self.df[self.df['distance_nm'] < radius_nm].copy()

        return nearby.sort_values('distance_nm')

    def ships_in_bounding_box(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> pd.DataFrame:
        """Find ships within a geographic bounding box"""

        return self.df[
            (self.df['latitude'] >= min_lat) &
            (self.df['latitude'] <= max_lat) &
            (self.df['longitude'] >= min_lon) &
            (self.df['longitude'] <= max_lon)
        ]

    def get_ship_trajectory(self, ship_name: str) -> pd.DataFrame:
        """Get full trajectory of a specific ship"""

        return self.df[self.df['ship_name'] == ship_name].sort_values('timestamp')

    # ==================== TIME-SERIES ANALYSIS ====================

    def traffic_over_time(self, interval='1H') -> pd.DataFrame:
        """Aggregate ship traffic over time intervals"""

        self.df.set_index('timestamp', inplace=False)
        traffic = self.df.groupby(pd.Grouper(key='timestamp', freq=interval)).agg({
            'mmsi': 'nunique',  # unique ships
            'ship_name': 'count'  # total positions
        }).rename(columns={'mmsi': 'unique_ships', 'ship_name': 'total_positions'})

        return traffic

    def speed_statistics_by_ship_type(self) -> pd.DataFrame:
        """Statistical analysis of speed by ship type"""

        return self.df.groupby('ship_type')['speed_knots'].agg([
            'mean', 'std', 'min', 'max', 'count'
        ]).round(2)

    # ==================== HELPER FUNCTIONS ====================

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points in nautical miles
        Using Haversine formula
        """
        R = 3440.065  # Earth radius in nautical miles

        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))

        return R * c


def run_analytics_demo():
    """Run analytics demonstration"""

    print("="*60)
    print("MARITIME ANALYTICS DEMO")
    print("Anomaly Detection + Geospatial Analysis")
    print("="*60)

    # Initialize
    analytics = MaritimeAnalytics()

    # 1. Speed anomalies
    print("\n1. SPEED ANOMALY DETECTION")
    print("-"*40)
    speed_anomalies = analytics.detect_speed_anomalies(threshold_knots=30)
    if len(speed_anomalies) > 0:
        print(f"Found {len(speed_anomalies)} speed anomalies:")
        for _, row in speed_anomalies.iterrows():
            print(f"   - {row['ship_name']}: {row['speed_knots']} knots at {row['timestamp']}")
    else:
        print("No speed anomalies detected")

    # 2. AIS gaps
    print("\n2. AIS TRANSMISSION GAP DETECTION")
    print("-"*40)
    gaps = analytics.detect_ais_gaps(gap_hours=4)
    if gaps:
        print(f"Found {len(gaps)} suspicious AIS gaps:")
        for gap in gaps:
            print(f"   - {gap['ship_name']}: {gap['gap_hours']}h gap, jumped {gap['distance_jumped_nm']:.1f} nm")
    else:
        print("No suspicious AIS gaps detected")

    # 3. Zone violations
    print("\n3. RESTRICTED ZONE MONITORING")
    print("-"*40)
    restricted_zones = [
        {"name": "Indian EEZ Checkpoint Alpha", "lat": 15.5, "lon": 73.0, "radius_nm": 30},
        {"name": "Naval Exercise Area", "lat": 12.0, "lon": 75.0, "radius_nm": 25},
    ]
    violations = analytics.detect_zone_violations(restricted_zones)
    if violations:
        print(f"Found {len(violations)} zone entries:")
        for v in violations[:5]:  # Show first 5
            print(f"   - {v['ship_name']} in {v['zone_name']} at {v['timestamp']}")
    else:
        print("No zone violations detected")

    # 4. Ships near Mumbai
    print("\n4. SHIPS NEAR MUMBAI PORT")
    print("-"*40)
    mumbai_ships = analytics.ships_near_port(18.9388, 72.8354, radius_nm=100)
    unique_ships = mumbai_ships['ship_name'].unique()
    print(f"Ships within 100nm of Mumbai: {len(unique_ships)}")
    for ship in unique_ships[:5]:
        print(f"   - {ship}")

    # 5. Speed statistics
    print("\n5. SPEED STATISTICS BY SHIP TYPE")
    print("-"*40)
    speed_stats = analytics.speed_statistics_by_ship_type()
    print(speed_stats.to_string())

    # 6. Traffic analysis
    print("\n6. TRAFFIC OVER TIME (6-hour intervals)")
    print("-"*40)
    traffic = analytics.traffic_over_time('6H')
    print(traffic.head(10).to_string())

    return analytics


if __name__ == "__main__":
    run_analytics_demo()
