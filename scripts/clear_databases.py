"""
Clear all maritime data from both Redis and PostgreSQL.
Run this to reset the system with fresh data.
"""
import os
import sys
import asyncio
import redis
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def clear_redis():
    """Clear all maritime data from Redis."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    r = redis.from_url(redis_url)

    print("=" * 50)
    print("CLEARING REDIS")
    print("=" * 50)

    # Get all maritime keys
    maritime_keys = list(r.scan_iter("maritime:*"))

    if not maritime_keys:
        print("No maritime keys found in Redis.")
        return

    print(f"Found {len(maritime_keys)} maritime keys")

    # Delete in batches
    batch_size = 100
    deleted = 0
    for i in range(0, len(maritime_keys), batch_size):
        batch = maritime_keys[i:i + batch_size]
        r.delete(*batch)
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(maritime_keys)} keys...")

    print(f"Deleted {deleted} Redis keys")

    # Also clear streams
    streams = [
        "maritime:ais-positions",
        "maritime:radar",
        "maritime:weather",
        "maritime:satellite",
        "maritime:drone",
        "maritime:alerts",
        "maritime:fused-tracks",
    ]

    for stream in streams:
        try:
            length = r.xlen(stream)
            if length > 0:
                r.delete(stream)
                print(f"  Cleared stream {stream} ({length} messages)")
        except Exception as e:
            pass  # Stream might not exist

    print("Redis cleared successfully!")


def clear_postgres():
    """Clear all maritime data from PostgreSQL."""
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

    if not db_url:
        print("No PostgreSQL URL found, skipping...")
        return

    print("\n" + "=" * 50)
    print("CLEARING POSTGRESQL")
    print("=" * 50)

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Tables to clear (order matters for foreign keys)
        tables = [
            "ais_positions",
            "weather_observations",
            "satellite_detections",
            "anomaly_alerts",
            "vessels",
        ]

        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                if count > 0:
                    cur.execute(f"TRUNCATE TABLE {table} CASCADE")
                    print(f"  Truncated {table} ({count} rows)")
                else:
                    print(f"  Table {table} is empty")
            except Exception as e:
                print(f"  Error with {table}: {e}")

        conn.commit()
        cur.close()
        conn.close()
        print("PostgreSQL cleared successfully!")

    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        print("(This is OK if you're only using Redis)")


def main():
    print("\n" + "=" * 60)
    print("MARITIME DATABASE RESET")
    print("=" * 60 + "\n")

    # Confirm
    if len(sys.argv) < 2 or sys.argv[1] != "--force":
        response = input("This will DELETE all maritime data. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    clear_redis()
    clear_postgres()

    print("\n" + "=" * 60)
    print("DATABASES CLEARED - Ready for fresh data")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Restart the ingestion system to regenerate ships")
    print("  2. Ships will spawn with fresh positions on shipping lanes")


if __name__ == "__main__":
    main()
