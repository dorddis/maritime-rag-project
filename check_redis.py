"""Check Redis stats"""
import redis
from dotenv import load_dotenv
import os

load_dotenv()
r = redis.from_url(os.getenv("REDIS_URL"))

info = r.info("memory")
print("="*50)
print("REDIS MEMORY STATS")
print("="*50)
print(f"Used memory: {info['used_memory_human']}")
print(f"Peak memory: {info['used_memory_peak_human']}")
print(f"Total keys: {r.dbsize()}")

print("\n" + "="*50)
print("STREAM SIZES")
print("="*50)
streams = [
    "maritime:ais-positions",
    "maritime:radar",
    "maritime:weather",
    "maritime:satellite",
    "maritime:drone",
    "maritime:alerts"
]
for stream in streams:
    try:
        length = r.xlen(stream)
        mem = r.memory_usage(stream) or 0
        print(f"{stream}: {length:,} msgs | {mem/1024/1024:.2f} MB")
    except:
        print(f"{stream}: (not created)")
