"""
Maritime Data Ingesters

Standalone processes for ingesting data from various sources.
Each ingester can be started/stopped independently via CLI or admin dashboard.
"""

__all__ = [
    'ais_nmea_ingester',
    'radar_binary_ingester',
    'satellite_file_ingester',
    'drone_cv_ingester'
]
