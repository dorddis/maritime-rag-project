"""
Generate sample AIS (Automatic Identification System) data
Simulates ship tracking data similar to what Blurgs.ai processes
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# Ship types
SHIP_TYPES = ["Cargo", "Tanker", "Container", "Fishing", "Passenger", "Military", "Unknown"]

# Indian Ocean / Arabian Sea ports (relevant for Indian Navy use case)
PORTS = {
    "Mumbai": (18.9388, 72.8354),
    "Chennai": (13.0827, 80.2707),
    "Kochi": (9.9312, 76.2673),
    "Visakhapatnam": (17.6868, 83.2185),
    "Kandla": (23.0333, 70.2167),
    "Colombo": (6.9271, 79.8612),
    "Dubai": (25.2048, 55.2708),
    "Singapore": (1.3521, 103.8198),
}

def generate_ship_trajectory(ship_id, ship_name, ship_type, start_port, end_port, start_time, num_points=50):
    """Generate a realistic ship trajectory between two ports"""

    start_coords = PORTS[start_port]
    end_coords = PORTS[end_port]

    # Generate trajectory with some randomness
    lats = np.linspace(start_coords[0], end_coords[0], num_points)
    lons = np.linspace(start_coords[1], end_coords[1], num_points)

    # Add some noise to make it realistic
    lats += np.random.normal(0, 0.1, num_points)
    lons += np.random.normal(0, 0.1, num_points)

    # Generate timestamps (ship moves every 30 min on average)
    timestamps = [start_time + timedelta(minutes=30*i + np.random.randint(-5, 5)) for i in range(num_points)]

    # Generate speed (knots) - typically 10-25 knots for cargo ships
    base_speed = np.random.uniform(12, 20)
    speeds = base_speed + np.random.normal(0, 2, num_points)
    speeds = np.clip(speeds, 5, 30)

    # Generate heading (degrees)
    headings = np.arctan2(np.diff(lons, prepend=lons[0]), np.diff(lats, prepend=lats[0])) * 180 / np.pi
    headings = (headings + 360) % 360

    records = []
    for i in range(num_points):
        records.append({
            "mmsi": ship_id,  # Maritime Mobile Service Identity
            "ship_name": ship_name,
            "ship_type": ship_type,
            "timestamp": timestamps[i].isoformat(),
            "latitude": round(lats[i], 6),
            "longitude": round(lons[i], 6),
            "speed_knots": round(speeds[i], 1),
            "heading": round(headings[i], 1),
            "origin_port": start_port,
            "destination_port": end_port,
            "status": "Underway" if speeds[i] > 1 else "Anchored"
        })

    return records


def generate_anomalous_ship(ship_id, ship_name, anomaly_type="dark_ship"):
    """Generate a ship with anomalous behavior"""

    # Dark ship: AIS turned off in suspicious area
    if anomaly_type == "dark_ship":
        # Ship appears near restricted zone, then disappears
        records = []
        base_time = datetime.now() - timedelta(days=2)

        # Normal behavior
        for i in range(10):
            records.append({
                "mmsi": ship_id,
                "ship_name": ship_name,
                "ship_type": "Unknown",
                "timestamp": (base_time + timedelta(hours=i)).isoformat(),
                "latitude": 15.0 + i * 0.1 + np.random.normal(0, 0.01),
                "longitude": 72.0 + i * 0.05 + np.random.normal(0, 0.01),
                "speed_knots": round(np.random.uniform(8, 12), 1),
                "heading": round(np.random.uniform(40, 50), 1),
                "origin_port": "Unknown",
                "destination_port": "Unknown",
                "status": "Underway",
                "anomaly_flag": False
            })

        # Gap in transmission (suspicious)
        gap_hours = 12

        # Reappears in different location
        for i in range(5):
            records.append({
                "mmsi": ship_id,
                "ship_name": ship_name,
                "ship_type": "Unknown",
                "timestamp": (base_time + timedelta(hours=10 + gap_hours + i)).isoformat(),
                "latitude": 16.5 + i * 0.1 + np.random.normal(0, 0.01),
                "longitude": 73.5 + i * 0.05 + np.random.normal(0, 0.01),
                "speed_knots": round(np.random.uniform(8, 12), 1),
                "heading": round(np.random.uniform(40, 50), 1),
                "origin_port": "Unknown",
                "destination_port": "Unknown",
                "status": "Underway",
                "anomaly_flag": True,
                "anomaly_type": "AIS_gap_suspicious_relocation"
            })

        return records

    # Speed anomaly: sudden unrealistic speed
    elif anomaly_type == "speed_anomaly":
        records = []
        base_time = datetime.now() - timedelta(days=1)

        for i in range(20):
            speed = np.random.uniform(12, 18)
            anomaly = False

            # Inject anomaly at point 10
            if i == 10:
                speed = 85  # Impossible speed for cargo ship
                anomaly = True

            records.append({
                "mmsi": ship_id,
                "ship_name": ship_name,
                "ship_type": "Cargo",
                "timestamp": (base_time + timedelta(hours=i)).isoformat(),
                "latitude": 12.0 + i * 0.1,
                "longitude": 75.0 + i * 0.05,
                "speed_knots": round(speed, 1),
                "heading": round(np.random.uniform(80, 100), 1),
                "origin_port": "Kochi",
                "destination_port": "Singapore",
                "status": "Underway",
                "anomaly_flag": anomaly,
                "anomaly_type": "impossible_speed" if anomaly else None
            })

        return records

    return []


def generate_dataset():
    """Generate complete AIS dataset"""

    all_records = []

    # Normal ships
    ships = [
        (123456789, "MV OCEAN STAR", "Cargo", "Mumbai", "Singapore"),
        (234567890, "ARABIAN PEARL", "Tanker", "Dubai", "Chennai"),
        (345678901, "INDIAN PRIDE", "Container", "Kandla", "Colombo"),
        (456789012, "SEA VOYAGER", "Cargo", "Visakhapatnam", "Dubai"),
        (567890123, "COASTAL QUEEN", "Passenger", "Kochi", "Mumbai"),
        (678901234, "BLUE HORIZON", "Tanker", "Singapore", "Kandla"),
        (789012345, "SWIFT CARRIER", "Container", "Chennai", "Singapore"),
        (890123456, "HARBOR MASTER", "Cargo", "Colombo", "Visakhapatnam"),
    ]

    base_time = datetime.now() - timedelta(days=3)

    for i, (mmsi, name, ship_type, origin, dest) in enumerate(ships):
        start_time = base_time + timedelta(hours=i*6)
        trajectory = generate_ship_trajectory(mmsi, name, ship_type, origin, dest, start_time)
        all_records.extend(trajectory)

    # Anomalous ships
    dark_ship = generate_anomalous_ship(999111222, "SHADOW VESSEL", "dark_ship")
    speed_anomaly = generate_anomalous_ship(999333444, "PHANTOM RUNNER", "speed_anomaly")

    all_records.extend(dark_ship)
    all_records.extend(speed_anomaly)

    return pd.DataFrame(all_records)


def create_maritime_documents(df):
    """Create text documents from AIS data for RAG ingestion"""

    documents = []

    # Ship summaries
    for ship_name in df['ship_name'].unique():
        ship_df = df[df['ship_name'] == ship_name]
        first = ship_df.iloc[0]
        last = ship_df.iloc[-1]

        doc = f"""
