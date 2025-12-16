"""
Ingester Manager

Controls starting/stopping of ingester subprocesses.
Tracks status in Redis for dashboard visibility.
Supports real-time log streaming via WebSocket.
"""

import subprocess
import sys
import logging
import threading
import queue
import os
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)

# Maximum log lines to keep per ingester
MAX_LOG_LINES = 100


@dataclass
class IngesterConfig:
    """Configuration for an ingester"""
    name: str
    module: str
    description: str
    default_args: Dict = field(default_factory=dict)
    redis_stream: str = ""
    status_key: str = ""


# Available ingesters - Updated for unified simulation
INGESTERS = {
    "world": IngesterConfig(
        name="world",
        module="ingestion.shared.world_simulator",
        description="World Simulator - Ground truth ship positions (START THIS FIRST)",
        default_args={
            "--ships": "500",
            "--dark-pct": "5.0",
            "--rate": "1.0"
        },
        redis_stream="",  # No stream, updates Redis hashes directly
        status_key="maritime:fleet:metadata"
    ),
    "ais": IngesterConfig(
        name="ais",
        module="ingestion.ingesters.ais_nmea_ingester",
        description="AIS Sensor - Only sees ships with AIS ON (skips dark ships)",
        default_args={
            "--source": "unified",
            "--rate": "1.0"
        },
        redis_stream="ais:positions",
        status_key="ingester:ais:status"
    ),
    "radar": IngesterConfig(
        name="radar",
        module="ingestion.ingesters.radar_binary_ingester",
        description="Radar Sensor - 7 coastal stations, sees dark ships, no identity",
        default_args={
            "--source": "unified",
            "--rate": "1.0",
            "--weather": "0.95"
        },
        redis_stream="radar:contacts",
        status_key="ingester:radar:status"
    ),
    "satellite": IngesterConfig(
        name="satellite",
        module="ingestion.ingesters.satellite_file_ingester",
        description="Satellite Sensor - Periodic passes, sees & flags dark ships",
        default_args={
            "--source": "unified",
            "--rate": "1.0",
            "--cloud-cover": "0.3"
        },
        redis_stream="satellite:detections",
        status_key="ingester:satellite:status"
    ),
    "drone": IngesterConfig(
        name="drone",
        module="ingestion.ingesters.drone_cv_ingester",
        description="Drone Sensor - 5 patrol zones, identifies dark ships visually",
        default_args={
            "--source": "unified",
            "--rate": "0.5"
        },
        redis_stream="drone:detections",
        status_key="ingester:drone:status"
    ),
    "fusion": IngesterConfig(
        name="fusion",
        module="ingestion.fusion.fusion_ingester",
        description="Data Fusion - Correlates all sensors, detects dark ships",
        default_args={
            "--rate": "2.0"
        },
        redis_stream="fusion:tracks",
        status_key="fusion:status"
    ),
}


@dataclass
class IngesterProcess:
    """Running ingester process"""
    config: IngesterConfig
    process: subprocess.Popen
    started_at: datetime
    args: Dict
    log_buffer: deque = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    log_thread: Optional[threading.Thread] = None
    _stop_event: Optional[threading.Event] = None