Ship Report: {ship_name}
MMSI: {first['mmsi']}
Type: {first['ship_type']}
Route: {first.get('origin_port', 'Unknown')} to {first.get('destination_port', 'Unknown')}
First Position: {first['latitude']:.4f}N, {first['longitude']:.4f}E at {first['timestamp']}
Last Position: {last['latitude']:.4f}N, {last['longitude']:.4f}E at {last['timestamp']}
Average Speed: {ship_df['speed_knots'].mean():.1f} knots
Total Positions Recorded: {len(ship_df)}
Current Status: {last['status']}
"""

        if 'anomaly_flag' in ship_df.columns and ship_df['anomaly_flag'].any():
            anomalies = ship_df[ship_df['anomaly_flag'] == True]
            doc += f"\nANOMALY DETECTED: {anomalies.iloc[0].get('anomaly_type', 'Unknown')}"

        documents.append({
            "content": doc.strip(),
            "metadata": {
                "type": "ship_report",
                "ship_name": ship_name,
                "mmsi": str(first['mmsi'])
            }
        })

    # Port activity summaries
    for port_name, coords in PORTS.items():
        # Find ships near this port
        nearby = df[
            (abs(df['latitude'] - coords[0]) < 1) &
            (abs(df['longitude'] - coords[1]) < 1)
        ]

        if len(nearby) > 0:
            doc = f"""
Port Activity Report: {port_name}
Location: {coords[0]:.4f}N, {coords[1]:.4f}E
Ships in vicinity: {nearby['ship_name'].nunique()}
Ship names: {', '.join(nearby['ship_name'].unique())}
Total position records: {len(nearby)}
"""
            documents.append({
                "content": doc.strip(),
                "metadata": {
                    "type": "port_report",
                    "port_name": port_name
                }
            })

    # Anomaly reports
    if 'anomaly_flag' in df.columns:
        anomalies = df[df['anomaly_flag'] == True]
        if len(anomalies) > 0:
            for _, row in anomalies.iterrows():
                doc = f"""
ANOMALY ALERT
Ship: {row['ship_name']}
MMSI: {row['mmsi']}
Type: {row.get('anomaly_type', 'Unknown')}
Location: {row['latitude']:.4f}N, {row['longitude']:.4f}E
Time: {row['timestamp']}
Speed: {row['speed_knots']} knots
This vessel has exhibited suspicious behavior requiring investigation.
"""
                documents.append({
                    "content": doc.strip(),
                    "metadata": {
                        "type": "anomaly_alert",
                        "ship_name": row['ship_name'],
                        "anomaly_type": row.get('anomaly_type', 'Unknown')
                    }
                })

    return documents


if __name__ == "__main__":
    # Generate data
    print("Generating AIS dataset...")
    df = generate_dataset()

    # Save raw data
    df.to_csv("ais_data.csv", index=False)
    print(f"Saved {len(df)} AIS records to ais_data.csv")

    # Create documents for RAG
    print("Creating documents for RAG...")
    documents = create_maritime_documents(df)

    with open("maritime_documents.json", "w") as f:
        json.dump(documents, f, indent=2)
    print(f"Saved {len(documents)} documents to maritime_documents.json")

    # Print summary
    print("\n--- Dataset Summary ---")
    print(f"Total records: {len(df)}")
    print(f"Unique ships: {df['ship_name'].nunique()}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Ship types: {df['ship_type'].value_counts().to_dict()}")

    if 'anomaly_flag' in df.columns:
        anomaly_count = df['anomaly_flag'].sum()
        print(f"Anomalies detected: {anomaly_count}")