class IngesterManager:
    """
    Manages ingester subprocesses.

    Allows starting/stopping individual ingesters and monitoring their status.
    Uses background threads for Windows-compatible stdout reading.
    """

    def __init__(self, working_dir: Optional[str] = None):
        self.processes: Dict[str, IngesterProcess] = {}
        self.working_dir = Path(working_dir) if working_dir else Path(__file__).parent.parent
        self._lock = threading.Lock()

    def _log_reader_thread(self, name: str, process: subprocess.Popen,
                           log_buffer: deque, stop_event: threading.Event):
        """Background thread to read stdout and populate log buffer."""
        try:
            while not stop_event.is_set():
                if process.poll() is not None:
                    # Process terminated, read remaining output
                    for line in process.stdout:
                        if line:
                            timestamp = datetime.utcnow().strftime("%H:%M:%S")
                            log_buffer.append(f"[{timestamp}] {line.strip()}")
                    break

                line = process.stdout.readline()
                if line:
                    timestamp = datetime.utcnow().strftime("%H:%M:%S")
                    log_buffer.append(f"[{timestamp}] {line.strip()}")
        except Exception as e:
            log_buffer.append(f"[ERROR] Log reader error: {e}")

    def get_available_ingesters(self) -> Dict[str, IngesterConfig]:
        """Get list of available ingesters"""
        return INGESTERS

    def get_status(self, name: str) -> dict:
        """Get status of an ingester"""
        config = INGESTERS.get(name)
        if not config:
            return {"error": f"Unknown ingester: {name}"}

        is_running = name in self.processes and self.processes[name].process.poll() is None

        status = {
            "name": name,
            "description": config.description,
            "running": is_running,
            "redis_stream": config.redis_stream,
            "status_key": config.status_key,
        }

        if is_running:
            proc = self.processes[name]
            status["pid"] = proc.process.pid
            status["started_at"] = proc.started_at.isoformat()
            status["args"] = proc.args

        return status

    def get_all_status(self) -> Dict[str, dict]:
        """Get status of all ingesters"""
        return {name: self.get_status(name) for name in INGESTERS}

    def start(self, name: str, args: Optional[Dict] = None) -> dict:
        """
        Start an ingester subprocess.

        Args:
            name: Ingester name (ais, radar, satellite, drone)
            args: Override default arguments

        Returns:
            Status dict with result
        """
        config = INGESTERS.get(name)
        if not config:
            return {"success": False, "error": f"Unknown ingester: {name}"}

        # Check if already running
        if name in self.processes:
            proc = self.processes[name]
            if proc.process.poll() is None:
                return {
                    "success": False,
                    "error": f"Ingester {name} already running (PID: {proc.process.pid})"
                }

        # Build command
        merged_args = {**config.default_args}
        if args:
            merged_args.update(args)

        cmd = [sys.executable, "-X", "utf8", "-m", config.module]
        for key, value in merged_args.items():
            cmd.extend([key, str(value)])

        logger.info(f"Starting ingester {name}: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Create log buffer and stop event
            log_buffer = deque(maxlen=MAX_LOG_LINES)
            stop_event = threading.Event()

            # Start log reader thread
            log_thread = threading.Thread(
                target=self._log_reader_thread,
                args=(name, process, log_buffer, stop_event),
                daemon=True
            )
            log_thread.start()

            self.processes[name] = IngesterProcess(
                config=config,
                process=process,
                started_at=datetime.utcnow(),
                args=merged_args,
                log_buffer=log_buffer,
                log_thread=log_thread,
                _stop_event=stop_event
            )

            return {
                "success": True,
                "message": f"Started {name} ingester",
                "pid": process.pid
            }

        except Exception as e:
            logger.error(f"Failed to start {name}: {e}")
            return {"success": False, "error": str(e)}

    def stop(self, name: str) -> dict:
        """
        Stop an ingester subprocess.

        Args:
            name: Ingester name

        Returns:
            Status dict with result
        """
        if name not in self.processes:
            return {"success": False, "error": f"Ingester {name} not running"}

        proc = self.processes[name]

        if proc.process.poll() is not None:
            # Already terminated - clean up thread
            if proc._stop_event:
                proc._stop_event.set()
            del self.processes[name]
            return {"success": True, "message": f"Ingester {name} already stopped"}

        logger.info(f"Stopping ingester {name} (PID: {proc.process.pid})")

        try:
            # Signal log reader thread to stop
            if proc._stop_event:
                proc._stop_event.set()

            proc.process.terminate()
            try:
                proc.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.process.kill()
                proc.process.wait()

            # Wait for log thread to finish
            if proc.log_thread and proc.log_thread.is_alive():
                proc.log_thread.join(timeout=1)

            del self.processes[name]
            return {"success": True, "message": f"Stopped {name} ingester"}

        except Exception as e:
            logger.error(f"Failed to stop {name}: {e}")
            return {"success": False, "error": str(e)}

    def stop_all(self) -> dict:
        """Stop all running ingesters"""
        results = {}
        for name in list(self.processes.keys()):
            results[name] = self.stop(name)
        return results

    def get_logs(self, name: str, lines: int = 50) -> List[str]:
        """
        Get recent log output from an ingester.

        Returns buffered log lines (up to MAX_LOG_LINES stored).
        """
        if name not in self.processes:
            return []

        proc = self.processes[name]
        # Return last N lines from buffer
        return list(proc.log_buffer)[-lines:]

    def get_all_logs(self) -> Dict[str, List[str]]:
        """Get logs for all ingesters."""
        return {name: self.get_logs(name) for name in self.processes}


# Singleton manager instance
_manager: Optional[IngesterManager] = None


def get_manager() -> IngesterManager:
    """Get or create the global ingester manager"""
    global _manager
    if _manager is None:
        _manager = IngesterManager()
    return _manager
